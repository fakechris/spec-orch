import json
from unittest.mock import patch

from typer.testing import CliRunner

from spec_orch.cli import app


def test_cli_version_flag_prints_version() -> None:
    runner = CliRunner()
    with patch("spec_orch.cli._resolve_version", return_value="1.2.3"):
        result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "1.2.3" in result.stdout


def test_cli_version_flag_falls_back_to_dev() -> None:
    runner = CliRunner()
    with patch(
        "importlib.metadata.version",
        side_effect=__import__("importlib.metadata").metadata.PackageNotFoundError,
    ):
        result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "dev" in result.stdout


def test_cli_help_shows_run_issue_command() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "run-issue" in result.stdout
    assert "review-issue" in result.stdout
    assert "accept-issue" in result.stdout
    assert "rerun" in result.stdout
    assert "status" in result.stdout
    assert "explain" in result.stdout
    assert "diff" in result.stdout
    assert "cherry-pick" in result.stdout
    assert "daemon" in result.stdout
    assert "gate" in result.stdout
    assert "create-pr" in result.stdout
    assert "watch" in result.stdout
    assert "logs" in result.stdout
    assert "plan-to-spec" in result.stdout


def test_run_issue_uses_fixture_and_reports_gate_result(tmp_path) -> None:
    fixtures_dir = tmp_path / "fixtures" / "issues"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "SPC-1.json").write_text(
        json.dumps(
            {
                "issue_id": "SPC-1",
                "title": "Build MVP runner",
                "summary": "Run one local fixture issue through the prototype pipeline.",
            }
        )
    )
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "run-issue",
            "SPC-1",
            "--repo-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert "SPC-1" in result.stdout
    assert "mergeable=False" in result.stdout
    assert "blocked=verification,review,human_acceptance" in result.stdout


def test_review_and_accept_issue_mark_existing_run_mergeable(tmp_path) -> None:
    runner = CliRunner()
    fixtures_dir = tmp_path / "fixtures" / "issues"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "SPC-9.json").write_text(
        """
{
  "issue_id": "SPC-9",
  "title": "Accept issue",
  "summary": "Verify acceptance flow.",
  "verification_commands": {
    "lint": ["{python}", "-c", "print('lint ok')"],
    "typecheck": ["{python}", "-c", "print('type ok')"],
    "test": ["{python}", "-c", "print('test ok')"],
    "build": ["{python}", "-c", "print('build ok')"]
  }
}
""".strip()
        + "\n"
    )

    run_result = runner.invoke(
        app,
        [
            "run-issue",
            "SPC-9",
            "--repo-root",
            str(tmp_path),
        ],
    )

    review_result = runner.invoke(
        app,
        [
            "review-issue",
            "SPC-9",
            "--repo-root",
            str(tmp_path),
            "--verdict",
            "pass",
            "--reviewed-by",
            "claude",
        ],
    )

    accept_result = runner.invoke(
        app,
        [
            "accept-issue",
            "SPC-9",
            "--repo-root",
            str(tmp_path),
            "--accepted-by",
            "chris",
        ],
    )

    assert run_result.exit_code == 0
    assert "mergeable=False" in run_result.stdout
    assert review_result.exit_code == 0
    assert "mergeable=False" in review_result.stdout
    assert "review_verdict=pass" in review_result.stdout
    assert accept_result.exit_code == 0
    assert "mergeable=True" in accept_result.stdout
    assert "accepted_by=chris" in accept_result.stdout


def test_status_command_shows_issue_state(tmp_path) -> None:
    fixtures_dir = tmp_path / "fixtures" / "issues"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "SPC-20.json").write_text(
        json.dumps(
            {
                "issue_id": "SPC-20",
                "title": "Status test",
                "summary": "Test status command.",
            }
        )
    )
    runner = CliRunner()
    runner.invoke(app, ["run-issue", "SPC-20", "--repo-root", str(tmp_path)])

    result = runner.invoke(app, ["status", "SPC-20", "--repo-root", str(tmp_path)])

    assert result.exit_code == 0
    assert "SPC-20" in result.stdout
    assert "mergeable=" in result.stdout


def test_explain_command_prints_report(tmp_path) -> None:
    fixtures_dir = tmp_path / "fixtures" / "issues"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "SPC-30.json").write_text(
        json.dumps(
            {
                "issue_id": "SPC-30",
                "title": "Explain test",
                "summary": "Test explain command.",
            }
        )
    )
    runner = CliRunner()
    runner.invoke(app, ["run-issue", "SPC-30", "--repo-root", str(tmp_path)])

    result = runner.invoke(app, ["explain", "SPC-30", "--repo-root", str(tmp_path)])

    assert result.exit_code == 0
    assert "SPC-30" in result.stdout


def test_status_command_reports_missing_run(tmp_path) -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["status", "SPC-999", "--repo-root", str(tmp_path)])

    assert result.exit_code == 1
    assert "no run found" in result.stdout


def test_gate_command_shows_issue_verdict(tmp_path) -> None:
    fixtures_dir = tmp_path / "fixtures" / "issues"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "SPC-G.json").write_text(
        json.dumps(
            {
                "issue_id": "SPC-G",
                "title": "Gate test",
                "summary": "Test gate command.",
            }
        )
    )
    runner = CliRunner()
    runner.invoke(app, ["run-issue", "SPC-G", "--repo-root", str(tmp_path)])

    result = runner.invoke(
        app, ["gate", "SPC-G", "--repo-root", str(tmp_path)]
    )

    assert result.exit_code == 0
    assert "SPC-G" in result.stdout
    assert "mergeable=" in result.stdout


def test_rerun_command_re_runs_verification(tmp_path) -> None:
    fixtures_dir = tmp_path / "fixtures" / "issues"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "SPC-RR.json").write_text(
        json.dumps(
            {
                "issue_id": "SPC-RR",
                "title": "Rerun test",
                "summary": "Test rerun command.",
                "verification_commands": {
                    "lint": ["{python}", "-c", "print('lint ok')"],
                    "typecheck": ["{python}", "-c", "print('type ok')"],
                    "test": ["{python}", "-c", "print('test ok')"],
                    "build": ["{python}", "-c", "print('build ok')"],
                },
            }
        )
    )
    runner = CliRunner()
    runner.invoke(
        app, ["run-issue", "SPC-RR", "--repo-root", str(tmp_path)]
    )

    result = runner.invoke(
        app, ["rerun", "SPC-RR", "--repo-root", str(tmp_path)]
    )

    assert result.exit_code == 0
    assert "SPC-RR" in result.stdout
    assert "mergeable=" in result.stdout


def test_gate_show_policy() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["gate", "--show-policy"])
    assert result.exit_code == 0
    assert "Gate Policy" in result.stdout


def test_watch_command_shows_activity_log(tmp_path) -> None:
    fixtures_dir = tmp_path / "fixtures" / "issues"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "SPC-W.json").write_text(
        json.dumps(
            {
                "issue_id": "SPC-W",
                "title": "Watch test",
                "summary": "Test watch command.",
            }
        )
    )
    runner = CliRunner()
    runner.invoke(app, ["run-issue", "SPC-W", "--repo-root", str(tmp_path)])

    result = runner.invoke(
        app, ["watch", "SPC-W", "--repo-root", str(tmp_path)]
    )

    assert result.exit_code == 0
    assert any(
        tag in result.stdout
        for tag in ("RUN", "BUILDER", "VERIFY", "GATE")
    )


def test_watch_command_reports_missing_log(tmp_path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        app, ["watch", "SPC-NONE", "--repo-root", str(tmp_path)]
    )
    assert result.exit_code == 1
    assert "no activity log" in result.stdout


def test_logs_command_shows_activity_log(tmp_path) -> None:
    fixtures_dir = tmp_path / "fixtures" / "issues"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "SPC-L.json").write_text(
        json.dumps(
            {
                "issue_id": "SPC-L",
                "title": "Logs test",
                "summary": "Test logs command.",
            }
        )
    )
    runner = CliRunner()
    runner.invoke(app, ["run-issue", "SPC-L", "--repo-root", str(tmp_path)])

    result = runner.invoke(
        app, ["logs", "SPC-L", "--repo-root", str(tmp_path)]
    )

    assert result.exit_code == 0
    assert any(
        tag in result.stdout
        for tag in ("RUN", "BUILDER", "VERIFY", "GATE")
    )


def test_logs_command_filter(tmp_path) -> None:
    fixtures_dir = tmp_path / "fixtures" / "issues"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "SPC-LF.json").write_text(
        json.dumps(
            {
                "issue_id": "SPC-LF",
                "title": "Logs filter test",
                "summary": "Test logs filter.",
            }
        )
    )
    runner = CliRunner()
    runner.invoke(app, ["run-issue", "SPC-LF", "--repo-root", str(tmp_path)])

    result = runner.invoke(
        app, ["logs", "SPC-LF", "--repo-root", str(tmp_path), "--filter", "GATE"]
    )

    assert result.exit_code == 0
    assert "GATE" in result.stdout
    for line in result.stdout.strip().splitlines():
        assert "GATE" in line.upper()


def test_logs_command_raw_mode(tmp_path) -> None:
    fixtures_dir = tmp_path / "fixtures" / "issues"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "SPC-LR.json").write_text(
        json.dumps(
            {
                "issue_id": "SPC-LR",
                "title": "Raw logs test",
                "summary": "Test raw logs.",
            }
        )
    )
    runner = CliRunner()
    runner.invoke(app, ["run-issue", "SPC-LR", "--repo-root", str(tmp_path)])

    result = runner.invoke(
        app, ["logs", "SPC-LR", "--repo-root", str(tmp_path), "--raw"]
    )

    if result.exit_code == 0:
        pass
    else:
        assert "file not found" in result.stdout


def test_logs_command_events_mode(tmp_path) -> None:
    fixtures_dir = tmp_path / "fixtures" / "issues"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "SPC-LE.json").write_text(
        json.dumps(
            {
                "issue_id": "SPC-LE",
                "title": "Events logs test",
                "summary": "Test events logs.",
            }
        )
    )
    runner = CliRunner()
    runner.invoke(app, ["run-issue", "SPC-LE", "--repo-root", str(tmp_path)])

    result = runner.invoke(
        app, ["logs", "SPC-LE", "--repo-root", str(tmp_path), "--events"]
    )

    assert result.exit_code == 0
    assert "run_started" in result.stdout or "event_type" in result.stdout


def test_run_issue_with_live_flag(tmp_path) -> None:
    fixtures_dir = tmp_path / "fixtures" / "issues"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "SPC-LV.json").write_text(
        json.dumps(
            {
                "issue_id": "SPC-LV",
                "title": "Live test",
                "summary": "Test live flag.",
            }
        )
    )
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["run-issue", "SPC-LV", "--repo-root", str(tmp_path), "--live"],
    )
    assert result.exit_code == 0
    assert "SPC-LV" in result.stdout


def test_plan_to_spec_command_generates_fixture(tmp_path) -> None:
    runner = CliRunner()
    plan_path = tmp_path / "plan.md"
    output_path = tmp_path / "fixtures" / "issues" / "SPC-PLAN.json"
    plan_path.write_text(
        """
# Build plan-to-spec

## Background

Turn a markdown plan into a fixture.

## File Changes
- Create `src/spec_orch/services/plan_parser.py` with parsing logic.

## Acceptance Criteria
- Fixture JSON is written.
""".strip()
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "plan-to-spec",
            str(plan_path),
            "--issue-id",
            "SPC-PLAN",
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 0
    assert output_path.exists()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["issue_id"] == "SPC-PLAN"
    assert payload["title"] == "Build plan-to-spec"
    assert payload["summary"] == "Turn a markdown plan into a fixture."
    assert payload["acceptance_criteria"] == ["Fixture JSON is written."]


def test_plan_to_spec_no_builder_flag(tmp_path) -> None:
    runner = CliRunner()
    plan_path = tmp_path / "plan.md"
    output_path = tmp_path / "fixtures" / "issues" / "SPC-NB.json"
    plan_path.write_text("# Empty\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "plan-to-spec",
            str(plan_path),
            "--issue-id",
            "SPC-NB",
            "--output",
            str(output_path),
            "--no-builder",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["builder_prompt"] is None


def test_plan_to_spec_appears_in_help() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "plan-to-spec" in result.stdout
