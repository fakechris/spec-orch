"""Acceptance-specific workflow/disposition helpers on top of decision_core."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from spec_orch.acceptance_core.models import AcceptanceJudgment, AcceptanceWorkflowState
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


def disposition_decision(
    judgment: AcceptanceJudgment,
    *,
    disposition: AcceptanceDisposition,
    summary: str,
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
        reflection="",
    )


__all__ = [
    "AcceptanceDisposition",
    "AcceptanceDispositionDecision",
    "build_acceptance_decision_review",
    "disposition_decision",
]
