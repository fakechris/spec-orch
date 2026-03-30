from __future__ import annotations

from pathlib import Path

from spec_orch.runtime_core.paths import (
    normalized_issue_conclusion_path,
    normalized_issue_live_path,
    normalized_issue_manifest_path,
    normalized_issue_root,
    normalized_mission_root,
    normalized_round_decision_path,
    normalized_round_root,
    normalized_round_summary_path,
    normalized_worker_builder_report_path,
)


def test_issue_paths_use_run_artifact_directory() -> None:
    workspace = Path("/repo/.spec_orch_runs/run-123")

    assert normalized_issue_root(workspace) == workspace / "run_artifact"
    assert normalized_issue_live_path(workspace) == workspace / "run_artifact" / "live.json"
    assert (
        normalized_issue_conclusion_path(workspace)
        == workspace / "run_artifact" / "conclusion.json"
    )
    assert normalized_issue_manifest_path(workspace) == workspace / "run_artifact" / "manifest.json"


def test_mission_and_round_paths_preserve_existing_layout() -> None:
    mission_root = Path("/repo/docs/specs/mission-1")
    round_dir = mission_root / "rounds" / "round-02"
    worker_dir = mission_root / "workers" / "pkt-1"

    assert normalized_mission_root(mission_root) == mission_root
    assert normalized_round_root(round_dir) == round_dir
    assert normalized_round_summary_path(round_dir) == round_dir / "round_summary.json"
    assert normalized_round_decision_path(round_dir) == round_dir / "round_decision.json"
    assert normalized_worker_builder_report_path(worker_dir) == worker_dir / "builder_report.json"
