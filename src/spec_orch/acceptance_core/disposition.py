"""Acceptance-specific workflow/disposition helpers on top of decision_core."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from spec_orch.acceptance_core.models import (
    AcceptanceJudgment,
    AcceptanceWorkflowState,
    apply_candidate_governance,
)
from spec_orch.decision_core.models import DecisionReview


class AcceptanceDisposition(StrEnum):
    REVIEW = "review"
    PROMOTE = "promote"
    DISMISS = "dismiss"
    ARCHIVE = "archive"


@dataclass(slots=True)
class AcceptanceDispositionDecision:
    judgment_id: str
    disposition: AcceptanceDisposition
    workflow_state: AcceptanceWorkflowState
    summary: str
    intervention_required: bool = False
    reviewer_identity: str = ""
    review_note: str = ""
    superseded_by: str = ""


def disposition_decision(
    judgment: AcceptanceJudgment,
    *,
    disposition: AcceptanceDisposition,
    summary: str,
    reviewer_identity: str = "",
    review_note: str = "",
    superseded_by: str = "",
) -> AcceptanceDispositionDecision:
    state_map = {
        AcceptanceDisposition.REVIEW: AcceptanceWorkflowState.REVIEWED,
        AcceptanceDisposition.PROMOTE: AcceptanceWorkflowState.PROMOTED,
        AcceptanceDisposition.DISMISS: AcceptanceWorkflowState.DISMISSED,
        AcceptanceDisposition.ARCHIVE: AcceptanceWorkflowState.ARCHIVED,
    }
    workflow_state = state_map[disposition]
    intervention_required = (
        disposition is AcceptanceDisposition.REVIEW
        and judgment.workflow_state is AcceptanceWorkflowState.QUEUED
    )
    return AcceptanceDispositionDecision(
        judgment_id=judgment.judgment_id,
        disposition=disposition,
        workflow_state=workflow_state,
        summary=summary,
        intervention_required=intervention_required,
        reviewer_identity=reviewer_identity,
        review_note=review_note,
        superseded_by=superseded_by,
    )


def build_acceptance_decision_review(
    decision: AcceptanceDispositionDecision,
    *,
    record_id: str,
    reviewer_kind: str,
) -> DecisionReview:
    verdict_map = {
        AcceptanceDisposition.REVIEW: "acceptance_candidate_reviewed",
        AcceptanceDisposition.PROMOTE: "acceptance_candidate_promoted",
        AcceptanceDisposition.DISMISS: "acceptance_candidate_dismissed",
        AcceptanceDisposition.ARCHIVE: "acceptance_observation_archived",
    }
    return DecisionReview(
        review_id=f"{record_id}:{decision.disposition.value}",
        record_id=record_id,
        reviewer_kind=reviewer_kind,
        verdict=verdict_map[decision.disposition],
        summary=decision.summary,
        reflection=decision.review_note,
    )


def apply_disposition_to_judgment(
    judgment: AcceptanceJudgment,
    decision: AcceptanceDispositionDecision,
) -> AcceptanceJudgment:
    updated = replace(judgment, workflow_state=decision.workflow_state)
    if updated.candidate is None:
        return updated
    dismissal_reason = (
        decision.summary if decision.disposition is AcceptanceDisposition.DISMISS else ""
    )
    updated_candidate = apply_candidate_governance(
        updated.candidate,
        reviewer_identity=decision.reviewer_identity,
        review_note=decision.review_note,
        dismissal_reason=dismissal_reason,
        superseded_by=decision.superseded_by,
    )
    return replace(updated, candidate=updated_candidate)


__all__ = [
    "AcceptanceDisposition",
    "AcceptanceDispositionDecision",
    "apply_disposition_to_judgment",
    "build_acceptance_decision_review",
    "disposition_decision",
]
