from __future__ import annotations

from typer.testing import CliRunner

from spec_orch.cli import app


def test_daemon_status_reports_no_persisted_state_when_read_state_empty(monkeypatch) -> None:
    monkeypatch.setattr(
        "spec_orch.services.daemon_installer.service_status",
        lambda label: {"platform": "darwin", "installed": "yes", "running": "no"},
    )
    monkeypatch.setattr(
        "spec_orch.services.daemon.SpecOrchDaemon.read_state",
        lambda repo_root, lockfile_dir=".spec_orch_locks/": {},
    )

    result = CliRunner().invoke(app, ["daemon", "status"])

    assert result.exit_code == 0
    assert "State:     no persisted state found" in result.stdout


def test_daemon_status_json_omits_state_error_when_read_state_returns_empty(monkeypatch) -> None:
    monkeypatch.setattr(
        "spec_orch.services.daemon_installer.service_status",
        lambda label: {"platform": "darwin", "installed": "yes", "running": "no"},
    )
    monkeypatch.setattr(
        "spec_orch.services.daemon.SpecOrchDaemon.read_state",
        lambda repo_root, lockfile_dir=".spec_orch_locks/": {},
    )

    result = CliRunner().invoke(app, ["daemon", "status", "--json"])

    assert result.exit_code == 0
    assert '"state_error"' not in result.stdout
