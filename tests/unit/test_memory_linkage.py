from __future__ import annotations

from pathlib import Path

import pytest

from spec_orch.acceptance_core.models import (
    AcceptanceJudgment,
    AcceptanceJudgmentClass,
    AcceptanceRunMode,
    AcceptanceWorkflowState,
    CandidateFinding,
)
from spec_orch.decision_core.models import DecisionAuthority, DecisionRecord, DecisionReview
from spec_orch.domain.execution_semantics import (
    ContinuityKind,
    ExecutionAttempt,
    ExecutionAttemptState,
    ExecutionOutcome,
    ExecutionOwnerKind,
    ExecutionStatus,
    ExecutionUnitKind,
)
from spec_orch.services.memory.fs_provider import FileSystemMemoryProvider
from spec_orch.services.memory.service import MemoryService


@pytest.fixture()
def svc(tmp_path: Path) -> MemoryService:
    provider = FileSystemMemoryProvider(tmp_path / "memory")
    return MemoryService(provider=provider)


def test_record_execution_outcome_persists_normalized_outcome_with_reviewed_provenance(
    svc: MemoryService,
) -> None:
    attempt = ExecutionAttempt(
        attempt_id="run-1",
        unit_kind=ExecutionUnitKind.ISSUE,
        unit_id="SON-500",
        owner_kind=ExecutionOwnerKind.RUN_CONTROLLER,
        continuity_kind=ContinuityKind.FILE_BACKED_RUN,
        continuity_id="run-1",
        workspace_root="/tmp/ws",
        attempt_state=ExecutionAttemptState.COMPLETED,
        outcome=ExecutionOutcome(
            unit_kind=ExecutionUnitKind.ISSUE,
            owner_kind=ExecutionOwnerKind.RUN_CONTROLLER,
            status=ExecutionStatus.SUCCEEDED,
            build={"adapter": "codex_exec"},
            verification={"pytest": {"exit_code": 0}},
            review={"verdict": "pass", "reviewed_by": "claude"},
            gate={"mergeable": True, "failed_conditions": []},
            artifacts={},
        ),
    )

    key = svc.record_execution_outcome(attempt=attempt)

    entry = svc.get(key)
    assert entry is not None
    assert "execution-outcome" in entry.tags
    assert entry.metadata["attempt_id"] == "run-1"
    assert entry.metadata["unit_kind"] == "issue"
    assert entry.metadata["provenance"] == "reviewed"
    assert entry.metadata["status"] == "succeeded"


def test_reviewed_decision_learning_views_split_failures_and_recipes(svc: MemoryService) -> None:
    negative_review = DecisionReview(
        review_id="review-1",
        record_id="record-1",
        reviewer_kind="human",
        verdict="revision_requested",
        summary="Need stronger evidence before rollout.",
        recommended_authority=DecisionAuthority.HUMAN_REQUIRED,
        escalate_to_human=True,
    )
    positive_review = DecisionReview(
        review_id="review-2",
        record_id="record-2",
        reviewer_kind="human",
        verdict="approval_granted",
        summary="Evidence is sufficient for rollout.",
        recommended_authority=DecisionAuthority.HUMAN_REQUIRED,
        escalate_to_human=False,
    )

    svc.record_decision_review(
        review=negative_review,
        mission_id="mission-1",
        round_id=1,
        point_key="mission.round.review",
        owner="litellm_supervisor_adapter",
        selected_action="ask_human",
    )
    svc.record_decision_review(
        review=positive_review,
        mission_id="mission-1",
        round_id=2,
        point_key="mission.round.review",
        owner="litellm_supervisor_adapter",
        selected_action="continue",
    )

    failures = svc.get_reviewed_decision_failures()
    recipes = svc.get_reviewed_decision_recipes()

    assert [item["record_id"] for item in failures] == ["record-1"]
    assert failures[0]["provenance"] == "reviewed"
    assert [item["record_id"] for item in recipes] == ["record-2"]
    assert recipes[0]["verdict"] == "approval_granted"


def test_reviewed_acceptance_findings_filter_out_unreviewed_candidates(svc: MemoryService) -> None:
    queued = AcceptanceJudgment(
        judgment_id="proposal:queued",
        judgment_class=AcceptanceJudgmentClass.CANDIDATE_FINDING,
        run_mode=AcceptanceRunMode.EXPLORE,
        workflow_state=AcceptanceWorkflowState.QUEUED,
        summary="Possible UX confusion in launcher navigation.",
        candidate=CandidateFinding(
            claim="Possible UX confusion in launcher navigation.",
            finding_id="candidate:queued",
            graph_profile="exploratory_probe_graph",
            origin_step="launcher_scan",
            run_mode="explore",
        ),
    )
    promoted = AcceptanceJudgment(
        judgment_id="proposal:promoted",
        judgment_class=AcceptanceJudgmentClass.CANDIDATE_FINDING,
        run_mode=AcceptanceRunMode.EXPLORE,
        workflow_state=AcceptanceWorkflowState.PROMOTED,
        summary="Confirmed regression in dashboard transcript route.",
        candidate=CandidateFinding(
            claim="Confirmed regression in dashboard transcript route.",
            finding_id="candidate:promoted",
            route="/?mission=mission-acceptance&mode=missions&tab=transcript",
            baseline_ref="fixture:dashboard-transcript-regression",
            origin_step="transcript_empty_state_review",
            graph_profile="tuned_dashboard_compare_graph",
            run_mode="explore",
            compare_overlay=True,
            promotion_test="rerun transcript path with retry artifact visible",
            dedupe_key="dashboard:transcript_empty_state_retry_cause",
        ),
    )

    svc.record_acceptance_judgments(
        mission_id="mission-acceptance",
        round_id=4,
        judgments=[queued, promoted],
    )

    findings = svc.get_reviewed_acceptance_findings()

    assert [item["judgment_id"] for item in findings] == ["proposal:promoted"]
    assert findings[0]["workflow_state"] == "promoted"
    assert findings[0]["provenance"] == "reviewed"
    assert findings[0]["finding_id"] == "candidate:promoted"
    assert findings[0]["route"] == "/?mission=mission-acceptance&mode=missions&tab=transcript"
    assert findings[0]["baseline_ref"] == "fixture:dashboard-transcript-regression"
    assert findings[0]["origin_step"] == "transcript_empty_state_review"
    assert findings[0]["graph_profile"] == "tuned_dashboard_compare_graph"
    assert findings[0]["run_mode"] == "explore"
    assert findings[0]["compare_overlay"] is True
    assert findings[0]["promotion_test"] == "rerun transcript path with retry artifact visible"
    assert findings[0]["dedupe_key"] == "dashboard:transcript_empty_state_retry_cause"


def test_recall_latest_with_provenance_prefers_newest_reviewed_entries(
    svc: MemoryService,
) -> None:
    record = DecisionRecord(
        record_id="record-unreviewed",
        point_key="mission.round.review",
        authority=DecisionAuthority.LLM_OWNED,
        owner="litellm_supervisor_adapter",
        selected_action="continue",
        summary="Continue after successful round.",
    )
    review = DecisionReview(
        review_id="review-recent",
        record_id="record-reviewed",
        reviewer_kind="human",
        verdict="approval_granted",
        summary="Approved after transcript and visual review.",
        recommended_authority=DecisionAuthority.HUMAN_REQUIRED,
    )

    svc.record_decision_record(record=record, mission_id="mission-2", round_id=1)
    svc.record_decision_review(
        review=review,
        mission_id="mission-2",
        round_id=2,
        point_key="mission.round.review",
        owner="litellm_supervisor_adapter",
        selected_action="continue",
    )

    recall = svc.recall_latest_with_provenance(entity_scope="mission", entity_id="mission-2")

    assert [item["key"] for item in recall[:2]] == [
        "decision-review-record-reviewed-review-recent",
        "decision-record-record-unreviewed",
    ]
    assert recall[0]["provenance"] == "reviewed"
    assert recall[1]["provenance"] == "unreviewed"
