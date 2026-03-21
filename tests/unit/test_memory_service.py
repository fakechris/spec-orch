"""Tests for MemoryService and EventBus integration."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from spec_orch.services.memory.service import MemoryService, reset_memory_service
from spec_orch.services.memory.types import MemoryEntry, MemoryLayer, MemoryQuery


@pytest.fixture(autouse=True)
def _clean_singleton():
    reset_memory_service()
    yield
    reset_memory_service()


@pytest.fixture()
def svc(tmp_path: Path) -> MemoryService:
    return MemoryService(repo_root=tmp_path)


class TestMemoryServiceCRUD:
    def test_store_and_get(self, svc: MemoryService):
        entry = MemoryEntry(key="k1", content="hello", layer=MemoryLayer.WORKING)
        svc.store(entry)
        result = svc.get("k1")
        assert result is not None
        assert result.content == "hello"

    def test_recall(self, svc: MemoryService):
        svc.store(MemoryEntry(key="a", content="apple pie", layer=MemoryLayer.SEMANTIC))
        svc.store(MemoryEntry(key="b", content="banana split", layer=MemoryLayer.SEMANTIC))
        results = svc.recall(MemoryQuery(text="apple"))
        assert len(results) == 1

    def test_forget(self, svc: MemoryService):
        svc.store(MemoryEntry(key="gone", content="bye", layer=MemoryLayer.WORKING))
        assert svc.forget("gone") is True
        assert svc.get("gone") is None

    def test_list_keys(self, svc: MemoryService):
        svc.store(MemoryEntry(key="x", content="1", layer=MemoryLayer.WORKING))
        svc.store(MemoryEntry(key="y", content="2", layer=MemoryLayer.EPISODIC))
        assert set(svc.list_keys()) == {"x", "y"}
        assert svc.list_keys(layer="working") == ["x"]

    def test_compact_removes_stale_episodic(self, svc: MemoryService):
        old = (datetime.now(UTC) - timedelta(days=60)).isoformat()
        svc.store(
            MemoryEntry(
                key="ep-old",
                content="stale",
                layer=MemoryLayer.EPISODIC,
                created_at=old,
            )
        )
        svc.store(MemoryEntry(key="ep-new", content="fresh", layer=MemoryLayer.EPISODIC))
        stats = svc.compact(max_age_days=30)
        assert stats["removed"] == 1
        assert stats["retained"] == 1
        assert svc.get("ep-old") is None
        assert svc.get("ep-new") is not None

    def test_consolidate_run_returns_none_when_empty(self, svc: MemoryService):
        assert (
            svc.consolidate_run(
                run_id="r1",
                issue_id="i1",
                succeeded=True,
                failed_conditions=None,
                key_learnings="",
            )
            is None
        )

    def test_consolidate_run_stores_semantic(self, svc: MemoryService):
        key = svc.consolidate_run(
            run_id="run-abc",
            issue_id="ISS-1",
            succeeded=False,
            failed_conditions=["ci", "review"],
            key_learnings="Retry with smaller diff",
        )
        assert key is not None
        entry = svc.get(key)
        assert entry is not None
        assert entry.layer == MemoryLayer.SEMANTIC
        assert "run-summary" in entry.tags
        assert "run-abc" in entry.content
        assert "Failed conditions: ci, review" in entry.content


class TestLifecycleCapture:
    def test_record_mission_event(self, svc: MemoryService):
        key = svc.record_mission_event("M-1", "planning", detail="Starting plan")
        entry = svc.get(key)
        assert entry is not None
        assert entry.layer == MemoryLayer.EPISODIC
        assert "mission-event" in entry.tags
        assert "Starting plan" in entry.content

    def test_record_issue_completion(self, svc: MemoryService):
        key = svc.record_issue_completion("SON-99", succeeded=True, summary="All tests pass")
        entry = svc.get(key)
        assert entry is not None
        assert "succeeded" in entry.tags
        assert entry.metadata["issue_id"] == "SON-99"


class TestEventBusIntegration:
    def test_subscribe_captures_mission_events(self, svc: MemoryService):
        from spec_orch.services.event_bus import Event, EventTopic, get_event_bus, reset_event_bus

        reset_event_bus()
        svc.subscribe_to_event_bus()
        bus = get_event_bus()

        bus.publish(
            Event(
                topic=EventTopic.MISSION_STATE,
                payload={"mission_id": "test-m", "old_state": "planning", "new_state": "executing"},
                source="test",
            )
        )

        entry = svc.get("mission-event-test-m-executing")
        assert entry is not None
        assert entry.layer == MemoryLayer.EPISODIC

        reset_event_bus()

    def test_subscribe_captures_issue_completion(self, svc: MemoryService):
        from spec_orch.services.event_bus import Event, EventTopic, get_event_bus, reset_event_bus

        reset_event_bus()
        svc.subscribe_to_event_bus()
        bus = get_event_bus()

        bus.publish(
            Event(
                topic=EventTopic.ISSUE_STATE,
                payload={"issue_id": "SON-42", "state": "merged"},
                source="test",
            )
        )

        entry = svc.get("issue-result-SON-42")
        assert entry is not None
        assert "succeeded" in entry.tags

        reset_event_bus()


class TestCustomProvider:
    def test_accepts_custom_provider(self):
        mock = MagicMock()
        mock.store.return_value = "custom-key"
        mock.get.return_value = MemoryEntry(
            key="custom-key", content="hi", layer=MemoryLayer.WORKING
        )

        svc = MemoryService(provider=mock)
        key = svc.store(MemoryEntry(key="x", content="y", layer=MemoryLayer.WORKING))
        assert key == "custom-key"
        mock.store.assert_called_once()
