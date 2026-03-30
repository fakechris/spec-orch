"""Decision recording seam for future supervision extraction."""

from __future__ import annotations

from collections import defaultdict

from spec_orch.decision_core.models import (
    DecisionAuthority,
    DecisionPoint,
    DecisionRecord,
)
from spec_orch.domain.models import RoundDecision

MISSION_ROUND_REVIEW_POINT = DecisionPoint(
    key="mission.round.review",
    authority=DecisionAuthority.LLM_OWNED,
    owner="round_orchestrator",
    summary="Review one mission round and decide the next orchestration action.",
)


def build_decision_record(
    point: DecisionPoint,
    *,
    record_id: str,
    selected_action: str,
    summary: str,
    rationale: str = "",
    confidence: float | None = None,
    context_artifacts: list[str] | None = None,
    blocking_questions: list[str] | None = None,
) -> DecisionRecord:
    return DecisionRecord(
        record_id=record_id,
        point_key=point.key,
        authority=point.authority,
        owner=point.owner,
        selected_action=selected_action,
        summary=summary,
        rationale=rationale,
        confidence=confidence,
        context_artifacts=list(context_artifacts or []),
        blocking_questions=list(blocking_questions or []),
    )


def build_round_review_decision_record(
    *,
    mission_id: str,
    round_id: int,
    owner: str,
    decision: RoundDecision,
    context_artifacts: list[str] | None = None,
    rationale: str = "",
) -> DecisionRecord:
    point = DecisionPoint(
        key=MISSION_ROUND_REVIEW_POINT.key,
        authority=MISSION_ROUND_REVIEW_POINT.authority,
        owner=owner,
        summary=MISSION_ROUND_REVIEW_POINT.summary,
        description=MISSION_ROUND_REVIEW_POINT.description,
    )
    return build_decision_record(
        point,
        record_id=f"{mission_id}-round-{round_id}-review",
        selected_action=decision.action.value,
        summary=decision.summary,
        rationale=rationale,
        confidence=decision.confidence,
        context_artifacts=context_artifacts,
        blocking_questions=decision.blocking_questions,
    )


def group_points_by_authority(
    points: list[DecisionPoint],
) -> dict[DecisionAuthority, list[DecisionPoint]]:
    grouped: dict[DecisionAuthority, list[DecisionPoint]] = defaultdict(list)
    for authority in DecisionAuthority:
        grouped[authority] = []
    for point in points:
        grouped[point.authority].append(point)
    return dict(grouped)


__all__ = [
    "MISSION_ROUND_REVIEW_POINT",
    "build_decision_record",
    "build_round_review_decision_record",
    "group_points_by_authority",
]
