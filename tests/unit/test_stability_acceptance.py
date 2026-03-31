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


def test_write_dashboard_ui_acceptance_report_materializes_surface_summary(
    tmp_path: Path,
) -> None:
    from spec_orch.services.stability_acceptance import write_dashboard_ui_acceptance_report

    report = write_dashboard_ui_acceptance_report(
        repo_root=tmp_path,
        command="./tests/e2e/dashboard_ui_acceptance.sh --full",
        suite_summary={
            "status": "pass",
            "selected_tests": [
                "test_launcher_readiness_endpoint",
                "test_acceptance_review_endpoint_surfaces_latest_review_and_filed_issues",
                "test_visual_qa_endpoint_includes_latest_round_and_review_route",
                "test_costs_endpoint_aggregates_worker_reports",
                "test_approvals_endpoint_returns_dedicated_queue",
            ],
            "surface_summary": {
                "launcher": "pass",
                "mission_detail": "pass",
                "acceptance_review": "pass",
                "visual_qa": "pass",
                "costs": "pass",
                "approvals": "pass",
            },
        },
    )

    report_json = json.loads(Path(report["json_path"]).read_text(encoding="utf-8"))
    assert report_json["status"] == "pass"
    assert report_json["command"] == "./tests/e2e/dashboard_ui_acceptance.sh --full"
    assert report_json["suite_summary"]["surface_summary"]["visual_qa"] == "pass"
    assert (
        "test_costs_endpoint_aggregates_worker_reports"
        in report_json["suite_summary"]["selected_tests"]
    )


def test_write_exploratory_acceptance_report_preserves_round_artifacts(
    tmp_path: Path,
) -> None:
    from spec_orch.services.stability_acceptance import write_exploratory_acceptance_report

    round_dir = tmp_path / "docs" / "specs" / "fresh-acpx-2" / "rounds" / "round-01"
    round_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        round_dir / "fresh_acpx_mission_e2e_report.json",
        {
            "mission_id": "fresh-acpx-2",
            "workflow_replay": {
                "proof_type": "workflow_replay",
                "review_routes": {"overview": "/?mission=fresh-acpx-2&mode=missions&tab=overview"},
            },
            "acceptance_review": {"status": "pass", "coverage_status": "complete"},
        },
    )
    _write_json(
        round_dir / "acceptance_review.json",
        {
            "status": "pass",
            "summary": "Exploratory replay completed.",
            "artifacts": {
                "graph_profile": "tuned_exploratory_graph",
                "step_artifacts": [
                    "docs/specs/fresh-acpx-2/rounds/round-01/acceptance_graph_runs/agr-1/steps/01.json"
                ],
            },
        },
    )
    _write_json(
        round_dir / "browser_evidence.json",
        {
            "tested_routes": ["/", "/settings"],
            "screenshots": ["shot-1.png"],
        },
    )

    report = write_exploratory_acceptance_report(
        repo_root=tmp_path,
        mission_id="fresh-acpx-2",
        variant="default",
        round_dir=round_dir,
        source="fresh-acpx-mission-smoke",
    )

    report_json = json.loads(Path(report["json_path"]).read_text(encoding="utf-8"))
    assert report_json["status"] == "pass"
    assert report_json["mission_id"] == "fresh-acpx-2"
    assert report_json["source"] == "fresh-acpx-mission-smoke"
    assert report_json["browser_evidence"]["tested_routes"] == ["/", "/settings"]
    assert (
        report_json["acceptance_review"]["artifacts"]["graph_profile"] == "tuned_exploratory_graph"
    )
