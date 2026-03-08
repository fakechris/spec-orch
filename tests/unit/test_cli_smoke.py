from typer.testing import CliRunner

from spec_orch.cli import app


def test_cli_help_shows_run_issue_command() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "run-issue" in result.stdout


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
