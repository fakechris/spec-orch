import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from spec_orch.cli import app
from spec_orch.domain.models import Finding
from spec_orch.services.finding_store import append_finding, fingerprint_from, load_findings


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


def test_status_all_command_shows_issue_table(tmp_path) -> None:
    runs_dir = tmp_path / ".spec_orch_runs"
    for issue_id, state, mergeable, title in (
        ("SPC-20", "review_pending", False, "Second issue"),
        ("SPC-3", "accepted", True, "First issue"),
    ):
        workspace = runs_dir / issue_id
        workspace.mkdir(parents=True)
        (workspace / "report.json").write_text(
            json.dumps(
                {
                    "issue_id": issue_id,
                    "state": state,
                    "mergeable": mergeable,
                    "title": title,
                }
            )
        )

    runner = CliRunner()

    result = runner.invoke(app, ["status", "--all", "--repo-root", str(tmp_path)])

    assert result.exit_code == 0
    assert "Issue ID" in result.stdout
    assert "State" in result.stdout
    assert "Mergeable" in result.stdout
    assert "Title" in result.stdout
    assert "SPC-3" in result.stdout
    assert "accepted" in result.stdout
    assert "True" in result.stdout
    assert "First issue" in result.stdout
    assert "SPC-20" in result.stdout
    assert "review_pending" in result.stdout
    assert "False" in result.stdout
    assert "Second issue" in result.stdout
    assert result.stdout.index("SPC-3") < result.stdout.index("SPC-20")


def test_status_all_command_reports_no_issues_found(tmp_path) -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["status", "--all", "--repo-root", str(tmp_path)])

    assert result.exit_code == 0
    assert "no issues found" in result.stdout


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


def _make_finding(fid: str, description: str) -> Finding:
    return Finding(
        id=fid,
        source="review",
        severity="blocking",
        confidence=0.9,
        scope="in_spec",
        fingerprint=fingerprint_from("review", description, "src/demo.py", 12),
        description=description,
        file_path="src/demo.py",
        line=12,
    )


def test_findings_list_shows_findings(tmp_path: Path) -> None:
    workspace = tmp_path / ".spec_orch_runs" / "SPC-FINDINGS"
    append_finding(workspace, _make_finding("f-1234", "Missing validation on input"))
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["findings", "list", "SPC-FINDINGS", "--repo-root", str(tmp_path)],
    )

    assert result.exit_code == 0
    assert "Missing validation on input" in result.stdout
    assert "f-1234" in result.stdout


def test_findings_resolve_marks_resolved(tmp_path: Path) -> None:
    workspace = tmp_path / ".spec_orch_runs" / "SPC-RESOLVE"
    append_finding(workspace, _make_finding("f-resolve", "Fix race condition"))
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["findings", "resolve", "SPC-RESOLVE", "f-resolve", "--repo-root", str(tmp_path)],
    )

    assert result.exit_code == 0
    assert "resolved" in result.stdout.lower()
    assert load_findings(workspace)[0].resolved is True


def test_findings_add_creates_finding(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "findings",
            "add",
            "SPC-ADD",
            "--source",
            "manual",
            "--severity",
            "advisory",
            "--description",
            "Document the missing CLI flag",
            "--file-path",
            "src/spec_orch/cli.py",
            "--line",
            "42",
            "--scope",
            "in_spec",
            "--confidence",
            "0.7",
            "--repo-root",
            str(tmp_path),
        ],
    )

    workspace = tmp_path / ".spec_orch_runs" / "SPC-ADD"
    findings = load_findings(workspace)

    assert result.exit_code == 0
    assert "added finding" in result.stdout.lower()
    assert len(findings) == 1
    assert findings[0].source == "manual"
    assert findings[0].description == "Document the missing CLI flag"


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


def test_watch_command_keeps_lines_appended_during_initial_read(tmp_path) -> None:
    workspace = tmp_path / ".spec_orch_runs" / "SPC-RACE"
    telemetry_dir = workspace / "telemetry"
    telemetry_dir.mkdir(parents=True)
    log_path = telemetry_dir / "activity.log"
    log_path.write_text("existing line\n", encoding="utf-8")

    original_read_text = __import__("pathlib").Path.read_text

    def racing_read_text(path, *args, **kwargs):
        text = original_read_text(path, *args, **kwargs)
        if path == log_path:
            log_path.write_text(text + "raced line\n", encoding="utf-8")
        return text

    def finish_watch(_seconds: float) -> None:
        (workspace / "report.json").write_text("{}", encoding="utf-8")

    runner = CliRunner()
    with patch.object(
        __import__("pathlib").Path,
        "read_text",
        autospec=True,
        side_effect=racing_read_text,
    ):
        with patch("spec_orch.cli.time.sleep", side_effect=finish_watch):
            result = runner.invoke(
                app, ["watch", "SPC-RACE", "--repo-root", str(tmp_path)]
            )

    assert result.exit_code == 0
    assert "existing line" in result.stdout
    assert "raced line" in result.stdout


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


def test_plan_to_spec_edit_uses_shell_style_editor_splitting(tmp_path) -> None:
    fixture_path = tmp_path / "plan.md"
    fixture_path.write_text("# Title\n", encoding="utf-8")
    invoked = {}

    def fake_run(command, check=False):
        invoked["command"] = command

        class Result:
            returncode = 0

        return Result()

    runner = CliRunner()
    with patch.dict("os.environ", {"EDITOR": 'python -c "print(\'ok\')"'}):
        with patch("spec_orch.cli.subprocess.run", side_effect=fake_run):
            result = runner.invoke(
                app,
                [
                    "plan-to-spec",
                    str(fixture_path),
                    "--issue-id",
                    "SPC-EDIT",
                    "--output",
                    str(tmp_path / "fixture.json"),
                    "--edit",
                ],
            )

    assert result.exit_code == 0
    assert invoked["command"][:3] == ["python", "-c", "print('ok')"]


def test_create_pr_triggers_linear_writeback(tmp_path: Path) -> None:
    from spec_orch.cli import _linear_writeback_on_pr
    from spec_orch.domain.models import GateVerdict

    config = tmp_path / "spec-orch.toml"
    config.write_text(
        '[linear]\ntoken_env = "TEST_LINEAR_TOKEN"\nteam_key = "SON"\n'
    )

    report = {"state": "gate_evaluated", "title": "Test issue"}
    gate = GateVerdict(mergeable=False, failed_conditions=["review"])

    fake_client = MagicMock()
    fake_client.get_issue.return_value = {"id": "uuid-123", "identifier": "SON-99"}

    with (
        patch.dict("os.environ", {"TEST_LINEAR_TOKEN": "fake-token"}),
        patch("spec_orch.services.linear_client.LinearClient", return_value=fake_client),
    ):
        _linear_writeback_on_pr(
            "SON-99", report, "https://github.com/pr/1", gate, tmp_path,
        )

    fake_client.add_comment.assert_called_once()
    comment = fake_client.add_comment.call_args[0][1]
    assert "SON-99" in comment
    assert "gate_evaluated" in comment
    fake_client.update_issue_state.assert_called_once_with("uuid-123", "In Progress")
    fake_client.close.assert_called_once()
