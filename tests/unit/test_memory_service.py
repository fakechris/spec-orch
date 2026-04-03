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
        old_entry = svc.get("ep-old")
        assert old_entry is not None
        assert old_entry.metadata.get("relation_type") == "superseded"
        assert svc.get("ep-new") is not None

    def test_consolidate_run_stores_successful_run(self, svc: MemoryService):
        key = svc.consolidate_run(
            run_id="r1",
            issue_id="i1",
            succeeded=True,
            failed_conditions=None,
            key_learnings="",
        )
        assert key == "run-summary-r1"
        entry = svc.get(key)
        assert entry is not None
        assert "succeeded" in entry.content

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
        assert entry.metadata["failed_conditions"] == ["ci", "review"]
        assert entry.metadata["succeeded"] is False


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


class TestCompactDistillation:
    def test_compact_distills_grouped_episodes(self, svc: MemoryService):
        """Expired episodic entries with the same issue_id are distilled."""
        old_ts = (datetime.now(UTC) - timedelta(days=60)).isoformat()
        for i in range(3):
            svc.store(
                MemoryEntry(
                    key=f"ep-{i}",
                    content=f"Event {i} for issue SON-100",
                    layer=MemoryLayer.EPISODIC,
                    created_at=old_ts,
                    metadata={"issue_id": "SON-100"},
                    tags=["issue-result"],
                )
            )

        stats = svc.compact(max_age_days=30, summarize=True)
        assert stats["removed"] == 3
        assert stats["distilled"] == 1

        keys = svc.list_keys(layer="semantic", tags=["distilled"])
        assert len(keys) == 1
        distilled = svc.get(keys[0])
        assert distilled is not None
        assert distilled.key.startswith("distilled-SON-100-")
        assert distilled.layer == MemoryLayer.SEMANTIC
        assert "distilled" in distilled.tags
        assert distilled.metadata["source_count"] == 3

    def test_compact_no_distill_when_disabled(self, svc: MemoryService):
        old_ts = (datetime.now(UTC) - timedelta(days=60)).isoformat()
        for i in range(3):
            svc.store(
                MemoryEntry(
                    key=f"nd-{i}",
                    content=f"Event {i}",
                    layer=MemoryLayer.EPISODIC,
                    created_at=old_ts,
                    metadata={"issue_id": "SON-200"},
                )
            )
        stats = svc.compact(max_age_days=30, summarize=False)
        assert stats["removed"] == 3
        assert stats["distilled"] == 0
        assert svc.get("distilled-SON-200") is None

    def test_compact_skips_single_entry_groups(self, svc: MemoryService):
        old_ts = (datetime.now(UTC) - timedelta(days=60)).isoformat()
        svc.store(
            MemoryEntry(
                key="single",
                content="Only one",
                layer=MemoryLayer.EPISODIC,
                created_at=old_ts,
                metadata={"issue_id": "SON-300"},
            )
        )
        stats = svc.compact(max_age_days=30, summarize=True)
        assert stats["removed"] == 1
        assert stats["distilled"] == 0


class TestBuilderTelemetry:
    def test_record_builder_telemetry(self, svc: MemoryService):
        key = svc.record_builder_telemetry(
            run_id="r1",
            issue_id="SON-50",
            tool_sequence=["read_file", "write_file", "run_tests"],
            lines_scanned=100,
            source_path="/tmp/events.jsonl",
        )
        assert key == "builder-telemetry-r1"
        entry = svc.get(key)
        assert entry is not None
        assert entry.layer == MemoryLayer.EPISODIC
        assert "builder-telemetry" in entry.tags
        assert entry.metadata["tool_count"] == 3
        assert entry.metadata["tool_sequence"] == ["read_file", "write_file", "run_tests"]

    def test_record_empty_telemetry_returns_none(self, svc: MemoryService):
        key = svc.record_builder_telemetry(run_id="r2", issue_id="SON-51", tool_sequence=[])
        assert key is None


class TestAcceptanceFeedback:
    def test_record_acceptance(self, svc: MemoryService):
        key = svc.record_acceptance(issue_id="SON-60", accepted_by="chris", run_id="run-abc")
        assert key == "acceptance-SON-60"
        entry = svc.get(key)
        assert entry is not None
        assert entry.layer == MemoryLayer.EPISODIC
        assert "acceptance" in entry.tags
        assert "human-feedback" in entry.tags
        assert entry.metadata["accepted_by"] == "chris"


class TestActiveLearningSynthesis:
    def test_schedule_post_run_derivations_synthesizes_active_learning_slices(
        self, svc: MemoryService, tmp_path: Path
    ) -> None:
        svc.record_issue_completion(
            "SON-90",
            succeeded=False,
            summary="Launcher flow regressed after review route cleanup",
        )
        svc.record_acceptance(issue_id="SON-90", accepted_by="chris", run_id="run-90")
        svc.record_evolution_journal(
            evolver_name="prompt_evolver",
            stage="validate",
            summary="Prompt variant reduced over-optimistic acceptance summaries.",
            metadata={"proposal_id": "proposal-1", "accepted": True},
        )

        task_ids = svc.schedule_post_run_derivations(
            issue_id="SON-90",
            run_id="run-90",
            repo_root=tmp_path,
        )

        assert task_ids == []
        assert [item["key"] for item in svc.get_active_learning_slice("delivery")] == [
            "issue-result-SON-90"
        ]
        assert [item["key"] for item in svc.get_active_learning_slice("feedback")] == [
            "acceptance-SON-90"
        ]
        assert [item["key"] for item in svc.get_active_learning_slice("self")] == [
            "evolution-journal-prompt_evolver-validate"
        ]

        active_entry = svc.get("active-learning-self")
        assert active_entry is not None
        assert active_entry.layer == MemoryLayer.SEMANTIC
        assert active_entry.metadata["kind"] == "self"
        assert active_entry.metadata["source_count"] == 1

    def test_record_evolution_journal_is_available_as_recent_journal(
        self, svc: MemoryService
    ) -> None:
        key = svc.record_evolution_journal(
            evolver_name="intent_evolver",
            stage="promote",
            summary="Promoted classifier prompt after stable demotion reduction.",
            metadata={"proposal_id": "proposal-2", "promoted": True},
        )

        assert key == "evolution-journal-intent_evolver-promote"
        recent = svc.get_recent_evolution_journal(limit=5)
        assert recent
        assert recent[0]["evolver_name"] == "intent_evolver"
        assert recent[0]["stage"] == "promote"
        assert recent[0]["metadata"]["promoted"] is True

    def test_get_learning_memory_refs_returns_mission_scoped_memory_links(
        self, svc: MemoryService
    ) -> None:
        svc.record_acceptance_judgments(
            mission_id="mission-learning",
            round_id=1,
            judgments=[],
        )
        svc.record_evolution_journal(
            evolver_name="prompt_evolver",
            stage="promote",
            summary="Promoted transcript continuity guidance.",
            metadata={
                "proposal_id": "proposal-1",
                "mission_id": "mission-learning",
                "origin_finding_ref": "candidate:learning-1",
                "origin_review_ref": "proposal:learning-1",
            },
        )
        svc.synthesize_active_learning_slice("self", top_k=5)

        refs = svc.get_learning_memory_refs("mission-learning")

        assert refs[0]["origin_finding_ref"] == "candidate:learning-1"
        assert refs[0]["origin_review_ref"] == "proposal:learning-1"
        assert refs[0]["memory_layer"] == "semantic"
        assert refs[0]["kind"] == "self"


class TestTrendSummary:
    def test_trend_summary_with_runs(self, svc: MemoryService):
        for i in range(5):
            svc.consolidate_run(
                run_id=f"trend-r{i}",
                issue_id=f"ISS-{i}",
                succeeded=i < 3,
                failed_conditions=["ci"] if i >= 3 else [],
            )
        trend = svc.get_trend_summary(recent_days=1)
        assert trend["total_runs"] == 5
        assert trend["succeeded"] == 3
        assert trend["failed"] == 2
        assert trend["success_rate"] == 0.6
        assert "ci" in trend["top_failure_reasons"]

    def test_trend_summary_empty(self, svc: MemoryService):
        trend = svc.get_trend_summary()
        assert trend["total_runs"] == 0
        assert trend["success_rate"] == 0.0


class TestEnrichedConsolidateRun:
    def test_consolidate_with_builder_info(self, svc: MemoryService):
        key = svc.consolidate_run(
            run_id="rich-1",
            issue_id="ISS-R1",
            succeeded=True,
            builder_adapter="codex-exec",
            verification_passed=True,
            key_learnings="All tests green on first try",
        )
        assert key is not None
        entry = svc.get(key)
        assert entry is not None
        assert "codex-exec" in entry.content
        assert "Verification: passed" in entry.content
        assert entry.metadata["builder_adapter"] == "codex-exec"
        assert entry.metadata["verification_passed"] is True

    def test_consolidate_backward_compatible(self, svc: MemoryService):
        key = svc.consolidate_run(
            run_id="compat-1",
            issue_id="ISS-C1",
            succeeded=False,
            failed_conditions=["review"],
        )
        entry = svc.get(key)
        assert entry is not None
        assert "builder_adapter" not in entry.metadata
        assert "verification_passed" not in entry.metadata


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
