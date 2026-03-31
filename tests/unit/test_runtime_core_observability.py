from __future__ import annotations

from spec_orch.runtime_core.observability.models import (
    RuntimeBudgetVisibility,
    RuntimeLiveSummary,
    RuntimeProgressEvent,
    RuntimeRecap,
)
from spec_orch.runtime_core.observability.store import (
    append_progress_event,
    append_recap,
    read_live_summary,
    read_progress_events,
    read_recaps,
    write_live_summary,
)


def test_observability_store_persists_progress_and_summary(tmp_path) -> None:
    root = tmp_path / "observability"
    budget = RuntimeBudgetVisibility(
        budget_key="acceptance-graph",
        planned_steps=4,
        completed_steps=1,
        remaining_steps=3,
        loop_budget=1,
        remaining_loop_budget=1,
    )
    append_progress_event(
        root,
        RuntimeProgressEvent(
            subject_key="mission-1:round-1:acceptance-graph",
            phase="running",
            step_key="surface_scan",
            message="Completed surface scan",
            budget=budget,
            updated_at="2026-03-31T12:00:00+00:00",
        ),
    )
    write_live_summary(
        root,
        RuntimeLiveSummary(
            subject_key="mission-1:round-1:acceptance-graph",
            phase="running",
            status_reason="step_completed",
            current_step_key="surface_scan",
            budget=budget,
            updated_at="2026-03-31T12:00:00+00:00",
        ),
    )

    events = read_progress_events(root)
    summary = read_live_summary(root)

    assert len(events) == 1
    assert events[0].budget.planned_steps == 4
    assert summary is not None
    assert summary.current_step_key == "surface_scan"
    assert summary.budget.remaining_steps == 3


def test_observability_store_persists_human_readable_recaps(tmp_path) -> None:
    root = tmp_path / "observability"
    append_recap(
        root,
        RuntimeRecap(
            subject_key="mission-1:round-1:acceptance-graph",
            title="Acceptance graph completed",
            bullets=["4 steps completed", "candidate_review executed"],
            artifact_refs={"graph_run": "graph_run.json"},
            updated_at="2026-03-31T12:01:00+00:00",
        ),
    )

    recaps = read_recaps(root)

    assert len(recaps) == 1
    assert recaps[0].title == "Acceptance graph completed"
    assert recaps[0].artifact_refs["graph_run"] == "graph_run.json"
