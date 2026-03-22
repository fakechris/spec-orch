"""Tests for Memory vNext Phase 1: relation layer (SON-228/229/230)."""

from pathlib import Path

import pytest

from spec_orch.services.memory.fs_provider import FileSystemMemoryProvider
from spec_orch.services.memory.service import MemoryService
from spec_orch.services.memory.types import MemoryEntry, MemoryLayer


@pytest.fixture()
def provider(tmp_path: Path) -> FileSystemMemoryProvider:
    return FileSystemMemoryProvider(tmp_path / "memory")


@pytest.fixture()
def svc(tmp_path: Path) -> MemoryService:
    p = FileSystemMemoryProvider(tmp_path / "memory")
    return MemoryService(provider=p)


class TestSchemaColumns:
    """SON-228: verify new columns exist in fresh and migrated databases."""

    def test_new_db_has_relation_columns(self, provider: FileSystemMemoryProvider):
        cols = {
            row[1] for row in provider._db.execute("PRAGMA table_info(memory_index)").fetchall()
        }
        assert "entity_scope" in cols
        assert "entity_id" in cols
        assert "relation_type" in cols

    def test_store_writes_relation_columns(self, provider: FileSystemMemoryProvider):
        entry = MemoryEntry(
            key="t1",
            content="test",
            layer=MemoryLayer.EPISODIC,
            metadata={
                "entity_scope": "issue",
                "entity_id": "SON-100",
                "relation_type": "observed",
            },
        )
        provider.store(entry)
        row = provider._db.execute(
            "SELECT entity_scope, entity_id, relation_type FROM memory_index WHERE key = ?",
            ("t1",),
        ).fetchone()
        assert row == ("issue", "SON-100", "observed")

    def test_store_defaults_relation_columns(self, provider: FileSystemMemoryProvider):
        entry = MemoryEntry(key="t2", content="no meta", layer=MemoryLayer.WORKING)
        provider.store(entry)
        row = provider._db.execute(
            "SELECT entity_scope, entity_id, relation_type FROM memory_index WHERE key = ?",
            ("t2",),
        ).fetchone()
        assert row == ("", "", "observed")

    def test_migration_adds_columns_to_old_db(self, tmp_path: Path):
        """Simulate an old DB without relation columns, then open with new code."""
        import sqlite3

        db_path = tmp_path / "old_memory" / "_index.db"
        db_path.parent.mkdir(parents=True)
        for layer in MemoryLayer:
            (tmp_path / "old_memory" / layer.value).mkdir(parents=True, exist_ok=True)

        db = sqlite3.connect(str(db_path))
        db.execute(
            """CREATE TABLE memory_index (
                key TEXT PRIMARY KEY,
                layer TEXT NOT NULL,
                tags TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT ''
            )"""
        )
        db.execute(
            "INSERT INTO memory_index (key, layer, tags) VALUES (?, ?, ?)",
            ("old-key", "episodic", "[]"),
        )
        db.commit()
        db.close()

        provider = FileSystemMemoryProvider(tmp_path / "old_memory")
        cols = {
            row[1] for row in provider._db.execute("PRAGMA table_info(memory_index)").fetchall()
        }
        assert "entity_scope" in cols
        assert "entity_id" in cols
        assert "relation_type" in cols

        row = provider._db.execute(
            "SELECT entity_scope, entity_id, relation_type FROM memory_index WHERE key = ?",
            ("old-key",),
        ).fetchone()
        assert row == ("", "", "observed")


class TestFilteredKeysEntityFilter:
    """SON-228: verify _filtered_keys supports entity-based filtering."""

    def test_filter_by_entity_scope_and_id(self, provider: FileSystemMemoryProvider):
        for i, (scope, eid) in enumerate(
            [("issue", "A"), ("issue", "B"), ("mission", "M1"), ("issue", "A")]
        ):
            provider.store(
                MemoryEntry(
                    key=f"e{i}",
                    content=f"c{i}",
                    layer=MemoryLayer.EPISODIC,
                    metadata={"entity_scope": scope, "entity_id": eid},
                )
            )
        keys = provider._filtered_keys(entity_scope="issue", entity_id="A")
        assert set(keys) == {"e0", "e3"}

    def test_exclude_relation_types(self, provider: FileSystemMemoryProvider):
        for i, rt in enumerate(["observed", "superseded", "derive", "superseded"]):
            provider.store(
                MemoryEntry(
                    key=f"r{i}",
                    content=f"c{i}",
                    layer=MemoryLayer.SEMANTIC,
                    metadata={"relation_type": rt},
                )
            )
        keys = provider._filtered_keys(exclude_relation_types=["superseded"])
        assert "r1" not in keys
        assert "r3" not in keys
        assert "r0" in keys
        assert "r2" in keys


class TestWriteSideRelationFields:
    """SON-229: verify write methods populate entity fields."""

    def test_consolidate_run_sets_entity(self, svc: MemoryService):
        svc.consolidate_run(
            run_id="run-1",
            issue_id="SON-50",
            succeeded=True,
        )
        entry = svc.get("run-summary-run-1")
        assert entry is not None
        assert entry.metadata["entity_scope"] == "issue"
        assert entry.metadata["entity_id"] == "SON-50"
        assert entry.metadata["relation_type"] == "summarize"
        assert entry.metadata["source_run_id"] == "run-1"

    def test_record_builder_telemetry_sets_entity(self, svc: MemoryService):
        svc.record_builder_telemetry(
            run_id="run-2",
            issue_id="SON-60",
            tool_sequence=["read", "write"],
        )
        entry = svc.get("builder-telemetry-run-2")
        assert entry is not None
        assert entry.metadata["entity_scope"] == "issue"
        assert entry.metadata["entity_id"] == "SON-60"
        assert entry.metadata["relation_type"] == "observed"

    def test_record_acceptance_sets_entity(self, svc: MemoryService):
        svc.record_acceptance(issue_id="SON-70", accepted_by="user1", run_id="r3")
        entry = svc.get("acceptance-SON-70")
        assert entry is not None
        assert entry.metadata["entity_scope"] == "issue"
        assert entry.metadata["entity_id"] == "SON-70"

    def test_record_issue_completion_sets_entity(self, svc: MemoryService):
        svc.record_issue_completion("SON-80", succeeded=False, summary="fail")
        entry = svc.get("issue-result-SON-80")
        assert entry is not None
        assert entry.metadata["entity_scope"] == "issue"
        assert entry.metadata["entity_id"] == "SON-80"
        assert entry.metadata["relation_type"] == "observed"

    def test_record_mission_event_sets_entity(self, svc: MemoryService):
        svc.record_mission_event("M1", "started")
        entry = svc.get("mission-event-M1-started")
        assert entry is not None
        assert entry.metadata["entity_scope"] == "mission"
        assert entry.metadata["entity_id"] == "M1"


class TestRecallLatest:
    """SON-230: verify recall_latest filters by entity and excludes superseded."""

    def test_recall_latest_returns_entity_entries(self, svc: MemoryService):
        for i in range(3):
            svc.store(
                MemoryEntry(
                    key=f"run-summary-r{i}",
                    content=f"run {i}",
                    layer=MemoryLayer.SEMANTIC,
                    metadata={
                        "entity_scope": "issue",
                        "entity_id": "SON-99",
                        "relation_type": "summarize",
                    },
                )
            )
        svc.store(
            MemoryEntry(
                key="run-summary-other",
                content="other issue",
                layer=MemoryLayer.SEMANTIC,
                metadata={
                    "entity_scope": "issue",
                    "entity_id": "SON-100",
                    "relation_type": "summarize",
                },
            )
        )

        results = svc.recall_latest(entity_scope="issue", entity_id="SON-99")
        assert len(results) == 3
        assert all(e.metadata["entity_id"] == "SON-99" for e in results)

    def test_recall_latest_excludes_superseded(self, svc: MemoryService):
        svc.store(
            MemoryEntry(
                key="old",
                content="old conclusion",
                layer=MemoryLayer.SEMANTIC,
                metadata={
                    "entity_scope": "issue",
                    "entity_id": "SON-99",
                    "relation_type": "superseded",
                },
            )
        )
        svc.store(
            MemoryEntry(
                key="new",
                content="new conclusion",
                layer=MemoryLayer.SEMANTIC,
                metadata={
                    "entity_scope": "issue",
                    "entity_id": "SON-99",
                    "relation_type": "summarize",
                },
            )
        )

        results = svc.recall_latest(entity_scope="issue", entity_id="SON-99")
        assert len(results) == 1
        assert results[0].key == "new"

    def test_recall_latest_with_layer_filter(self, svc: MemoryService):
        svc.store(
            MemoryEntry(
                key="ep1",
                content="episodic",
                layer=MemoryLayer.EPISODIC,
                metadata={
                    "entity_scope": "issue",
                    "entity_id": "X",
                    "relation_type": "observed",
                },
            )
        )
        svc.store(
            MemoryEntry(
                key="sem1",
                content="semantic",
                layer=MemoryLayer.SEMANTIC,
                metadata={
                    "entity_scope": "issue",
                    "entity_id": "X",
                    "relation_type": "summarize",
                },
            )
        )
        results = svc.recall_latest(
            entity_scope="issue", entity_id="X", layer=MemoryLayer.EPISODIC.value
        )
        assert len(results) == 1
        assert results[0].key == "ep1"


class TestRebuildIndexPreservesRelationColumns:
    def test_rebuild_preserves_entity_metadata(self, tmp_path: Path):
        provider = FileSystemMemoryProvider(tmp_path / "mem")
        provider.store(
            MemoryEntry(
                key="with-entity",
                content="test",
                layer=MemoryLayer.SEMANTIC,
                metadata={
                    "entity_scope": "project",
                    "entity_id": "my-repo",
                    "relation_type": "summarize",
                },
            )
        )
        provider._rebuild_index()
        row = provider._db.execute(
            "SELECT entity_scope, entity_id, relation_type FROM memory_index WHERE key = ?",
            ("with-entity",),
        ).fetchone()
        assert row == ("project", "my-repo", "summarize")
