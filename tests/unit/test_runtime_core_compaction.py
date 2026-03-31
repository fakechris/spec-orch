from __future__ import annotations

from pathlib import Path

from spec_orch.runtime_core.compaction.models import (
    CompactionBoundary,
    CompactionRestoreBundle,
    CompactionTelemetryEvent,
)
from spec_orch.runtime_core.compaction.restore import (
    build_restore_bundle,
    restore_bundle_from_boundary,
)
from spec_orch.runtime_core.compaction.runner import (
    evaluate_compaction_input,
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
        self.failures: list[str] = []

    def compact(
        self, *, max_age_days: int, summarize: bool, planner_config: dict | None
    ) -> dict[str, int]:
        if self.failures:
            raise RuntimeError(self.failures.pop(0))
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


def test_evaluate_compaction_input_uses_budget_pressure() -> None:
    decision = evaluate_compaction_input(
        effective_context_window=1000,
        reserved_output_budget=200,
        transcript_size=850,
        recent_growth=20,
    )
    assert decision.trigger is True
    assert decision.reason == "budget_pressure"
    assert decision.effective_budget == 800


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
    assert last["guard_state"] == "released"


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


def test_compaction_restore_bundle_round_trips_boundary() -> None:
    restore = build_restore_bundle(
        restored_state={"issue_id": "SPC-1"},
        attachment_refs={"workspace": "workspace/SPC-1"},
        discovered_tools=["acpx.session.ensure"],
    )
    boundary = CompactionBoundary(
        boundary_id="boundary-1",
        trigger_reason="budget_pressure",
        restore_bundle=restore.to_dict(),
    )

    restored = restore_bundle_from_boundary(boundary)

    assert restored.restored_state["issue_id"] == "SPC-1"
    assert restored.discovered_tools == ["acpx.session.ensure"]


def test_run_memory_compaction_retries_prompt_too_long_with_fallback(tmp_path: Path) -> None:
    memory = _FakeMemoryService()
    memory.failures = ["prompt too long"]
    decision = evaluate_compaction_trigger(observed_count=10, threshold=10)

    result = run_memory_compaction(
        root=tmp_path,
        memory_service=memory,
        trigger=decision,
        restore_bundle=CompactionRestoreBundle(),
        planner_config={"model": "test-model"},
    )

    assert result["retries_used"] == 1
    assert result["fallback_used"] == "smaller_source_slice"
    assert memory.calls[-1]["summarize"] is False


def test_run_memory_compaction_emits_failure_payload(tmp_path: Path) -> None:
    memory = _FakeMemoryService()
    memory.failures = ["hard failure", "hard failure"]
    decision = evaluate_compaction_trigger(observed_count=10, threshold=10)

    try:
        run_memory_compaction(
            root=tmp_path,
            memory_service=memory,
            trigger=decision,
            restore_bundle=CompactionRestoreBundle(),
        )
    except RuntimeError as exc:
        assert "hard failure" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")

    events = read_compaction_events(tmp_path)
    assert [event.phase for event in events] == ["started", "failed"]
    last = read_last_compaction(tmp_path)
    assert last is not None
    assert last["guard_state"] == "failed"


def test_run_memory_compaction_recursion_guard_blocks_reentry(tmp_path: Path) -> None:
    memory = _FakeMemoryService()
    decision = evaluate_compaction_trigger(observed_count=10, threshold=10)
    guard = tmp_path / "compaction.lock"
    guard.write_text("busy", encoding="utf-8")

    try:
        run_memory_compaction(
            root=tmp_path,
            memory_service=memory,
            trigger=decision,
            restore_bundle=CompactionRestoreBundle(),
        )
    except RuntimeError as exc:
        assert "recursion guard" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")
