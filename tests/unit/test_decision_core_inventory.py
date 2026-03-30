from __future__ import annotations

from spec_orch.decision_core.inventory import (
    CONDUCTOR_INTENT_CLASSIFICATION_POINT,
    FLOW_ROUTER_FALLBACK_POINT,
    FLOW_ROUTER_LLM_POINT,
    FLOW_ROUTER_RULE_POINT,
    ISSUE_REVIEW_VERDICT_POINT,
    MISSION_ROUND_REVIEW_POINT,
    decision_point_for_flow_router_source,
    default_decision_points,
)
from spec_orch.decision_core.models import DecisionAuthority
from spec_orch.decision_core.records import group_points_by_authority


def test_default_decision_inventory_covers_mission_and_non_mission_paths() -> None:
    points = {point.key: point for point in default_decision_points()}

    assert MISSION_ROUND_REVIEW_POINT.key in points
    assert FLOW_ROUTER_RULE_POINT.key in points
    assert FLOW_ROUTER_LLM_POINT.key in points
    assert FLOW_ROUTER_FALLBACK_POINT.key in points
    assert CONDUCTOR_INTENT_CLASSIFICATION_POINT.key in points
    assert ISSUE_REVIEW_VERDICT_POINT.key in points

    grouped = group_points_by_authority(list(points.values()))
    assert FLOW_ROUTER_RULE_POINT in grouped[DecisionAuthority.RULE_OWNED]
    assert FLOW_ROUTER_LLM_POINT in grouped[DecisionAuthority.LLM_OWNED]
    assert CONDUCTOR_INTENT_CLASSIFICATION_POINT in grouped[DecisionAuthority.LLM_OWNED]
    assert ISSUE_REVIEW_VERDICT_POINT in grouped[DecisionAuthority.HUMAN_REQUIRED]


def test_flow_router_source_mapping_uses_canonical_decision_points() -> None:
    assert decision_point_for_flow_router_source("rule") is FLOW_ROUTER_RULE_POINT
    assert decision_point_for_flow_router_source("llm") is FLOW_ROUTER_LLM_POINT
    assert decision_point_for_flow_router_source("fallback") is FLOW_ROUTER_FALLBACK_POINT
    assert decision_point_for_flow_router_source("unknown") is FLOW_ROUTER_FALLBACK_POINT
