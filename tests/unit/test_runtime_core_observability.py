from __future__ import annotations

import json

from spec_orch.runtime_core.observability.models import (
    RuntimeBatchSummary,
    RuntimeBudgetVisibility,
    RuntimeLiveSummary,
    RuntimeProgressEvent,
    RuntimeRecap,
    RuntimeStepSummary,
)
from spec_orch.runtime_core.observability.progress import (
    build_batch_summary,
    build_step_summary,
    derive_stall_signal,
)
from spec_orch.runtime_core.observability.store import (
    append_batch_summary,
    append_progress_event,
    append_recap,
    append_step_summary,
    read_batch_summaries,
    read_live_summary,
    read_progress_events,
    read_recaps,
    read_step_summaries,
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


def test_observability_store_persists_step_and_batch_summaries(tmp_path) -> None:
    root = tmp_path / "observability"
    append_step_summary(
        root,
        RuntimeStepSummary(
            subject_key="mission-1:round-1:acceptance-graph",
            step_key="guided_probe",
            summary="Step captured two candidate observations",
            artifact_refs={"step_artifact": "steps/02-guided_probe.json"},
            updated_at="2026-03-31T12:01:00+00:00",
        ),
    )
    append_batch_summary(
        root,
        RuntimeBatchSummary(
            subject_key="mission-1:round-1:acceptance-graph",
            batch_key="guided_probe_batch",
            steps=["surface_scan", "guided_probe"],
            summary="Discovery batch completed",
            artifact_refs={"graph_run": "graph_run.json"},
            updated_at="2026-03-31T12:02:00+00:00",
        ),
    )

    step_summaries = read_step_summaries(root)
    batch_summaries = read_batch_summaries(root)

    assert len(step_summaries) == 1
    assert step_summaries[0].step_key == "guided_probe"
    assert step_summaries[0].artifact_refs["step_artifact"].endswith("guided_probe.json")
    assert len(batch_summaries) == 1
    assert batch_summaries[0].steps == ["surface_scan", "guided_probe"]
    assert batch_summaries[0].summary == "Discovery batch completed"


def test_observability_helpers_build_summaries_and_stall_signals() -> None:
    stall = derive_stall_signal(repeated_steps=3, idle_seconds=10, low_yield=True)
    step_summary = build_step_summary(
        subject_key="mission-1:round-1:acceptance-graph",
        step_key="candidate_review",
        summary="Reviewed one promoted candidate",
        artifact_refs={"review": "decision_review.json"},
        updated_at="2026-03-31T12:03:00+00:00",
    )
    batch_summary = build_batch_summary(
        subject_key="mission-1:round-1:acceptance-graph",
        batch_key="review_batch",
        steps=["candidate_review", "summarize_judgment"],
        summary="Review batch completed cleanly",
        artifact_refs={"graph_run": "graph_run.json"},
        updated_at="2026-03-31T12:04:00+00:00",
    )

    assert stall.stalled is True
    assert stall.reason == "repeated_step_loop"
    assert stall.diminishing_returns is True
    assert step_summary.artifact_refs["review"] == "decision_review.json"
    assert batch_summary.steps == ["candidate_review", "summarize_judgment"]


def test_observability_store_sanitizes_absolute_paths(tmp_path) -> None:
    repo_root = tmp_path / "repo"
    observability_root = repo_root / "docs/specs/mission-1/operator/observability/round-01"
    repo_root.joinpath(".git").mkdir(parents=True)

    append_step_summary(
        observability_root,
        RuntimeStepSummary(
            subject_key="mission-1:round-1:acceptance-graph",
            step_key="guided_probe",
            summary=(
                "See "
                f"{repo_root / 'rounds/round-01/steps/02-guided_probe.json'} "
                "and /Users/chris/workspace/spec-orch/.venv-py313/bin/python"
            ),
            artifact_refs={
                "step_artifact": str(repo_root / "rounds/round-01/steps/02-guided_probe.json"),
                "external": "/Users/chris/tmp/raw-proof.json",
            },
            updated_at="2026-03-31T12:01:00+00:00",
        ),
    )
    write_live_summary(
        observability_root,
        RuntimeLiveSummary(
            subject_key="mission-1:round-1:acceptance-graph",
            phase="running",
            status_reason="step_completed",
            current_step_key="guided_probe",
            budget=RuntimeBudgetVisibility(
                budget_key="acceptance-graph",
                planned_steps=4,
                completed_steps=1,
                remaining_steps=3,
            ),
            artifact_refs={
                "graph_run": str(repo_root / "rounds/round-01/graph_run.json"),
            },
            updated_at="2026-03-31T12:00:00+00:00",
        ),
    )

    step_summary_path = observability_root / "step_summaries.jsonl"
    live_summary_path = observability_root / "live_summary.json"

    step_payload = json.loads(step_summary_path.read_text(encoding="utf-8").splitlines()[0])
    live_payload = json.loads(live_summary_path.read_text(encoding="utf-8"))

    assert "/Users/chris/" not in json.dumps(step_payload)
    assert (
        step_payload["artifact_refs"]["step_artifact"]
        == "rounds/round-01/steps/02-guided_probe.json"
    )
    assert step_payload["artifact_refs"]["external"] == "<external-path>/tmp/raw-proof.json"
    assert step_payload["summary"].startswith("See rounds/round-01/steps/02-guided_probe.json")
    assert "<external-path>/.venv-py313/bin/python" in step_payload["summary"]
    assert live_payload["artifact_refs"]["graph_run"] == "rounds/round-01/graph_run.json"
