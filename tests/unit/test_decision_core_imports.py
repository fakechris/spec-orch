from __future__ import annotations


def test_decision_core_package_exposes_skeleton_modules() -> None:
    from spec_orch import decision_core

    assert decision_core.__all__ == [
        "interventions",
        "inventory",
        "models",
        "records",
        "review_queue",
    ]


def test_decision_core_support_modules_import_cleanly() -> None:
    from spec_orch.decision_core import interventions, inventory, models, records, review_queue

    assert hasattr(models, "DecisionRecord")
    assert inventory.__all__ == [
        "CONDUCTOR_INTENT_CLASSIFICATION_POINT",
        "FLOW_ROUTER_FALLBACK_POINT",
        "FLOW_ROUTER_LLM_POINT",
        "FLOW_ROUTER_RULE_POINT",
        "ISSUE_REVIEW_VERDICT_POINT",
        "MISSION_ROUND_REVIEW_POINT",
        "decision_point_for_flow_router_source",
        "default_decision_points",
    ]
    assert interventions.__all__ == [
        "Intervention",
        "InterventionStatus",
        "build_intervention_from_record",
    ]
    assert models.__all__ == [
        "DecisionAuthority",
        "DecisionPoint",
        "DecisionRecord",
        "DecisionReview",
    ]
    assert records.__all__ == [
        "MISSION_ROUND_REVIEW_POINT",
        "build_decision_record",
        "build_round_review_decision_record",
        "group_points_by_authority",
    ]
    assert review_queue.__all__ == [
        "append_decision_review",
        "append_intervention",
        "append_intervention_response",
        "decision_record_path",
        "decision_review_history_path",
        "intervention_queue_path",
        "intervention_response_history_path",
        "load_decision_reviews",
        "load_intervention_response_history",
        "load_latest_intervention",
        "write_round_decision_record",
    ]
