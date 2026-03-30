from __future__ import annotations

from spec_orch.decision_core.interventions import build_intervention_from_record
from spec_orch.decision_core.models import (
    DecisionAuthority,
    DecisionPoint,
)
from spec_orch.decision_core.records import (
    MISSION_ROUND_REVIEW_POINT,
    build_decision_record,
    build_round_review_decision_record,
    group_points_by_authority,
)


def test_group_points_by_authority_creates_inventory_buckets() -> None:
    points = [
        DecisionPoint(
            key="flow.classify_intent",
            authority=DecisionAuthority.RULE_OWNED,
            owner="conductor",
            summary="Route inbound message to the right flow.",
        ),
        DecisionPoint(
            key="mission.round.review",
            authority=DecisionAuthority.LLM_OWNED,
            owner="round_orchestrator",
            summary="Review one mission round.",
        ),
        DecisionPoint(
            key="mission.round.approval",
            authority=DecisionAuthority.HUMAN_REQUIRED,
            owner="dashboard.approvals",
            summary="Resolve operator approval requests.",
        ),
    ]

    inventory = group_points_by_authority(points)

    assert [point.key for point in inventory[DecisionAuthority.RULE_OWNED]] == [
        "flow.classify_intent"
    ]
    assert [point.key for point in inventory[DecisionAuthority.LLM_OWNED]] == [
        "mission.round.review"
    ]
    assert [point.key for point in inventory[DecisionAuthority.HUMAN_REQUIRED]] == [
        "mission.round.approval"
    ]


def test_build_decision_record_and_intervention_from_point() -> None:
    point = DecisionPoint(
        key="mission.round.review",
        authority=DecisionAuthority.LLM_OWNED,
        owner="round_orchestrator",
        summary="Review one mission round.",
    )

    record = build_decision_record(
        point,
        record_id="dec-1",
        selected_action="ask_human",
        summary="Need human approval before rollout.",
        confidence=0.74,
        blocking_questions=["Approve rollout?"],
    )
    intervention = build_intervention_from_record(record, intervention_id="int-1")

    assert record.owner == "round_orchestrator"
    assert record.authority is DecisionAuthority.LLM_OWNED
    assert intervention.point_key == point.key
    assert intervention.questions == ["Approve rollout?"]


def test_build_round_review_decision_record_uses_canonical_point_and_shape() -> None:
    from spec_orch.domain.models import RoundAction, RoundDecision

    record = build_round_review_decision_record(
        mission_id="mission-1",
        round_id=2,
        owner="litellm_supervisor_adapter",
        decision=RoundDecision(
            action=RoundAction.ASK_HUMAN,
            summary="Need approval before rollout.",
            confidence=0.73,
            blocking_questions=["Approve rollout?"],
        ),
        context_artifacts=[
            "docs/specs/mission-1/rounds/round-02/supervisor_review.md",
            "docs/specs/mission-1/rounds/round-02/round_decision.json",
        ],
    )

    assert MISSION_ROUND_REVIEW_POINT.key == "mission.round.review"
    assert record.record_id == "mission-1-round-2-review"
    assert record.point_key == "mission.round.review"
    assert record.owner == "litellm_supervisor_adapter"
    assert record.selected_action == "ask_human"
    assert record.blocking_questions == ["Approve rollout?"]
