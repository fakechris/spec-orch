from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from spec_orch.cli import app
from spec_orch.services.config_checker import CheckResult, ConfigChecker


def _write_config(path: Path, content: str) -> Path:
    path.write_text(content.strip() + "\n", encoding="utf-8")
    return path


def test_check_toml_reports_missing_required_fields(tmp_path: Path) -> None:
    checker = ConfigChecker()
    config_path = _write_config(
        tmp_path / "spec-orch.toml",
        """
        [linear]
        token_env = "SPEC_ORCH_LINEAR_TOKEN"

        [builder]
        adapter = "codex_exec"

        [planner]
        api_key_env = "SPEC_ORCH_LLM_API_KEY"

        [daemon]
        max_concurrent = 1
        """,
    )

    results = checker.check_toml(config_path)

    assert results == [
        CheckResult(
            name="linear",
            status="fail",
            message="Missing required fields: team_key",
        ),
        CheckResult(
            name="builder",
            status="pass",
            message="Section present.",
        ),
        CheckResult(
            name="planner",
            status="fail",
            message="Missing required fields: model",
        ),
        CheckResult(
            name="daemon",
            status="pass",
            message="Section present.",
        ),
    ]


def test_check_linear_reports_available_workflow_states() -> None:
    checker = ConfigChecker()
    fake_client = MagicMock()
    fake_client.query.return_value = {
        "teams": {
            "nodes": [
                {
                    "key": "SPC",
                    "name": "SpecOrch",
                    "states": {"nodes": [{"name": "Todo"}, {"name": "In Progress"}]},
                }
            ]
        }
    }

    with patch("spec_orch.services.config_checker.LinearClient", return_value=fake_client):
        results = checker.check_linear("linear-token", "SPC")

    assert results == [
        CheckResult(
            name="linear_api",
            status="pass",
            message="Connected to Linear team SPC. Workflow states: Todo, In Progress",
        )
    ]
    fake_client.close.assert_called_once_with()


def test_check_linear_fails_when_team_key_does_not_exist() -> None:
    checker = ConfigChecker()
    fake_client = MagicMock()
    fake_client.query.return_value = {
        "teams": {"nodes": [{"key": "OPS", "states": {"nodes": [{"name": "Todo"}]}}]}
    }

    with patch("spec_orch.services.config_checker.LinearClient", return_value=fake_client):
        results = checker.check_linear("linear-token", "SPC")

    assert results == [
        CheckResult(
            name="linear_api",
            status="fail",
            message="Team key SPC not found. Available teams: OPS",
        )
    ]


def test_check_codex_runs_version_command() -> None:
    """Legacy test for backward compatibility."""
    checker = ConfigChecker()
    completed = MagicMock(returncode=0, stdout="codex 1.2.3\n", stderr="")

    with patch("spec_orch.services.config_checker.subprocess.run", return_value=completed) as run:
        result = checker.check_codex("codex")

    assert result.name == "builder"  # Now returns "builder" instead of "codex"
    assert result.status == "pass"
    assert "codex_exec" in result.message
    assert "codex 1.2.3" in result.message
    run.assert_called_once_with(
        ["codex", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )


def test_check_codex_fails_when_executable_is_missing() -> None:
    """Legacy test for backward compatibility."""
    checker = ConfigChecker()

    with patch(
        "spec_orch.services.config_checker.subprocess.run",
        side_effect=FileNotFoundError("No such file or directory"),
    ):
        result = checker.check_codex("missing-codex")

    assert result.name == "builder"  # Now returns "builder" instead of "codex"
    assert result.status == "fail"
    assert "codex_exec" in result.message
    assert "Executable not found" in result.message


def test_check_builder_with_agent_and_model() -> None:
    """Test check_builder with all parameters including agent and model."""
    checker = ConfigChecker()
    completed = MagicMock(returncode=0, stdout="opencode 2.0.0\n", stderr="")

    with patch("spec_orch.services.config_checker.subprocess.run", return_value=completed):
        result = checker.check_builder(
            adapter="opencode",
            executable="opencode",
            agent="opencode",
            model="minimax/MiniMax-M2.5",
        )

    assert result.name == "builder"
    assert result.status == "pass"
    assert "adapter=opencode" in result.message
    assert "agent=opencode" in result.message
    assert "model=minimax/MiniMax-M2.5" in result.message
    assert "opencode 2.0.0" in result.message


def test_check_builder_acpx_no_executable_check() -> None:
    """Test that acpx adapter doesn't run executable check."""
    checker = ConfigChecker()

    result = checker.check_builder(
        adapter="acpx",
        executable="npx",
        agent="codex",
        model="gpt-4o",
    )

    assert result.name == "builder"
    assert result.status == "pass"
    assert "adapter=acpx" in result.message
    assert "agent=codex" in result.message
    assert "model=gpt-4o" in result.message


def test_check_planner_warns_when_model_is_not_configured() -> None:
    checker = ConfigChecker()

    results = checker.check_planner(None, None)

    assert results == [
        CheckResult(
            name="planner_model",
            status="warn",
            message="Planner model is not configured.",
        ),
        CheckResult(
            name="planner_api_key",
            status="warn",
            message="Planner API key env var is not configured.",
        ),
    ]


def test_check_planner_requires_defined_api_key_env() -> None:
    checker = ConfigChecker()

    with patch.dict("os.environ", {}, clear=True):
        results = checker.check_planner("anthropic/claude-sonnet", "SPEC_ORCH_LLM_API_KEY")

    assert results == [
        CheckResult(
            name="planner_model",
            status="pass",
            message="Planner model configured: anthropic/claude-sonnet (api_type=anthropic)",
        ),
        CheckResult(
            name="planner_api_key",
            status="fail",
            message="Environment variable SPEC_ORCH_LLM_API_KEY is not set.",
        ),
    ]


def test_config_check_command_prints_report_and_succeeds(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path / "spec-orch.toml",
        """
        [linear]
        token_env = "SPEC_ORCH_LINEAR_TOKEN"
        team_key = "SPC"

        [builder]
        codex_executable = "codex"

        [planner]
        model = "anthropic/claude-sonnet"
        api_key_env = "SPEC_ORCH_LLM_API_KEY"

        [daemon]
        max_concurrent = 1
        """,
    )
    runner = CliRunner()

    with (
        patch.object(
            ConfigChecker,
            "check_toml",
            return_value=[
                CheckResult("linear", "pass", "Section present."),
                CheckResult("builder", "pass", "Section present."),
                CheckResult("planner", "pass", "Section present."),
                CheckResult("daemon", "pass", "Section present."),
            ],
        ),
        patch.object(
            ConfigChecker,
            "check_linear",
            return_value=[
                CheckResult(
                    "linear_api",
                    "pass",
                    "Connected to Linear team SPC. Workflow states: Todo",
                )
            ],
        ),
        patch.object(
            ConfigChecker,
            "check_builder",
            return_value=CheckResult("builder", "pass", "adapter=codex_exec | codex 1.2.3"),
        ),
        patch.object(
            ConfigChecker,
            "check_planner",
            return_value=[
                CheckResult(
                    "planner_model",
                    "pass",
                    "Planner model configured: anthropic/claude-sonnet (api_type=anthropic)",
                ),
                CheckResult(
                    "planner_api_key",
                    "pass",
                    "Environment variable SPEC_ORCH_LLM_API_KEY is set.",
                ),
            ],
        ),
    ):
        result = runner.invoke(app, ["config", "check", "--config", str(config_path)])

    assert result.exit_code == 0
    assert "[PASS] linear" in result.stdout
    assert "[PASS] linear_api" in result.stdout
    assert "[PASS] builder" in result.stdout
    assert "Summary: 9 pass, 0 warn, 0 fail" in result.stdout


def test_config_check_command_exits_nonzero_on_failures(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path / "spec-orch.toml",
        """
        [linear]
        token_env = "SPEC_ORCH_LINEAR_TOKEN"
        team_key = "SPC"

        [builder]
        codex_executable = "codex"

        [planner]
        model = "anthropic/claude-sonnet"
        api_key_env = "SPEC_ORCH_LLM_API_KEY"

        [daemon]
        max_concurrent = 1
        """,
    )
    runner = CliRunner()

    with (
        patch.object(
            ConfigChecker,
            "check_toml",
            return_value=[
                CheckResult("linear", "pass", "Section present."),
                CheckResult("builder", "pass", "Section present."),
                CheckResult("planner", "pass", "Section present."),
                CheckResult("daemon", "pass", "Section present."),
            ],
        ),
        patch.object(
            ConfigChecker,
            "check_linear",
            return_value=[CheckResult("linear_api", "fail", "Token rejected.")],
        ),
        patch.object(
            ConfigChecker,
            "check_builder",
            return_value=CheckResult("builder", "pass", "adapter=codex_exec | codex 1.2.3"),
        ),
        patch.object(
            ConfigChecker,
            "check_planner",
            return_value=[
                CheckResult(
                    "planner_model",
                    "pass",
                    "Planner model configured: anthropic/claude-sonnet (api_type=anthropic)",
                ),
                CheckResult(
                    "planner_api_key",
                    "pass",
                    "Environment variable SPEC_ORCH_LLM_API_KEY is set.",
                ),
            ],
        ),
    ):
        result = runner.invoke(app, ["config", "check", "--config", str(config_path)])

    assert result.exit_code == 1
    assert "[FAIL] linear_api" in result.stdout
    assert "Summary: 8 pass, 0 warn, 1 fail" in result.stdout
