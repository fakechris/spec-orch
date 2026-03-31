from __future__ import annotations

from pathlib import Path

from spec_orch.runtime_core.compaction.models import (
    CompactionBoundary,
    CompactionRestoreBundle,
    CompactionTelemetryEvent,
)
from spec_orch.runtime_core.compaction.runner import (
    evaluate_compaction_trigger,
    run_memory_compaction,
)
from spec_orch.runtime_core.compaction.store import (
    read_compaction_boundaries,
    read_compaction_events,
    read_last_compaction,
)


class _FakeMemoryService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def compact(
        self, *, max_age_days: int, summarize: bool, planner_config: dict | None
    ) -> dict[str, int]:
        self.calls.append(
            {
                "max_age_days": max_age_days,
                "summarize": summarize,
                "planner_config": planner_config,
            }
        )
        return {"removed": 2, "retained": 5, "distilled": 1}


def test_evaluate_compaction_trigger_uses_explicit_threshold() -> None:
    assert evaluate_compaction_trigger(observed_count=3, threshold=10).trigger is False
    decision = evaluate_compaction_trigger(observed_count=10, threshold=10)
    assert decision.trigger is True
    assert decision.reason == "run_threshold_reached"


def test_run_memory_compaction_writes_boundary_and_telemetry(tmp_path: Path) -> None:
    memory = _FakeMemoryService()
    decision = evaluate_compaction_trigger(observed_count=10, threshold=10)
    restore_bundle = CompactionRestoreBundle(
        restored_state={
            "issue_id": "SPC-1",
            "run_id": "run-1",
        },
        attachment_refs={
            "workspace": "workspace/SPC-1",
        },
        discovered_tools=["acpx.session.ensure"],
    )

    result = run_memory_compaction(
        root=tmp_path,
        memory_service=memory,
        trigger=decision,
        restore_bundle=restore_bundle,
        planner_config={"model": "test-model"},
    )

    assert result["stats"] == {"removed": 2, "retained": 5, "distilled": 1}
    assert memory.calls == [
        {
            "max_age_days": 30,
            "summarize": True,
            "planner_config": {"model": "test-model"},
        }
    ]
    events = read_compaction_events(tmp_path)
    assert [event.phase for event in events] == ["started", "completed"]
    boundaries = read_compaction_boundaries(tmp_path)
    assert len(boundaries) == 1
    assert boundaries[0].trigger_reason == "run_threshold_reached"
    assert boundaries[0].restore_bundle["restored_state"]["issue_id"] == "SPC-1"
    last = read_last_compaction(tmp_path)
    assert last is not None
    assert last["stats"]["distilled"] == 1


def test_compaction_models_coerce_malformed_nested_payloads() -> None:
    boundary = CompactionBoundary.from_dict(
        {
            "boundary_id": "boundary-1",
            "trigger_reason": "run_threshold_reached",
            "restore_bundle": "not-a-mapping",
        }
    )
    event = CompactionTelemetryEvent.from_dict(
        {
            "phase": "completed",
            "reason": "run_threshold_reached",
            "details": "not-a-mapping",
        }
    )

    assert boundary.restore_bundle == {}
    assert event.details == {}
