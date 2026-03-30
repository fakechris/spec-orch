from __future__ import annotations


def test_runtime_core_package_exposes_skeleton_modules() -> None:
    from spec_orch import runtime_core

    assert runtime_core.__all__ == [
        "adapters",
        "models",
        "paths",
        "readers",
        "writers",
    ]


def test_runtime_core_models_reexport_execution_semantics() -> None:
    from spec_orch.runtime_core import models

    assert models.ExecutionAttempt.__name__ == "ExecutionAttempt"
    assert models.ExecutionOutcome.__name__ == "ExecutionOutcome"
    assert models.ExecutionUnitKind.ISSUE.value == "issue"


def test_runtime_core_support_modules_import_cleanly() -> None:
    from spec_orch.runtime_core import adapters, paths, readers, writers

    assert adapters.__all__ == [
        "build_packet_attempt_payload",
        "write_issue_attempt_payloads",
        "write_round_cycle_payloads",
        "write_worker_attempt_payloads",
    ]
    assert readers.__all__ == [
        "read_issue_artifacts",
        "read_issue_execution_attempt",
        "read_round_supervision_cycle",
        "read_worker_execution_attempt",
    ]
    assert writers.__all__ == [
        "write_issue_execution_payloads",
        "write_round_supervision_payloads",
        "write_worker_execution_payloads",
    ]
    assert paths.__all__ == [
        "normalized_issue_conclusion_path",
        "normalized_issue_live_path",
        "normalized_issue_manifest_path",
        "normalized_issue_root",
        "normalized_mission_root",
        "normalized_round_decision_path",
        "normalized_round_root",
        "normalized_round_summary_path",
        "normalized_worker_builder_report_path",
    ]
