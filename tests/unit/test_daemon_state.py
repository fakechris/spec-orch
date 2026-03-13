"""Tests for daemon state persistence and daemon_installer."""

from __future__ import annotations

import json
from pathlib import Path

from spec_orch.services.daemon import DaemonConfig, SpecOrchDaemon
from spec_orch.services.daemon_installer import generate_service_file


def test_state_persistence_round_trip(tmp_path: Path) -> None:
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)
    daemon._processed.add("SPC-1")
    daemon._processed.add("SPC-2")
    daemon._triaged.add("SPC-3")
    daemon._save_state()

    state_path = tmp_path / "locks" / "daemon_state.json"
    assert state_path.exists()
    data = json.loads(state_path.read_text())
    assert set(data["processed"]) == {"SPC-1", "SPC-2"}
    assert data["triaged"] == ["SPC-3"]
    assert "last_poll" in data


def test_state_loaded_on_init(tmp_path: Path) -> None:
    locks_dir = tmp_path / "locks"
    locks_dir.mkdir()
    state_file = locks_dir / "daemon_state.json"
    state_file.write_text(
        json.dumps(
            {
                "processed": ["SPC-A", "SPC-B"],
                "triaged": ["SPC-C"],
                "last_poll": "2026-01-01T00:00:00Z",
            }
        )
    )

    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(locks_dir)}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)
    assert "SPC-A" in daemon._processed
    assert "SPC-B" in daemon._processed
    assert "SPC-C" in daemon._triaged


def test_state_empty_on_missing_file(tmp_path: Path) -> None:
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)
    assert daemon._processed == set()
    assert daemon._triaged == set()


def test_state_handles_corrupt_json(tmp_path: Path) -> None:
    locks_dir = tmp_path / "locks"
    locks_dir.mkdir()
    (locks_dir / "daemon_state.json").write_text("NOT JSON")

    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(locks_dir)}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)
    assert daemon._processed == set()


def test_generate_service_file_darwin(tmp_path: Path, monkeypatch: object) -> None:
    import spec_orch.services.daemon_installer as mod

    monkeypatch.setattr(mod, "_detect_platform", lambda: "darwin")
    content, target = generate_service_file(
        repo_root=tmp_path,
        config_path=tmp_path / "spec-orch.toml",
    )
    assert "com.specorch.daemon" in content
    assert "LaunchAgents" in target
    assert "<plist" in content


def test_generate_service_file_linux(tmp_path: Path, monkeypatch: object) -> None:
    import spec_orch.services.daemon_installer as mod

    monkeypatch.setattr(mod, "_detect_platform", lambda: "linux")
    content, target = generate_service_file(
        repo_root=tmp_path,
        config_path=tmp_path / "spec-orch.toml",
    )
    assert "[Unit]" in content
    assert "[Service]" in content
    assert "systemd" in target
