from __future__ import annotations

from spec_orch.domain.context import ContextBundle, ExecutionContext, LearningContext, TaskContext
from spec_orch.domain.models import GateVerdict, Issue, VerificationDetail, VerificationSummary
from spec_orch.services.evolution.signal_bridge import build_evolution_signal_snapshot


def _issue() -> Issue:
    return Issue(
        issue_id="SON-600",
        title="Epic 6 signal bridge",
        summary="Normalize evolution evidence",
        builder_prompt="Tighten evolution signal provenance.",
        acceptance_criteria=["journal includes provenance"],
    )


def test_build_evolution_signal_snapshot_counts_reviewed_origins() -> None:
    ctx = ContextBundle(
        task=TaskContext(issue=_issue()),
        execution=ExecutionContext(
            verification_results=VerificationSummary(
                details={
                    "pytest": VerificationDetail(
                        command=["pytest"],
                        exit_code=1,
                        stdout="",
                        stderr="failing",
                    )
                },
            ),
            gate_report=GateVerdict(mergeable=False, failed_conditions=["verification"]),
        ),
        learning=LearningContext(
            reviewed_decision_failures=[{"record_id": "dr-fail-1", "verdict": "blocked"}],
            reviewed_decision_recipes=[{"record_id": "dr-ok-1", "verdict": "continue"}],
            reviewed_acceptance_findings=[
                {"finding_id": "af-1", "workflow_state": "reviewed", "graph_profile": "guided"}
            ],
            recent_evolution_journal=[{"evolver_name": "prompt_evolver", "stage": "promote"}],
        ),
    )

    snapshot = build_evolution_signal_snapshot(ctx)

    assert snapshot.reviewed_decision_failure_count == 1
    assert snapshot.reviewed_decision_recipe_count == 1
    assert snapshot.reviewed_acceptance_finding_count == 1
    assert snapshot.recent_evolution_journal_count == 1
    assert snapshot.reviewed_evidence_count == 3
    assert snapshot.execution_signal_count == 2
    assert snapshot.signal_origins == [
        "execution",
        "decision_review",
        "acceptance_review",
        "evolution_journal",
    ]
