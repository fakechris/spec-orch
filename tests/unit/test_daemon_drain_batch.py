"""Tests for batched drain in DaemonIssueDispatcher."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from spec_orch.services.daemon_issue_dispatcher import DaemonIssueDispatcher
from spec_orch.services.daemon_state_store import DaemonStateStore


def _make_shared_state() -> Any:
    """Return a minimal _DaemonSharedState-like object."""
    from spec_orch.services.daemon import _DaemonSharedState

    return _DaemonSharedState(
        processed=set(),
        triaged=set(),
        pr_commits={},
        retry_counts={},
        retry_at={},
        dead_letter=set(),
        in_progress=set(),
        reaction_marks=set(),
    )


def _make_dispatcher(
    tmp_path: Path,
    *,
    drain_batch_size: int = 5,
) -> DaemonIssueDispatcher:
    """Build a DaemonIssueDispatcher with real state store and mock collaborators."""
    lockdir = tmp_path / ".locks"
    lockdir.mkdir(parents=True, exist_ok=True)
    state_store = DaemonStateStore(lockdir)
    config = MagicMock()
    config.hotfix_labels = ["hotfix"]
    host = MagicMock()
    pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="test-drain")
    dispatcher = DaemonIssueDispatcher(
        config=config,
        state_store=state_store,
        admission_governor=MagicMock(),
        daemon_executor=MagicMock(),
        executor_pool=pool,
        state_lock=threading.Lock(),
        shared_state=_make_shared_state(),
        host=host,
        process_lock_owner="test:1",
        drain_batch_size=drain_batch_size,
    )
    return dispatcher


def _enqueue(dispatcher: DaemonIssueDispatcher, issue_id: str) -> None:
    """Enqueue a fake execution intent."""
    dispatcher._state_store.enqueue_execution_intent(
        issue_id=issue_id,
        raw_issue={"identifier": issue_id, "id": f"uid-{issue_id}"},
        is_hotfix=False,
    )


class TestDrainBatchSize:
    """Verify that _drain_execution_queue respects drain_batch_size."""

    def test_drains_at_most_batch_size(self, tmp_path: Path) -> None:
        """With 10 intents queued and batch_size=3, only 3 are drained per call."""
        dispatcher = _make_dispatcher(tmp_path, drain_batch_size=3)
        for i in range(10):
            _enqueue(dispatcher, f"ISS-{i}")

        client = MagicMock()
        controller = MagicMock()

        drained = dispatcher._drain_execution_queue(client, controller)

        assert drained == 3
        assert len(dispatcher._execution_futures) == 3
        # 7 intents should remain in the queue
        remaining = dispatcher._state_store.list_execution_intents()
        assert len(remaining) == 7

    def test_remaining_intents_available_next_cycle(self, tmp_path: Path) -> None:
        """After draining a batch, the remaining intents are still in the queue."""
        dispatcher = _make_dispatcher(tmp_path, drain_batch_size=2)
        for i in range(5):
            _enqueue(dispatcher, f"ISS-{i}")

        client = MagicMock()
        controller = MagicMock()

        # First cycle
        drained_1 = dispatcher._drain_execution_queue(client, controller)
        assert drained_1 == 2

        # Second cycle
        drained_2 = dispatcher._drain_execution_queue(client, controller)
        assert drained_2 == 2

        # Third cycle - only 1 left
        drained_3 = dispatcher._drain_execution_queue(client, controller)
        assert drained_3 == 1

        # Fourth cycle - empty
        drained_4 = dispatcher._drain_execution_queue(client, controller)
        assert drained_4 == 0

    def test_drain_returns_count(self, tmp_path: Path) -> None:
        """drain returns the exact count of intents drained."""
        dispatcher = _make_dispatcher(tmp_path, drain_batch_size=10)

        client = MagicMock()
        controller = MagicMock()

        # Empty queue returns 0
        assert dispatcher._drain_execution_queue(client, controller) == 0

        # Fewer intents than batch_size returns actual count
        _enqueue(dispatcher, "ISS-A")
        _enqueue(dispatcher, "ISS-B")
        _enqueue(dispatcher, "ISS-C")
        drained = dispatcher._drain_execution_queue(client, controller)
        assert drained == 3

    def test_default_batch_size_is_five(self, tmp_path: Path) -> None:
        """When drain_batch_size is not specified, defaults to 5."""
        dispatcher = _make_dispatcher(tmp_path)  # default
        assert dispatcher._drain_batch_size == 5

    def test_submit_failure_still_counts_toward_batch(self, tmp_path: Path) -> None:
        """A submit failure still increments the drain count."""
        dispatcher = _make_dispatcher(tmp_path, drain_batch_size=2)
        dispatcher._executor_pool.submit = MagicMock(side_effect=RuntimeError("pool full"))

        _enqueue(dispatcher, "ISS-X")
        _enqueue(dispatcher, "ISS-Y")
        _enqueue(dispatcher, "ISS-Z")

        client = MagicMock()
        controller = MagicMock()

        drained = dispatcher._drain_execution_queue(client, controller)
        assert drained == 2
        # One intent should remain
        remaining = dispatcher._state_store.list_execution_intents()
        assert len(remaining) == 1
