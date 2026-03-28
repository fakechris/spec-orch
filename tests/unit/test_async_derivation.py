"""Tests for Memory vNext Phase 4: Async Derivation (SON-233)."""

from pathlib import Path

import pytest

from spec_orch.services.memory.derivation import (
    DerivationQueue,
    DerivationTask,
    DerivationWorker,
)
from spec_orch.services.memory.fs_provider import FileSystemMemoryProvider
from spec_orch.services.memory.service import MemoryService
from spec_orch.services.memory.types import MemoryEntry, MemoryLayer


@pytest.fixture()
def queue(tmp_path: Path) -> DerivationQueue:
    return DerivationQueue(tmp_path / "derivation.db")


@pytest.fixture()
def svc_sync(tmp_path: Path) -> MemoryService:
    p = FileSystemMemoryProvider(tmp_path / "memory")
    return MemoryService(provider=p, derivation_mode="sync")


@pytest.fixture()
def svc_async(tmp_path: Path) -> MemoryService:
    p = FileSystemMemoryProvider(tmp_path / "memory")
    return MemoryService(provider=p, derivation_mode="async")


class TestDerivationQueue:
    def test_enqueue_returns_task_id(self, queue: DerivationQueue):
        task_id = queue.enqueue("compact", {"max_age_days": 30})
        assert isinstance(task_id, str)
        assert len(task_id) == 12

    def test_pending_count(self, queue: DerivationQueue):
        assert queue.pending_count() == 0
        queue.enqueue("task1")
        queue.enqueue("task2")
        assert queue.pending_count() == 2

    def test_dequeue_returns_tasks(self, queue: DerivationQueue):
        queue.enqueue("compact")
        queue.enqueue("profile-refresh")
        tasks = queue.dequeue(batch_size=5)
        assert len(tasks) == 2
        assert all(isinstance(t, DerivationTask) for t in tasks)
        assert all(t.status == "running" for t in tasks)
        assert queue.pending_count() == 0

    def test_dequeue_respects_batch_size(self, queue: DerivationQueue):
        for i in range(5):
            queue.enqueue(f"task-{i}")
        tasks = queue.dequeue(batch_size=2)
        assert len(tasks) == 2
        assert queue.pending_count() == 3

    def test_complete_marks_done(self, queue: DerivationQueue):
        queue.enqueue("task1")
        tasks = queue.dequeue()
        queue.complete(tasks[0].task_id)
        assert queue.pending_count() == 0

    def test_complete_with_error(self, queue: DerivationQueue):
        queue.enqueue("failing-task")
        tasks = queue.dequeue()
        queue.complete(tasks[0].task_id, error="something broke")
        row = queue._db.execute(
            "SELECT status, error FROM derivation_queue WHERE task_id = ?",
            (tasks[0].task_id,),
        ).fetchone()
        assert row[0] == "failed"
        assert row[1] == "something broke"

    def test_cleanup_removes_old_completed(self, queue: DerivationQueue):
        queue.enqueue("old-task")
        tasks = queue.dequeue()
        queue.complete(tasks[0].task_id)
        queue._db.execute(
            "UPDATE derivation_queue SET completed_at = '2020-01-01T00:00:00' WHERE task_id = ?",
            (tasks[0].task_id,),
        )
        queue._db.commit()
        removed = queue.cleanup(max_age_days=1)
        assert removed == 1

    def test_dequeue_idempotent(self, queue: DerivationQueue):
        queue.enqueue("task1")
        queue.dequeue(batch_size=5)
        tasks2 = queue.dequeue(batch_size=5)
        assert len(tasks2) == 0


class TestDerivationWorker:
    def test_register_and_process(self, queue: DerivationQueue):
        results: list[str] = []

        def handler(payload: dict) -> None:
            results.append(payload.get("name", ""))

        worker = DerivationWorker(queue)
        worker.register("greet", handler)
        queue.enqueue("greet", {"name": "world"})
        processed = worker.process_batch()
        assert processed == 1
        assert results == ["world"]

    def test_unregistered_type_logs_error(self, queue: DerivationQueue):
        worker = DerivationWorker(queue)
        queue.enqueue("unknown-type")
        processed = worker.process_batch()
        assert processed == 0

    def test_handler_failure_marks_task_failed(self, queue: DerivationQueue):
        def bad_handler(payload: dict) -> None:
            raise ValueError("test error")

        worker = DerivationWorker(queue)
        worker.register("bad", bad_handler)
        queue.enqueue("bad")
        processed = worker.process_batch()
        assert processed == 0
        row = queue._db.execute(
            "SELECT status, error FROM derivation_queue WHERE status = 'failed'"
        ).fetchone()
        assert row is not None
        assert "test error" in row[1]

    def test_tick_alias(self, queue: DerivationQueue):
        worker = DerivationWorker(queue)
        worker.register("noop", lambda p: None)
        queue.enqueue("noop")
        assert worker.tick() == 1


class TestMemoryServiceDerivationMode:
    def test_sync_mode_default(self, svc_sync: MemoryService):
        assert svc_sync.derivation_mode == "sync"

    def test_async_mode(self, svc_async: MemoryService):
        assert svc_async.derivation_mode == "async"

    def test_enqueue_creates_task(self, svc_async: MemoryService):
        task_id = svc_async.enqueue_derivation("compact")
        assert isinstance(task_id, str)

    def test_process_derivations(self, svc_async: MemoryService):
        svc_async.enqueue_derivation("compact", {"max_age_days": 30})
        processed = svc_async.process_derivations()
        assert processed == 1


class TestSchedulePostRunDerivations:
    def test_async_mode_enqueues(self, svc_async: MemoryService):
        task_ids = svc_async.schedule_post_run_derivations(issue_id="I1", run_id="r1")
        assert len(task_ids) == 6

    def test_sync_mode_executes_inline(self, svc_sync: MemoryService):
        task_ids = svc_sync.schedule_post_run_derivations(issue_id="I1", run_id="r1")
        assert task_ids == []


class TestSoftDeleteStale:
    def test_marks_old_entries_superseded(self, svc_sync: MemoryService):
        from datetime import UTC, datetime, timedelta

        old_time = (datetime.now(UTC) - timedelta(days=100)).isoformat()
        svc_sync.store(
            MemoryEntry(
                key="old-ep",
                content="old event",
                layer=MemoryLayer.EPISODIC,
                metadata={"entity_scope": "issue", "entity_id": "X"},
            )
        )
        svc_sync.provider._db.execute(
            "UPDATE memory_index SET updated_at = ? WHERE key = ?",
            (old_time, "old-ep"),
        )
        svc_sync.provider._db.commit()
        svc_sync.store(
            MemoryEntry(
                key="new-ep",
                content="new event",
                layer=MemoryLayer.EPISODIC,
                metadata={"entity_scope": "issue", "entity_id": "X"},
            )
        )
        marked = svc_sync._soft_delete_stale_entries(max_age_days=90)
        assert marked == 1
        old = svc_sync.get("old-ep")
        assert old is not None
        assert old.metadata["relation_type"] == "superseded"
        new = svc_sync.get("new-ep")
        assert new is not None
        assert new.metadata.get("relation_type") != "superseded"

    def test_skips_already_superseded(self, svc_sync: MemoryService):
        from datetime import UTC, datetime, timedelta

        old_time = (datetime.now(UTC) - timedelta(days=100)).isoformat()
        svc_sync.store(
            MemoryEntry(
                key="already-super",
                content="already done",
                layer=MemoryLayer.EPISODIC,
                metadata={"relation_type": "superseded"},
            )
        )
        svc_sync.provider._db.execute(
            "UPDATE memory_index SET updated_at = ? WHERE key = ?",
            (old_time, "already-super"),
        )
        svc_sync.provider._db.commit()
        marked = svc_sync._soft_delete_stale_entries(max_age_days=90)
        assert marked == 0
