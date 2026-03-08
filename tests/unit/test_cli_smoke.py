from typer.testing import CliRunner

from spec_orch.cli import app


def test_cli_help_shows_run_issue_command() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "run-issue" in result.stdout
    assert "accept-issue" in result.stdout


def test_run_issue_uses_fixture_and_reports_gate_result(tmp_path) -> None:
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
    assert "blocked=verification,human_acceptance" in result.stdout


def test_accept_issue_marks_existing_run_mergeable(tmp_path) -> None:
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
    assert accept_result.exit_code == 0
    assert "mergeable=True" in accept_result.stdout
    assert "accepted_by=chris" in accept_result.stdout
