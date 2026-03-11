from __future__ import annotations

import signal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from spec_orch.domain.models import RunState
from spec_orch.services.daemon import DaemonConfig, SpecOrchDaemon


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

    with patch("subprocess.run") as mock_run:
        daemon._notify("SPC-5", True)

    captured = capsys.readouterr()
    assert "\a" in captured.out
    mock_run.assert_called_once()
    args = mock_run.call_args
    assert "osascript" in args[0][0]


def test_daemon_poll_and_run_skips_locked(tmp_path: Path) -> None:
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)

    mock_client = MagicMock()
    mock_client.list_issues.return_value = [{"identifier": "SPC-10"}]
    mock_controller = MagicMock()

    daemon._claim("SPC-10")
    daemon._poll_and_run(mock_client, mock_controller)

    mock_controller.advance.assert_not_called()


def test_daemon_poll_and_run_processes_new_issue(tmp_path: Path) -> None:
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)

    mock_client = MagicMock()
    mock_client.list_issues.return_value = [{"identifier": "SPC-11"}]

    mock_gate = MagicMock()
    mock_gate.mergeable = True
    mock_gate.failed_conditions = []
    mock_result = MagicMock()
    mock_result.gate = mock_gate
    mock_result.state = RunState.ACCEPTED

    mock_controller = MagicMock()
    mock_controller.advance.return_value = mock_result

    daemon._poll_and_run(mock_client, mock_controller)

    mock_controller.advance.assert_called_once_with("SPC-11")
    assert "SPC-11" in daemon._processed


def test_daemon_poll_and_run_releases_non_terminal(tmp_path: Path) -> None:
    """Non-terminal states should release the lock so the next poll re-advances."""
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)

    mock_client = MagicMock()
    mock_client.list_issues.return_value = [{"identifier": "SPC-12"}]

    mock_gate = MagicMock()
    mock_gate.mergeable = False
    mock_gate.failed_conditions = ["pre_build"]
    mock_result = MagicMock()
    mock_result.gate = mock_gate
    mock_result.state = RunState.SPEC_DRAFTING

    mock_controller = MagicMock()
    mock_controller.advance.return_value = mock_result

    daemon._poll_and_run(mock_client, mock_controller)

    mock_controller.advance.assert_called_once_with("SPC-12")
    assert "SPC-12" not in daemon._processed
    assert not daemon._is_locked("SPC-12")


def test_daemon_poll_and_run_marks_gate_evaluated_as_processed(tmp_path: Path) -> None:
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)

    mock_client = MagicMock()
    mock_client.list_issues.return_value = [{"identifier": "SPC-13"}]

    mock_gate = MagicMock()
    mock_gate.mergeable = False
    mock_gate.failed_conditions = ["human_acceptance"]
    mock_result = MagicMock()
    mock_result.gate = mock_gate
    mock_result.state = RunState.GATE_EVALUATED

    mock_controller = MagicMock()
    mock_controller.advance.return_value = mock_result

    daemon._poll_and_run(mock_client, mock_controller)

    mock_controller.advance.assert_called_once_with("SPC-13")
    assert "SPC-13" in daemon._processed
