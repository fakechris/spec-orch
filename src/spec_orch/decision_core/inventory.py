"""Canonical decision-point inventory for repo-wide routing and review seams."""

from __future__ import annotations

from spec_orch.decision_core.models import DecisionAuthority, DecisionPoint

MISSION_ROUND_REVIEW_POINT = DecisionPoint(
    key="mission.round.review",
    authority=DecisionAuthority.LLM_OWNED,
    owner="round_orchestrator",
    summary="Review one mission round and decide the next orchestration action.",
)

FLOW_ROUTER_RULE_POINT = DecisionPoint(
    key="issue.flow.route.rule",
    authority=DecisionAuthority.RULE_OWNED,
    owner="flow_router",
    summary="Resolve issue flow selection directly from static routing rules.",
)

FLOW_ROUTER_LLM_POINT = DecisionPoint(
    key="issue.flow.route.llm",
    authority=DecisionAuthority.LLM_OWNED,
    owner="flow_router",
    summary="Use the LLM router to choose an issue flow when rules are ambiguous.",
)

FLOW_ROUTER_FALLBACK_POINT = DecisionPoint(
    key="issue.flow.route.fallback",
    authority=DecisionAuthority.RULE_OWNED,
    owner="flow_router",
    summary="Fall back to the default issue flow when routing is not confident.",
)

CONDUCTOR_INTENT_CLASSIFICATION_POINT = DecisionPoint(
    key="conductor.intent.classify",
    authority=DecisionAuthority.LLM_OWNED,
    owner="conductor",
    summary="Classify conversational intent and decide whether to keep exploring or formalize.",
)

ISSUE_REVIEW_VERDICT_POINT = DecisionPoint(
    key="issue.review.verdict",
    authority=DecisionAuthority.HUMAN_REQUIRED,
    owner="review_adapter",
    summary="Record the explicit review verdict for an issue workspace.",
)


def default_decision_points() -> list[DecisionPoint]:
    return [
        MISSION_ROUND_REVIEW_POINT,
        FLOW_ROUTER_RULE_POINT,
        FLOW_ROUTER_LLM_POINT,
        FLOW_ROUTER_FALLBACK_POINT,
        CONDUCTOR_INTENT_CLASSIFICATION_POINT,
        ISSUE_REVIEW_VERDICT_POINT,
    ]


def decision_point_for_flow_router_source(source: str) -> DecisionPoint:
    if source == "rule":
        return FLOW_ROUTER_RULE_POINT
    if source == "llm":
        return FLOW_ROUTER_LLM_POINT
    return FLOW_ROUTER_FALLBACK_POINT


__all__ = [
    "CONDUCTOR_INTENT_CLASSIFICATION_POINT",
    "FLOW_ROUTER_FALLBACK_POINT",
    "FLOW_ROUTER_LLM_POINT",
    "FLOW_ROUTER_RULE_POINT",
    "ISSUE_REVIEW_VERDICT_POINT",
    "MISSION_ROUND_REVIEW_POINT",
    "decision_point_for_flow_router_source",
    "default_decision_points",
]
