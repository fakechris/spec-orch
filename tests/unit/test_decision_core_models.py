from __future__ import annotations

from spec_orch.decision_core.interventions import InterventionStatus
from spec_orch.decision_core.models import (
    DecisionAuthority,
    DecisionPoint,
    DecisionRecord,
    DecisionReview,
)


def test_decision_authority_values_match_program_language() -> None:
    assert DecisionAuthority.RULE_OWNED.value == "rule_owned"
    assert DecisionAuthority.LLM_OWNED.value == "llm_owned"
    assert DecisionAuthority.HUMAN_REQUIRED.value == "human_required"


def test_decision_point_and_record_capture_minimal_decision_shape() -> None:
    point = DecisionPoint(
        key="mission.round.review",
        authority=DecisionAuthority.LLM_OWNED,
        owner="round_orchestrator",
        summary="Review round evidence and decide the next mission action.",
    )
    record = DecisionRecord(
        record_id="dec-1",
        point_key=point.key,
        authority=point.authority,
        owner=point.owner,
        selected_action="ask_human",
        summary="Need human approval before rollout.",
        confidence=0.74,
        blocking_questions=["Approve rollout?"],
    )

    assert record.point_key == "mission.round.review"
    assert record.authority is DecisionAuthority.LLM_OWNED
    assert record.selected_action == "ask_human"
    assert record.blocking_questions == ["Approve rollout?"]


def test_intervention_status_defaults_to_open() -> None:
    assert InterventionStatus.OPEN.value == "open"


def test_decision_review_captures_review_and_escalation_shape() -> None:
    review = DecisionReview(
        review_id="rev-1",
        record_id="dec-1",
        reviewer_kind="human",
        verdict="approval_granted",
        summary="Approved after transcript review.",
        recommended_authority=DecisionAuthority.HUMAN_REQUIRED,
        escalate_to_human=False,
        reflection="Human operator confirmed rollout.",
    )

    assert review.record_id == "dec-1"
    assert review.reviewer_kind == "human"
    assert review.recommended_authority is DecisionAuthority.HUMAN_REQUIRED
    assert review.to_dict()["recommended_authority"] == "human_required"
