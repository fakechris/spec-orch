"""Tests for daemon state persistence and daemon_installer."""

from __future__ import annotations

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

    db_path = tmp_path / "locks" / "daemon_state.db"
    assert db_path.exists()
    data = SpecOrchDaemon.read_state(tmp_path, str(tmp_path / "locks"))
    assert set(data["processed"]) == {"SPC-1", "SPC-2"}
    assert data["triaged"] == ["SPC-3"]
    assert "last_poll" in data


def test_state_loaded_on_init(tmp_path: Path) -> None:
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon1 = SpecOrchDaemon(config=cfg, repo_root=tmp_path)
    daemon1._processed.update({"SPC-A", "SPC-B"})
    daemon1._triaged.add("SPC-C")
    daemon1._save_state()

    locks_dir = tmp_path / "locks"
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(locks_dir)}})
    daemon2 = SpecOrchDaemon(config=cfg, repo_root=tmp_path)
    assert "SPC-A" in daemon2._processed
    assert "SPC-B" in daemon2._processed
    assert "SPC-C" in daemon2._triaged


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


def test_execution_intent_queue_round_trip(tmp_path: Path) -> None:
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)

    daemon._state_store.enqueue_execution_intent(
        issue_id="SPC-QUEUE",
        raw_issue={"id": "uuid-queue", "identifier": "SPC-QUEUE"},
        is_hotfix=True,
    )

    intents = daemon._state_store.list_execution_intents()
    assert len(intents) == 1
    assert intents[0]["issue_id"] == "SPC-QUEUE"
    assert intents[0]["raw_issue"]["id"] == "uuid-queue"
    assert intents[0]["is_hotfix"] is True

    daemon._state_store.delete_execution_intent("SPC-QUEUE")
    assert daemon._state_store.list_execution_intents() == []


def test_issue_claim_rejects_other_owner_until_lease_expires(tmp_path: Path) -> None:
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)

    assert daemon._state_store.try_claim_issue(
        "SPC-CLAIM",
        owner="daemon-a",
        lease_seconds=60,
        now=100.0,
    )
    assert not daemon._state_store.try_claim_issue(
        "SPC-CLAIM",
        owner="daemon-b",
        lease_seconds=60,
        now=101.0,
    )
    assert daemon._state_store.try_claim_issue(
        "SPC-CLAIM",
        owner="daemon-b",
        lease_seconds=60,
        now=161.0,
    )


def test_daemon_lock_rejects_second_owner_until_lease_expires(tmp_path: Path) -> None:
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)

    assert daemon._state_store.acquire_daemon_lock(
        owner="daemon-a",
        pid=111,
        lease_seconds=30,
        now=10.0,
    )
    assert not daemon._state_store.acquire_daemon_lock(
        owner="daemon-b",
        pid=222,
        lease_seconds=30,
        now=20.0,
    )
    assert daemon._state_store.acquire_daemon_lock(
        owner="daemon-b",
        pid=222,
        lease_seconds=30,
        now=41.0,
    )


def test_pop_next_execution_intent_removes_only_popped_issue(tmp_path: Path) -> None:
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)

    daemon._state_store.enqueue_execution_intent(
        issue_id="SPC-1",
        raw_issue={"id": "uid-1"},
        is_hotfix=False,
        enqueued_at=10.0,
    )
    daemon._state_store.enqueue_execution_intent(
        issue_id="SPC-2",
        raw_issue={"id": "uid-2"},
        is_hotfix=True,
        enqueued_at=20.0,
    )

    popped = daemon._state_store.pop_next_execution_intent()

    assert popped is not None
    assert popped["issue_id"] == "SPC-1"
    assert daemon._state_store.list_execution_intents() == [
        {
            "issue_id": "SPC-2",
            "raw_issue": {"id": "uid-2"},
            "is_hotfix": True,
            "enqueued_at": 20.0,
        }
    ]


# ── Phase 14 tests: Daemon resilience ────────────────────────────────


def test_retry_counts_persisted(tmp_path: Path) -> None:
    """SON-145: Retry counts are saved and loaded across daemon restarts."""
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)
    daemon._retry_counts["SPC-1"] = 2
    daemon._save_state()

    daemon2 = SpecOrchDaemon(config=cfg, repo_root=tmp_path)
    assert daemon2._retry_counts["SPC-1"] == 2


def test_dead_letter_persisted(tmp_path: Path) -> None:
    """SON-146: Dead letter set is saved and loaded."""
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)
    daemon._dead_letter.add("SPC-DEAD")
    daemon._save_state()

    daemon2 = SpecOrchDaemon(config=cfg, repo_root=tmp_path)
    assert "SPC-DEAD" in daemon2._dead_letter


def test_in_progress_persisted(tmp_path: Path) -> None:
    """SON-144: In-progress issues are saved for restart recovery."""
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)
    daemon._in_progress.add("SPC-WIP")
    daemon._save_state()

    daemon2 = SpecOrchDaemon(config=cfg, repo_root=tmp_path)
    assert "SPC-WIP" in daemon2._in_progress


def test_is_hotfix_detects_labels(tmp_path: Path) -> None:
    """SON-147: _is_hotfix returns True when issue has hotfix labels."""
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)

    assert daemon._is_hotfix({"labels": {"nodes": [{"name": "hotfix"}]}}) is True
    assert daemon._is_hotfix({"labels": {"nodes": [{"name": "P0"}]}}) is True
    assert daemon._is_hotfix({"labels": {"nodes": [{"name": "feature"}]}}) is False
    assert daemon._is_hotfix({"labels": {"nodes": []}}) is False
    assert daemon._is_hotfix({}) is False


def test_should_backoff_no_retries(tmp_path: Path) -> None:
    """SON-145: No backoff when retry count is zero."""
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)
    assert daemon._should_backoff("SPC-1") is False


def test_should_backoff_active(tmp_path: Path) -> None:
    """SON-145: Backoff is active when retry_at is in the future."""
    import time

    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)
    daemon._retry_counts["SPC-1"] = 1
    daemon._retry_at["SPC-1"] = time.time() + 3600
    assert daemon._should_backoff("SPC-1") is True


def test_should_backoff_expired(tmp_path: Path) -> None:
    """SON-145: Backoff is not active when retry_at is in the past."""
    import time

    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)
    daemon._retry_counts["SPC-1"] = 1
    daemon._retry_at["SPC-1"] = time.time() - 10
    assert daemon._should_backoff("SPC-1") is False


def test_process_lock_prevents_second_daemon_instance(tmp_path: Path) -> None:
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon1 = SpecOrchDaemon(config=cfg, repo_root=tmp_path)
    daemon2 = SpecOrchDaemon(config=cfg, repo_root=tmp_path)

    daemon1._acquire_process_lock()
    try:
        try:
            daemon2._acquire_process_lock()
        except RuntimeError as exc:
            assert "already holds the process lock" in str(exc)
        else:
            raise AssertionError("expected process lock acquisition to fail")
    finally:
        daemon1._release_process_lock()


def test_record_failure_increments_count(tmp_path: Path) -> None:
    """SON-145/146: _record_failure increments count and moves to dead letter at max."""
    from unittest.mock import MagicMock

    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks"), "max_retries": 2}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)
    mock_client = MagicMock()

    daemon._record_failure("SPC-1", "err1", mock_client, "uid1")
    assert daemon._retry_counts["SPC-1"] == 1
    assert "SPC-1" not in daemon._dead_letter

    daemon._record_failure("SPC-1", "err2", mock_client, "uid1")
    assert "SPC-1" in daemon._dead_letter
    assert "SPC-1" not in daemon._retry_counts
    mock_client.add_comment.assert_called_once()
    mock_client.add_label.assert_called_once()


def test_daemon_config_retry_defaults() -> None:
    """SON-145/147: DaemonConfig exposes retry and hotfix settings."""
    cfg = DaemonConfig({})
    assert cfg.max_retries == 3
    assert cfg.retry_base_delay == 60
    assert "hotfix" in cfg.hotfix_labels
    assert "P0" in cfg.hotfix_labels


def test_daemon_config_custom_values() -> None:
    """SON-145/147: DaemonConfig reads custom values from TOML."""
    cfg = DaemonConfig(
        {
            "daemon": {
                "max_retries": 5,
                "retry_base_delay_seconds": 120,
                "hotfix_labels": ["emergency"],
            }
        }
    )
    assert cfg.max_retries == 5
    assert cfg.retry_base_delay == 120
    assert cfg.hotfix_labels == ["emergency"]


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
