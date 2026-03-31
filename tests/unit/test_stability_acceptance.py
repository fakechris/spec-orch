from __future__ import annotations

import json
from pathlib import Path


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_write_issue_start_acceptance_report_materializes_normalized_attempt(
    tmp_path: Path,
) -> None:
    from spec_orch.services.stability_acceptance import write_issue_start_acceptance_report

    workspace = tmp_path / ".spec_orch_runs" / "SPC-1"
    _write_json(
        workspace / "report.json",
        {
            "issue_id": "SPC-1",
            "title": "Smoke issue",
            "state": "gate_evaluated",
            "mergeable": True,
            "failed_conditions": [],
        },
    )
    _write_json(
        workspace / "run_artifact" / "live.json",
        {
            "run_id": "run-spc-1",
            "issue_id": "SPC-1",
            "builder": {"adapter": "codex_exec", "succeeded": True},
            "verification": {"passed": 3, "total": 3},
            "review": {"verdict": "pass"},
        },
    )
    _write_json(
        workspace / "run_artifact" / "conclusion.json",
        {
            "run_id": "run-spc-1",
            "issue_id": "SPC-1",
            "state": "gate_evaluated",
            "verdict": "pass",
            "mergeable": True,
            "failed_conditions": [],
        },
    )
    _write_json(
        workspace / "run_artifact" / "manifest.json",
        {
            "run_id": "run-spc-1",
            "artifacts": {
                "report": str(workspace / "report.json"),
                "builder_report": str(workspace / "builder_report.json"),
            },
        },
    )

    report = write_issue_start_acceptance_report(
        repo_root=tmp_path,
        issue_id="SPC-1",
        fixture_issue_id="SPC-1",
        preflight_report={"summary": {"pass": 4, "fail": 0, "warn": 0}},
    )

    report_json = json.loads(Path(report["json_path"]).read_text(encoding="utf-8"))
    assert report_json["status"] == "pass"
    assert report_json["issue_id"] == "SPC-1"
    assert report_json["preflight"]["summary"]["fail"] == 0
    assert report_json["attempt"]["attempt_id"] == "run-spc-1"
    assert report_json["attempt"]["outcome"]["status"] == "succeeded"
    assert report_json["attempt"]["outcome"]["artifacts"]["manifest"]["path"].endswith(
        "run_artifact/manifest.json"
    )


def test_write_mission_start_acceptance_report_preserves_fresh_report(
    tmp_path: Path,
) -> None:
    from spec_orch.services.stability_acceptance import write_mission_start_acceptance_report

    round_dir = tmp_path / "docs" / "specs" / "fresh-acpx-1" / "rounds" / "round-01"
    round_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        round_dir / "fresh_acpx_mission_e2e_report.json",
        {
            "mission_id": "fresh-acpx-1",
            "variant": "default",
            "fresh_execution": {"fresh_round_path": str(round_dir)},
            "workflow_replay": {"proof_type": "workflow_replay"},
            "acceptance_review": {"status": "pass", "coverage_status": "complete"},
        },
    )

    report = write_mission_start_acceptance_report(
        repo_root=tmp_path,
        mission_id="fresh-acpx-1",
        launch_mode="fresh",
        variant="default",
        round_dir=round_dir,
    )

    report_json = json.loads(Path(report["json_path"]).read_text(encoding="utf-8"))
    assert report_json["status"] == "pass"
    assert report_json["mission_id"] == "fresh-acpx-1"
    assert report_json["launch_mode"] == "fresh"
    assert report_json["variant"] == "default"
    assert report_json["round_dir"] == str(round_dir)
    assert report_json["fresh_report"]["acceptance_review"]["status"] == "pass"
