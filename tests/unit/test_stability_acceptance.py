from __future__ import annotations

import json
import os
from pathlib import Path


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_issue_start_smoke_script_reads_redirected_preflight_report() -> None:
    script = (
        Path(__file__).resolve().parents[2] / "tests" / "e2e" / "issue_start_smoke.sh"
    ).read_text(encoding="utf-8")

    assert "/tmp/spec_orch_issue_start_preflight.json" in script
    assert 'repo_root / ".spec_orch" / "preflight.json"' not in script
    assert "PREFLIGHT_EXIT=0" in script
    assert "spec-orch chain status --issue-id" in script
    assert 'python - <<\'PY\' "$ISSUE_ID" "$RUN_EXIT"' in script
    assert "run_exit_code = int(sys.argv[2])" in script
    assert "except (OSError, json.JSONDecodeError):" in script
    assert (
        'uv run --python 3.13 spec-orch run "$ISSUE_ID" --source "$SOURCE" --auto-approve' in script
    )


def test_issue_start_smoke_fixture_uses_bounded_builder_prompt() -> None:
    fixture = json.loads(
        (Path(__file__).resolve().parents[2] / "fixtures" / "issues" / "SPC-1.json").read_text(
            encoding="utf-8"
        )
    )

    prompt = fixture.get("builder_prompt")
    assert isinstance(prompt, str)
    assert "prototype pipeline" not in prompt.lower()
    assert ".spec_orch_smoke/issue_start_builder.txt" in prompt
    assert "do not invoke `spec-orch`" in prompt.lower()
    verification_commands = fixture.get("verification_commands")
    assert isinstance(verification_commands, dict)
    assert set(verification_commands) == {"smoke_check", "build"}
    assert ".spec_orch_smoke/issue_start_builder.txt" in verification_commands["smoke_check"][-1]


def test_mission_harness_polls_runtime_chain_status_while_fresh_run_executes() -> None:
    script = (
        Path(__file__).resolve().parents[2] / "tests" / "e2e" / "mission_start_acceptance.sh"
    ).read_text(encoding="utf-8")

    assert '. "$SCRIPT_DIR/_shared_env.sh"' in script
    assert "activate_shared_worktree_context" in script
    assert './tests/e2e/fresh_acpx_mission_smoke.sh --full --variant "$VARIANT" >' in script
    assert "HARNESS_PID=$!" in script
    assert "spec-orch chain status --mission-id" in script
    assert 'wait "$HARNESS_PID"' in script
    assert "write_mission_start_acceptance_failure_report" in script


def test_exploratory_harness_polls_runtime_chain_status_while_fresh_run_executes() -> None:
    script = (
        Path(__file__).resolve().parents[2] / "tests" / "e2e" / "exploratory_acceptance_smoke.sh"
    ).read_text(encoding="utf-8")

    assert '. "$SCRIPT_DIR/_shared_env.sh"' in script
    assert "activate_shared_worktree_context" in script
    assert './tests/e2e/fresh_acpx_mission_smoke.sh --full --variant "$VARIANT" >' in script
    assert "HARNESS_PID=$!" in script
    assert "spec-orch chain status --mission-id" in script
    assert 'wait "$HARNESS_PID"' in script
    assert "run_fresh_exploratory_acceptance_review" in script
    assert 'spec-orch dashboard --port "$DASHBOARD_PORT"' in script
    assert 'SPEC_ORCH_VISUAL_EVAL_URL="http://127.0.0.1:${DASHBOARD_PORT}"' in script
    assert "dashboard started at http://127.0.0.1:${DASHBOARD_PORT}" in script
    assert "reusing dashboard at http://127.0.0.1:${DASHBOARD_PORT}" in script
    assert "write_exploratory_acceptance_failure_report" in script


def test_acceptance_harnesses_share_uv_project_environment_resolution() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    shared_helper = (repo_root / "tests" / "e2e" / "_shared_env.sh").read_text(
        encoding="utf-8"
    )

    assert "resolve_uv_project_environment" in shared_helper
    assert 'printf \'%s\\n\' "$shared_root/.venv-py313"' in shared_helper
    assert 'export UV_PROJECT_ENVIRONMENT="$shared_uv_env"' in shared_helper

    for name in (
        "dashboard_ui_acceptance.sh",
        "issue_start_smoke.sh",
        "mission_start_acceptance.sh",
        "exploratory_acceptance_smoke.sh",
        "fresh_acpx_mission_smoke.sh",
        "update_stability_acceptance_status.sh",
    ):
        script = (repo_root / "tests" / "e2e" / name).read_text(encoding="utf-8")
        assert '. "$SCRIPT_DIR/_shared_env.sh"' in script
        assert "activate_shared_worktree_context" in script


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
        run_exit_code=0,
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


def test_write_issue_start_acceptance_report_requires_succeeded_attempt(
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
            "mergeable": False,
            "failed_conditions": ["builder", "verification"],
        },
    )
    _write_json(
        workspace / "run_artifact" / "live.json",
        {
            "run_id": "run-spc-1",
            "issue_id": "SPC-1",
            "builder": {"adapter": "acpx", "succeeded": False},
            "verification": {"lint": {"exit_code": 1}},
            "review": {"verdict": "pending"},
        },
    )
    _write_json(
        workspace / "run_artifact" / "conclusion.json",
        {
            "run_id": "run-spc-1",
            "issue_id": "SPC-1",
            "state": "gate_evaluated",
            "verdict": "fail",
            "mergeable": False,
            "failed_conditions": ["builder", "verification"],
        },
    )

    report = write_issue_start_acceptance_report(
        repo_root=tmp_path,
        issue_id="SPC-1",
        fixture_issue_id="SPC-1",
        preflight_report={"summary": {"pass": 4, "fail": 0, "warn": 0}},
        run_exit_code=0,
    )

    report_json = json.loads(Path(report["json_path"]).read_text(encoding="utf-8"))
    assert report_json["status"] == "fail"
    assert report_json["attempt"]["outcome"]["status"] == "failed"


def test_write_issue_start_acceptance_report_allows_gate_blocked_after_clean_smoke(
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
            "mergeable": False,
            "failed_conditions": ["human_acceptance", "review"],
        },
    )
    _write_json(
        workspace / "run_artifact" / "live.json",
        {
            "run_id": "run-spc-1",
            "issue_id": "SPC-1",
            "builder": {"adapter": "acpx", "succeeded": True},
            "verification": {
                "smoke_check": {"exit_code": 0},
                "build": {"exit_code": 0},
            },
            "review": {"verdict": "pending"},
        },
    )
    _write_json(
        workspace / "run_artifact" / "conclusion.json",
        {
            "run_id": "run-spc-1",
            "issue_id": "SPC-1",
            "state": "gate_evaluated",
            "verdict": "fail",
            "mergeable": False,
            "failed_conditions": ["human_acceptance", "review"],
        },
    )

    report = write_issue_start_acceptance_report(
        repo_root=tmp_path,
        issue_id="SPC-1",
        fixture_issue_id="SPC-1",
        preflight_report={"summary": {"pass": 4, "fail": 0, "warn": 0}},
        run_exit_code=0,
    )

    report_json = json.loads(Path(report["json_path"]).read_text(encoding="utf-8"))
    assert report_json["status"] == "pass"
    assert report_json["attempt"]["outcome"]["status"] == "failed"
    assert report_json["attempt"]["outcome"]["verification"]["smoke_check"]["exit_code"] == 0


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


def test_write_mission_start_acceptance_failure_report_materializes_direct_fail_payload(
    tmp_path: Path,
) -> None:
    from spec_orch.services.stability_acceptance import (
        write_mission_start_acceptance_failure_report,
    )

    report = write_mission_start_acceptance_failure_report(
        repo_root=tmp_path,
        launch_mode="fresh",
        variant="default",
        failure_reason="missing usable model-chain credentials for full mode: planner",
        mission_id="",
    )

    report_json = json.loads(Path(report["json_path"]).read_text(encoding="utf-8"))
    assert report_json["status"] == "fail"
    assert report_json["launch_mode"] == "fresh"
    assert report_json["variant"] == "default"
    assert "planner" in report_json["failure_reason"]


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
        round_dir / "exploratory_acceptance_review.json",
        {
            "status": "pass",
            "summary": "Exploratory critique found one useful UX issue.",
            "acceptance_mode": "exploratory",
            "findings": [
                {
                    "severity": "medium",
                    "summary": "Acceptance evidence is discoverable but weakly signposted.",
                    "critique_axis": "discoverability gaps",
                }
            ],
            "issue_proposals": [
                {
                    "title": "Clarify acceptance evidence entry point",
                    "summary": "Improve wayfinding into the acceptance tab.",
                    "severity": "medium",
                }
            ],
            "recommended_next_step": "Review mission tab naming and evidence grouping.",
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
    assert report_json["summary"] == "Exploratory critique found one useful UX issue."
    assert report_json["mission_id"] == "fresh-acpx-2"
    assert report_json["source"] == "fresh-acpx-mission-smoke"
    assert report_json["source_run"]["mission_id"] == "fresh-acpx-2"
    assert report_json["source_run"]["round_id"] == "round-01"
    assert report_json["source_run"]["review_path"].endswith(
        "docs/specs/fresh-acpx-2/rounds/round-01/exploratory_acceptance_review.json"
    )
    assert report_json["findings_count"] == 1
    assert report_json["issue_proposal_count"] == 1
    assert (
        report_json["recommended_next_step"] == "Review mission tab naming and evidence grouping."
    )
    assert report_json["acceptance_mode"] == "exploratory"
    assert report_json["coverage_status"] == "complete"
    assert report_json["browser_evidence"]["tested_routes"] == ["/", "/settings"]
    assert report_json["acceptance_review"]["acceptance_mode"] == "exploratory"
    assert (
        report_json["acceptance_review"]["artifacts"]["graph_profile"] == "tuned_exploratory_graph"
    )
    assert report_json["finding_taxonomy"]["counts"]["ux_gap"] == 2
    assert report_json["finding_taxonomy"]["counts"]["harness_bug"] == 0
    assert report_json["finding_taxonomy"]["counts"]["n2n_bug"] == 0
    assert report_json["finding_taxonomy"]["findings"][0]["bug_type"] == "ux_gap"
    assert report_json["finding_taxonomy"]["issue_proposals"][0]["bug_type"] == "ux_gap"
    report_md = Path(report["markdown_path"]).read_text(encoding="utf-8")
    assert "Findings: `1`" in report_md
    assert "Issue proposals: `1`" in report_md
    assert "Recommended next step: `Review mission tab naming and evidence grouping.`" in report_md


def test_write_exploratory_acceptance_report_prefers_exploratory_browser_evidence(
    tmp_path: Path,
) -> None:
    from spec_orch.services.stability_acceptance import write_exploratory_acceptance_report

    mission_id = "fresh-acpx-3"
    round_dir = tmp_path / "docs" / "specs" / mission_id / "rounds" / "round-01"
    round_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        round_dir / "exploratory_acceptance_review.json",
        {
            "status": "pass",
            "summary": "Exploratory review succeeded.",
            "acceptance_mode": "exploratory",
        },
    )
    _write_json(
        round_dir / "browser_evidence.json",
        {
            "tested_routes": ["/"],
            "interactions": {"/": []},
        },
    )
    _write_json(
        round_dir / "exploratory_browser_evidence.json",
        {
            "tested_routes": ["/?mission=fresh-acpx-3&tab=transcript"],
            "interactions": {
                "/?mission=fresh-acpx-3&tab=transcript": [
                    {"action": "wait_for_selector", "status": "passed"}
                ]
            },
        },
    )

    report = write_exploratory_acceptance_report(
        repo_root=tmp_path,
        mission_id=mission_id,
        variant="default",
        round_dir=round_dir,
        source="fresh-acpx-mission-smoke",
    )

    report_json = json.loads(Path(report["json_path"]).read_text(encoding="utf-8"))
    assert report_json["browser_evidence"]["tested_routes"] == [
        "/?mission=fresh-acpx-3&tab=transcript"
    ]


def test_write_exploratory_acceptance_failure_report_materializes_direct_fail_payload(
    tmp_path: Path,
) -> None:
    from spec_orch.services.stability_acceptance import (
        write_exploratory_acceptance_failure_report,
    )

    report = write_exploratory_acceptance_failure_report(
        repo_root=tmp_path,
        mission_id="",
        variant="default",
        source="fresh-acpx-mission-smoke",
        failure_reason="missing usable model-chain credentials for full mode: planner",
    )

    report_json = json.loads(Path(report["json_path"]).read_text(encoding="utf-8"))
    assert report_json["status"] == "fail"
    assert report_json["source"] == "fresh-acpx-mission-smoke"
    assert "planner" in report_json["summary"]


def test_write_exploratory_acceptance_report_preserves_warn_status_and_harness_taxonomy(
    tmp_path: Path,
) -> None:
    from spec_orch.services.stability_acceptance import write_exploratory_acceptance_report

    mission_id = "fresh-acpx-config"
    round_dir = tmp_path / "docs" / "specs" / mission_id / "rounds" / "round-02"
    round_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        round_dir / "exploratory_acceptance_review.json",
        {
            "status": "warn",
            "summary": "Exploratory acceptance configuration is incomplete.",
            "acceptance_mode": "exploratory",
            "coverage_status": "partial",
            "findings": [
                {
                    "severity": "high",
                    "summary": "Acceptance evaluator configuration is incomplete.",
                    "details": "The second-stage exploratory critique cannot produce product findings until its provider configuration is valid.",
                    "critique_axis": "evaluation_config",
                    "why_it_matters": "The critique stage is blocked on harness configuration.",
                }
            ],
            "issue_proposals": [],
            "recommended_next_step": "Set the acceptance evaluator API base and rerun exploratory critique.",
        },
    )

    report = write_exploratory_acceptance_report(
        repo_root=tmp_path,
        mission_id=mission_id,
        variant="default",
        round_dir=round_dir,
        source="fresh-acpx-mission-smoke",
    )

    report_json = json.loads(Path(report["json_path"]).read_text(encoding="utf-8"))
    assert report_json["status"] == "warn"
    assert report_json["summary"] == "Exploratory acceptance configuration is incomplete."
    assert report_json["source_run"]["round_id"] == "round-02"
    assert report_json["coverage_status"] == "partial"
    assert report_json["recommended_next_step"] == (
        "Set the acceptance evaluator API base and rerun exploratory critique."
    )
    assert report_json["findings_count"] == 1
    assert report_json["issue_proposal_count"] == 0
    assert report_json["finding_taxonomy"]["counts"]["harness_bug"] == 1
    assert report_json["finding_taxonomy"]["counts"]["n2n_bug"] == 0
    assert report_json["finding_taxonomy"]["counts"]["ux_gap"] == 0
    assert report_json["finding_taxonomy"]["findings"][0]["bug_type"] == "harness_bug"


def test_write_exploratory_acceptance_report_classifies_route_page_errors_as_n2n_bugs(
    tmp_path: Path,
) -> None:
    from spec_orch.services.stability_acceptance import write_exploratory_acceptance_report

    mission_id = "fresh-acpx-page-error"
    round_dir = tmp_path / "docs" / "specs" / mission_id / "rounds" / "round-03"
    round_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        round_dir / "exploratory_acceptance_review.json",
        {
            "status": "warn",
            "summary": "Transcript route hit a page error during exploratory critique.",
            "acceptance_mode": "exploratory",
            "coverage_status": "complete",
            "findings": [
                {
                    "severity": "high",
                    "summary": "Browser page error on /?mission=demo&tab=transcript",
                    "details": "Browser evidence recorded a page error on /?mission=demo&tab=transcript.",
                    "route": "/?mission=demo&tab=transcript",
                }
            ],
            "issue_proposals": [
                {
                    "title": "Investigate transcript page error",
                    "summary": "Browser evidence recorded a page error on /?mission=demo&tab=transcript.",
                    "route": "/?mission=demo&tab=transcript",
                }
            ],
        },
    )

    report = write_exploratory_acceptance_report(
        repo_root=tmp_path,
        mission_id=mission_id,
        variant="default",
        round_dir=round_dir,
        source="fresh-acpx-mission-smoke",
    )

    report_json = json.loads(Path(report["json_path"]).read_text(encoding="utf-8"))
    assert report_json["finding_taxonomy"]["counts"]["n2n_bug"] == 2
    assert report_json["finding_taxonomy"]["counts"]["harness_bug"] == 0
    assert report_json["finding_taxonomy"]["findings"][0]["bug_type"] == "n2n_bug"
    assert report_json["finding_taxonomy"]["issue_proposals"][0]["bug_type"] == "n2n_bug"


def test_write_stability_acceptance_status_summarizes_latest_reports(
    tmp_path: Path,
) -> None:
    from spec_orch.services.stability_acceptance import write_stability_acceptance_status

    acceptance_dir = tmp_path / ".spec_orch" / "acceptance"
    _write_json(acceptance_dir / "issue_start_smoke.json", {"status": "pass", "issue_id": "SPC-1"})
    _write_json(
        acceptance_dir / "dashboard_ui_acceptance.json",
        {
            "status": "pass",
            "suite_summary": {"surface_summary": {"launcher": "pass", "visual_qa": "pass"}},
        },
    )

    mission_id = "fresh-acpx-3"
    operator_dir = tmp_path / "docs" / "specs" / mission_id / "operator"
    _write_json(
        operator_dir / "mission_start_acceptance.json",
        {"status": "pass", "mission_id": mission_id, "variant": "default"},
    )
    _write_json(
        operator_dir / "exploratory_acceptance_smoke.json",
        {"status": "fail", "mission_id": mission_id, "variant": "default"},
    )
    _write_json(
        operator_dir / "runtime_chain" / "chain_status.json",
        {
            "chain_id": "mission-chain-7",
            "active_span_id": "mission-chain-7:acceptance",
            "subject_kind": "acceptance",
            "subject_id": "acceptance-round-03",
            "phase": "degraded",
            "status_reason": "acceptance_model_waiting",
            "updated_at": "2026-03-31T10:15:00+00:00",
        },
    )

    report = write_stability_acceptance_status(repo_root=tmp_path)

    report_json = json.loads(Path(report["json_path"]).read_text(encoding="utf-8"))
    report_md = Path(report["markdown_path"]).read_text(encoding="utf-8")

    assert report_json["summary"]["overall_status"] == "fail"
    assert report_json["checks"]["issue_start"]["status"] == "pass"
    assert report_json["checks"]["dashboard_ui"]["status"] == "pass"
    assert report_json["checks"]["mission_start"]["mission_id"] == mission_id
    assert report_json["checks"]["mission_start"]["runtime_chain"]["phase"] == "degraded"
    assert (
        report_json["checks"]["mission_start"]["runtime_chain"]["status_reason"]
        == "acceptance_model_waiting"
    )
    assert report_json["checks"]["exploratory"]["status"] == "fail"
    assert "Exploratory" in report_md
    assert "fail" in report_md.lower()
    assert "acceptance_model_waiting" in report_md


def test_write_stability_acceptance_status_prefers_newer_direct_failure_reports_over_history(
    tmp_path: Path,
) -> None:
    from spec_orch.services.stability_acceptance import write_stability_acceptance_status

    acceptance_dir = tmp_path / ".spec_orch" / "acceptance"
    _write_json(acceptance_dir / "issue_start_smoke.json", {"status": "fail", "issue_id": "SPC-1"})
    _write_json(
        acceptance_dir / "dashboard_ui_acceptance.json",
        {"status": "pass", "suite_summary": {"surface_summary": {"launcher": "pass"}}},
    )
    _write_json(
        acceptance_dir / "mission_start_acceptance.json",
        {"status": "fail", "failure_reason": "planner creds missing"},
    )
    _write_json(
        acceptance_dir / "exploratory_acceptance_smoke.json",
        {"status": "fail", "summary": "planner creds missing"},
    )

    operator_dir = tmp_path / "docs" / "specs" / "fresh-acpx-stale" / "operator"
    _write_json(
        operator_dir / "mission_start_acceptance.json",
        {"status": "pass", "mission_id": "fresh-acpx-stale"},
    )
    _write_json(
        operator_dir / "exploratory_acceptance_smoke.json",
        {"status": "pass", "mission_id": "fresh-acpx-stale"},
    )
    os.utime(operator_dir / "mission_start_acceptance.json", (1, 1))
    os.utime(operator_dir / "exploratory_acceptance_smoke.json", (1, 1))
    os.utime(acceptance_dir / "mission_start_acceptance.json", (2, 2))
    os.utime(acceptance_dir / "exploratory_acceptance_smoke.json", (2, 2))

    report = write_stability_acceptance_status(repo_root=tmp_path)

    report_json = json.loads(Path(report["json_path"]).read_text(encoding="utf-8"))
    assert report_json["checks"]["mission_start"]["status"] == "fail"
    assert report_json["checks"]["exploratory"]["status"] == "fail"
    assert report_json["summary"]["overall_status"] == "fail"


def test_write_stability_acceptance_status_prefers_newer_operator_reports_over_stale_direct_failures(
    tmp_path: Path,
) -> None:
    from spec_orch.services.stability_acceptance import write_stability_acceptance_status

    acceptance_dir = tmp_path / ".spec_orch" / "acceptance"
    _write_json(acceptance_dir / "issue_start_smoke.json", {"status": "pass", "issue_id": "SPC-1"})
    _write_json(
        acceptance_dir / "dashboard_ui_acceptance.json",
        {"status": "pass", "suite_summary": {"surface_summary": {"launcher": "pass"}}},
    )
    _write_json(
        acceptance_dir / "mission_start_acceptance.json",
        {"status": "fail", "failure_reason": "stale creds failure"},
    )
    _write_json(
        acceptance_dir / "exploratory_acceptance_smoke.json",
        {"status": "fail", "summary": "stale creds failure"},
    )

    operator_dir = tmp_path / "docs" / "specs" / "fresh-acpx-new" / "operator"
    _write_json(
        operator_dir / "mission_start_acceptance.json",
        {"status": "pass", "mission_id": "fresh-acpx-new"},
    )
    _write_json(
        operator_dir / "exploratory_acceptance_smoke.json",
        {"status": "pass", "mission_id": "fresh-acpx-new"},
    )
    os.utime(acceptance_dir / "mission_start_acceptance.json", (1, 1))
    os.utime(acceptance_dir / "exploratory_acceptance_smoke.json", (1, 1))
    os.utime(operator_dir / "mission_start_acceptance.json", (2, 2))
    os.utime(operator_dir / "exploratory_acceptance_smoke.json", (2, 2))

    report = write_stability_acceptance_status(repo_root=tmp_path)

    report_json = json.loads(Path(report["json_path"]).read_text(encoding="utf-8"))
    assert report_json["checks"]["mission_start"]["status"] == "pass"
    assert report_json["checks"]["exploratory"]["status"] == "pass"
    assert report_json["summary"]["overall_status"] == "pass"
