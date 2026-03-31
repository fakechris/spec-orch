from __future__ import annotations

import signal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from spec_orch.domain.models import RunState
from spec_orch.services.daemon import DaemonConfig, SpecOrchDaemon
from spec_orch.services.readiness_checker import ReadinessChecker

_COMPLETE_DESC = (
    "## Goal\nDo something.\n\n## Acceptance Criteria\n"
    "- [ ] Done\n\n## Files in Scope\n- `src/x.py`\n"
)


def _init_checker(daemon: SpecOrchDaemon) -> None:
    """Ensure daemon has a ReadinessChecker for tests that call _poll_and_run."""
    if daemon._readiness_checker is None:
        daemon._readiness_checker = ReadinessChecker()


def test_daemon_config_from_toml(tmp_path: Path) -> None:
    toml_file = tmp_path / "spec-orch.toml"
    toml_file.write_text(
        """\
[linear]
token_env = "MY_TOKEN"
team_key = "PROJ"
poll_interval_seconds = 30
issue_filter = "all"

[builder]
adapter = "codex_exec"
codex_executable = "/usr/local/bin/codex"

[daemon]
max_concurrent = 2
lockfile_dir = ".locks/"
"""
    )
    cfg = DaemonConfig.from_toml(toml_file)
    assert cfg.linear_token_env == "MY_TOKEN"
    assert cfg.team_key == "PROJ"
    assert cfg.poll_interval_seconds == 30
    assert cfg.issue_filter == "all"
    assert cfg.codex_executable == "/usr/local/bin/codex"
    assert cfg.max_concurrent == 2
    assert cfg.lockfile_dir == ".locks/"


def test_daemon_config_defaults() -> None:
    cfg = DaemonConfig({})
    assert cfg.linear_token_env == "SPEC_ORCH_LINEAR_TOKEN"
    assert cfg.team_key == "SPC"
    assert cfg.poll_interval_seconds == 60
    assert cfg.builder_adapter == "codex_exec"
    assert cfg.max_concurrent == 1


def test_daemon_lockfile_prevents_reprocessing(tmp_path: Path) -> None:
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)

    assert not daemon._is_locked("SPC-1")
    daemon._claim("SPC-1")
    assert daemon._is_locked("SPC-1")


def test_daemon_signal_stops_loop(tmp_path: Path) -> None:
    cfg = DaemonConfig({})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)

    assert daemon._running is True
    daemon._handle_signal(signal.SIGINT, None)
    assert daemon._running is False


def test_daemon_notify_sends_bell(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cfg = DaemonConfig({})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)

    with patch("spec_orch.services.daemon._subprocess.run") as mock_run:
        daemon._notify("SPC-5", True)

    captured = capsys.readouterr()
    assert "\a" in captured.out
    mock_run.assert_called_once()
    args = mock_run.call_args
    assert "osascript" in args[0][0]


def test_daemon_config_planner_fields(tmp_path: Path) -> None:
    toml_file = tmp_path / "spec-orch.toml"
    toml_file.write_text(
        """\
[planner]
model = "openai/gpt-4o"
api_key_env = "MY_KEY"
api_base_env = "MY_BASE"
token_command = "echo test-token"
"""
    )
    cfg = DaemonConfig.from_toml(toml_file)
    assert cfg.planner_model == "openai/gpt-4o"
    assert cfg.planner_api_key_env == "MY_KEY"
    assert cfg.planner_api_base_env == "MY_BASE"
    assert cfg.planner_token_command == "echo test-token"


def test_daemon_config_planner_defaults() -> None:
    cfg = DaemonConfig({})
    assert cfg.planner_model is None
    assert cfg.planner_api_key_env is None
    assert cfg.planner_api_base_env is None
    assert cfg.planner_token_command is None


def test_build_round_orchestrator_wires_command_visual_evaluator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = DaemonConfig(
        {
            "supervisor": {
                "adapter": "litellm",
                "model": "openai/gpt-4o",
                "visual_evaluator": {
                    "adapter": "command",
                    "command": ["{python}", "tools/visual_eval.py"],
                    "timeout_seconds": 30,
                },
            }
        }
    )
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)

    captured: dict[str, object] = {}

    class StubRoundOrchestrator:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        "spec_orch.services.litellm_supervisor_adapter.LiteLLMSupervisorAdapter",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        "spec_orch.services.round_orchestrator.RoundOrchestrator",
        StubRoundOrchestrator,
    )

    orchestrator = daemon._build_round_orchestrator()

    assert isinstance(orchestrator, StubRoundOrchestrator)
    visual_evaluator = captured["visual_evaluator"]
    assert visual_evaluator is not None
    assert visual_evaluator.__class__.__name__ == "CommandVisualEvaluator"


def test_build_round_orchestrator_wires_acceptance_evaluator_and_filer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "spec_orch.services.daemon.LinearClient",
        lambda **kwargs: object(),
    )
    cfg = DaemonConfig(
        {
            "linear": {"team_key": "SON"},
            "supervisor": {
                "adapter": "litellm",
                "model": "openai/gpt-4o",
            },
            "acceptance_evaluator": {
                "adapter": "litellm",
                "model": "minimax/MiniMax-M2.7-highspeed",
                "auto_file_issues": True,
                "min_confidence": 0.91,
                "min_severity": "critical",
            },
        }
    )
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)

    captured: dict[str, object] = {}

    class StubRoundOrchestrator:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    captured_supervisor: dict[str, object] = {}
    captured_acceptance: dict[str, object] = {}

    monkeypatch.setattr(
        "spec_orch.services.litellm_supervisor_adapter.LiteLLMSupervisorAdapter",
        lambda **kwargs: captured_supervisor.update(kwargs) or object(),
    )
    monkeypatch.setattr(
        "spec_orch.services.acceptance.litellm_acceptance_evaluator.LiteLLMAcceptanceEvaluator",
        lambda **kwargs: captured_acceptance.update(kwargs) or object(),
    )
    monkeypatch.setattr(
        "spec_orch.services.acceptance.linear_filing.LinearAcceptanceFiler",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        "spec_orch.services.round_orchestrator.RoundOrchestrator",
        StubRoundOrchestrator,
    )

    orchestrator = daemon._build_round_orchestrator()

    assert isinstance(orchestrator, StubRoundOrchestrator)
    assert captured["acceptance_evaluator"] is not None
    assert captured["acceptance_filer"] is not None
    assert captured_supervisor["api_type"] == "anthropic"
    assert captured_acceptance["api_type"] == "anthropic"


def test_build_round_orchestrator_passes_acpx_worker_robustness_knobs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = DaemonConfig(
        {
            "builder": {
                "adapter": "acpx_opencode",
                "startup_timeout_seconds": 17,
                "idle_progress_timeout_seconds": 45,
                "completion_quiet_period_seconds": 3,
                "max_retries": 2,
                "max_turns_per_session": 7,
                "max_session_age_seconds": 900,
            },
            "supervisor": {
                "adapter": "litellm",
                "model": "openai/gpt-4o",
            },
        }
    )
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)

    captured_orchestrator: dict[str, object] = {}
    captured_factory: dict[str, object] = {}

    class StubRoundOrchestrator:
        def __init__(self, **kwargs):
            captured_orchestrator.update(kwargs)

    monkeypatch.setattr(
        "spec_orch.services.litellm_supervisor_adapter.LiteLLMSupervisorAdapter",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        "spec_orch.services.workers.acpx_worker_handle_factory.AcpxWorkerHandleFactory",
        lambda **kwargs: captured_factory.update(kwargs) or object(),
    )
    monkeypatch.setattr(
        "spec_orch.services.round_orchestrator.RoundOrchestrator",
        StubRoundOrchestrator,
    )

    orchestrator = daemon._build_round_orchestrator()

    assert isinstance(orchestrator, StubRoundOrchestrator)
    assert captured_orchestrator["worker_factory"] is not None
    assert captured_factory["agent"] == "opencode"
    assert captured_factory["startup_timeout_seconds"] == 17.0
    assert captured_factory["idle_progress_timeout_seconds"] == 45.0
    assert captured_factory["completion_quiet_period_seconds"] == 3.0
    assert captured_factory["max_retries"] == 2
    assert captured_factory["max_turns_per_session"] == 7
    assert captured_factory["max_session_age_seconds"] == 900.0


def test_daemon_poll_and_run_skips_locked(tmp_path: Path) -> None:
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)

    mock_client = MagicMock()
    mock_client.list_issues.return_value = [{"identifier": "SPC-10", "description": _COMPLETE_DESC}]
    mock_controller = MagicMock()

    _init_checker(daemon)
    daemon._claim("SPC-10")
    daemon._poll_and_run(mock_client, mock_controller)

    mock_controller.advance_to_completion.assert_not_called()


def test_daemon_poll_and_run_processes_new_issue(tmp_path: Path) -> None:
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)
    daemon._write_back = MagicMock()

    mock_client = MagicMock()
    mock_client.list_issues.return_value = [
        {"id": "uuid-11", "identifier": "SPC-11", "description": _COMPLETE_DESC}
    ]

    mock_gate = MagicMock()
    mock_gate.mergeable = True
    mock_gate.failed_conditions = []
    mock_result = MagicMock()
    mock_result.gate = mock_gate
    mock_result.state = RunState.ACCEPTED

    mock_controller = MagicMock()
    mock_controller.advance_to_completion.return_value = mock_result

    _init_checker(daemon)
    daemon._poll_and_run(mock_client, mock_controller)

    mock_controller.advance_to_completion.assert_called_once_with("SPC-11", flow_type=None)
    assert "SPC-11" in daemon._processed
    daemon._write_back.post_run_summary.assert_called_once()


def test_daemon_poll_and_run_releases_non_terminal(tmp_path: Path) -> None:
    """Non-terminal states should release the lock so the next poll re-advances."""
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)
    daemon._write_back = MagicMock()

    mock_client = MagicMock()
    mock_client.list_issues.return_value = [
        {"id": "uuid-12", "identifier": "SPC-12", "description": _COMPLETE_DESC}
    ]

    mock_gate = MagicMock()
    mock_gate.mergeable = False
    mock_gate.failed_conditions = ["pre_build"]
    mock_result = MagicMock()
    mock_result.gate = mock_gate
    mock_result.state = RunState.SPEC_DRAFTING

    mock_controller = MagicMock()
    mock_controller.advance_to_completion.return_value = mock_result

    _init_checker(daemon)
    daemon._poll_and_run(mock_client, mock_controller)

    mock_controller.advance_to_completion.assert_called_once_with("SPC-12", flow_type=None)
    assert "SPC-12" not in daemon._processed
    assert not daemon._is_locked("SPC-12")


def test_daemon_poll_and_run_marks_gate_evaluated_as_processed(tmp_path: Path) -> None:
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)
    daemon._write_back = MagicMock()

    mock_client = MagicMock()
    mock_client.list_issues.return_value = [
        {"id": "uuid-13", "identifier": "SPC-13", "description": _COMPLETE_DESC}
    ]

    mock_gate = MagicMock()
    mock_gate.mergeable = False
    mock_gate.failed_conditions = ["human_acceptance"]
    mock_result = MagicMock()
    mock_result.gate = mock_gate
    mock_result.state = RunState.GATE_EVALUATED

    mock_controller = MagicMock()
    mock_controller.advance_to_completion.return_value = mock_result

    _init_checker(daemon)
    daemon._poll_and_run(mock_client, mock_controller)

    mock_controller.advance_to_completion.assert_called_once_with("SPC-13", flow_type=None)
    assert "SPC-13" in daemon._processed


def test_daemon_auto_create_pr(tmp_path: Path) -> None:
    """Daemon should attempt PR creation when reaching GATE_EVALUATED."""
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)

    mock_gate = MagicMock()
    mock_gate.mergeable = True
    mock_gate.failed_conditions = []
    mock_result = MagicMock()
    mock_result.state = RunState.GATE_EVALUATED
    mock_result.gate = mock_gate
    mock_result.issue.title = "Test Issue"
    mock_result.issue.issue_id = "SPC-20"
    mock_result.workspace = tmp_path

    with patch("spec_orch.services.daemon.GitHubPRService") as MockGH:
        mock_gh = MockGH.return_value
        mock_gh._current_branch.return_value = "feat/spc-20"
        mock_gh.check_mergeable.return_value = {"mergeable": True, "conflicting_files": []}
        mock_gh.create_pr.return_value = "https://github.com/pr/99"
        daemon._auto_create_pr("SPC-20", mock_result)
        mock_gh.create_pr.assert_called_once()
