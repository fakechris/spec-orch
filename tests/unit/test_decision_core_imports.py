from __future__ import annotations


def test_decision_core_package_exposes_skeleton_modules() -> None:
    from spec_orch import decision_core

    assert decision_core.__all__ == [
        "interventions",
        "models",
        "records",
        "review_queue",
    ]


def test_decision_core_support_modules_import_cleanly() -> None:
    from spec_orch.decision_core import interventions, models, records, review_queue

    assert interventions.__all__ == [
        "Intervention",
        "InterventionStatus",
        "build_intervention_from_record",
    ]
    assert models.__all__ == [
        "DecisionAuthority",
        "DecisionPoint",
        "DecisionRecord",
    ]
    assert records.__all__ == [
        "MISSION_ROUND_REVIEW_POINT",
        "build_decision_record",
        "build_round_review_decision_record",
        "group_points_by_authority",
    ]
    assert review_queue.__all__ == [
        "append_intervention",
        "append_intervention_response",
        "decision_record_path",
        "intervention_queue_path",
        "intervention_response_history_path",
        "load_intervention_response_history",
        "load_latest_intervention",
        "write_round_decision_record",
    ]
