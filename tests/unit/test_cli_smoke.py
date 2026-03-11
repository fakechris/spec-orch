from typer.testing import CliRunner

from spec_orch.cli import app


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


def test_run_issue_uses_fixture_and_reports_gate_result(tmp_path) -> None:
    import json

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
    import json

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
    import json

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
    import json

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
    import json

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
