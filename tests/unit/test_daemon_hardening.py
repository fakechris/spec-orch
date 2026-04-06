"""Tests for daemon hardening (SON-46): heartbeat, DLQ, crash recovery."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from spec_orch.services.daemon import DaemonConfig, SpecOrchDaemon
from spec_orch.services.daemon_state_store import DaemonStateStore


def _minimal_config() -> DaemonConfig:
    return DaemonConfig(
        {
            "linear": {"token_env": "FAKE_TOKEN", "team_key": "TST"},
            "builder": {"adapter": "codex_exec"},
            "daemon": {"lockfile_dir": ".test_locks/"},
        }
    )


def _make_daemon(tmp_path: Path) -> SpecOrchDaemon:
    cfg = _minimal_config()
    cfg.lockfile_dir = str(tmp_path / ".locks") + "/"
    with patch.dict("os.environ", {"FAKE_TOKEN": "fake"}):
        d = SpecOrchDaemon.__new__(SpecOrchDaemon)
        d.config = cfg
        d.repo_root = tmp_path
        d._running = True
        d._lockdir = tmp_path / ".locks"
        d._lockdir.mkdir(parents=True, exist_ok=True)
        d._state_store = DaemonStateStore(d._lockdir)
        d._state_path = d._lockdir / SpecOrchDaemon.STATE_FILE
        d._processed = set()
        d._triaged = set()
        d._last_poll = ""
        d._pr_commits = {}
        d._retry_counts = {}
        d._retry_at = {}
        d._dead_letter = set()
        d._in_progress = set()
        d._reaction_marks = set()
        d._process_lock_owner = f"test:{id(d)}"
        d._consecutive_loop_errors = 0
        d._executor_pool = None  # not needed for hardening tests
        d._execution_futures: dict[str, object] = {}

        from spec_orch.services.event_bus import get_event_bus

        d._event_bus = get_event_bus()
    return d


def test_heartbeat_write_and_read(tmp_path: Path) -> None:
    d = _make_daemon(tmp_path)
    d._write_heartbeat(status="healthy")

    hb = SpecOrchDaemon.read_heartbeat(tmp_path, str(tmp_path / ".locks") + "/")
    assert hb["status"] == "healthy"
    assert "pid" in hb
    assert "age_seconds" in hb


def test_heartbeat_stale_detection(tmp_path: Path) -> None:
    d = _make_daemon(tmp_path)
    d._write_heartbeat(status="healthy")

    hb_path = d._lockdir / SpecOrchDaemon.HEARTBEAT_FILE
    data = json.loads(hb_path.read_text())
    data["epoch"] = time.time() - 600
    hb_path.write_text(json.dumps(data))

    hb = SpecOrchDaemon.read_heartbeat(tmp_path, str(tmp_path / ".locks") + "/")
    assert hb["status"] == "stale"


def test_heartbeat_not_running(tmp_path: Path) -> None:
    hb = SpecOrchDaemon.read_heartbeat(tmp_path, ".nonexistent/")
    assert hb["status"] == "not_running"


def test_dead_letter_retry(tmp_path: Path) -> None:
    d = _make_daemon(tmp_path)
    d._dead_letter.add("SON-99")
    d._processed.add("SON-99")
    d._retry_counts["SON-99"] = 3
    d._save_state()

    assert d.retry_dead_letter("SON-99")
    assert "SON-99" not in d._dead_letter
    assert "SON-99" not in d._processed
    assert "SON-99" not in d._retry_counts


def test_dead_letter_retry_not_in_dlq(tmp_path: Path) -> None:
    d = _make_daemon(tmp_path)
    assert not d.retry_dead_letter("NOT-THERE")


def test_clear_dead_letter(tmp_path: Path) -> None:
    d = _make_daemon(tmp_path)
    d._dead_letter = {"A", "B", "C"}
    count = d.clear_dead_letter()
    assert count == 3
    assert len(d._dead_letter) == 0


def test_get_dead_letter_issues(tmp_path: Path) -> None:
    d = _make_daemon(tmp_path)
    d._dead_letter = {"Z-1", "A-2"}
    assert d.get_dead_letter_issues() == ["A-2", "Z-1"]


def test_emit_error_event(tmp_path: Path) -> None:
    d = _make_daemon(tmp_path)
    d._emit_error_event("test.error", "something broke", issue_id="SON-1")

    events = d._event_bus.query_history(limit=5)
    found = [e for e in events if e.payload.get("kind") == "test.error"]
    assert len(found) >= 1
    assert found[-1].payload["message"] == "something broke"


def test_record_failure_emits_event(tmp_path: Path) -> None:
    d = _make_daemon(tmp_path)
    d._record_failure("SON-50", "timeout", MagicMock(), "uid-50")
    events = d._event_bus.query_history(limit=10)
    found = [e for e in events if e.payload.get("kind") == "daemon.issue_failed"]
    assert len(found) >= 1
    assert found[-1].payload["issue_id"] == "SON-50"


def test_run_already_completed_detects_terminal(tmp_path: Path) -> None:
    d = _make_daemon(tmp_path)
    controller = MagicMock()
    ws = tmp_path / ".spec_orch_runs" / "SON-77"
    controller.workspace_service.issue_workspace_path.return_value = ws

    art = ws / "run_artifact"
    art.mkdir(parents=True)
    (art / "conclusion.json").write_text(json.dumps({"state": "gate_evaluated", "mergeable": True}))

    assert d._run_already_completed("SON-77", controller)


def test_run_already_completed_no_artifact(tmp_path: Path) -> None:
    d = _make_daemon(tmp_path)
    controller = MagicMock()
    ws = tmp_path / ".spec_orch_runs" / "SON-88"
    controller.workspace_service.issue_workspace_path.return_value = ws

    assert not d._run_already_completed("SON-88", controller)


def test_resume_skips_completed_runs(tmp_path: Path) -> None:
    d = _make_daemon(tmp_path)
    d._in_progress = {"SON-77"}

    controller = MagicMock()
    ws = tmp_path / ".spec_orch_runs" / "SON-77"
    controller.workspace_service.issue_workspace_path.return_value = ws
    art = ws / "run_artifact"
    art.mkdir(parents=True)
    (art / "conclusion.json").write_text(json.dumps({"state": "merged", "mergeable": True}))

    d.resume_in_progress(controller)
    assert "SON-77" not in d._in_progress
    assert "SON-77" in d._processed
    controller.advance_to_completion.assert_not_called()


def test_read_state_static(tmp_path: Path) -> None:
    d = _make_daemon(tmp_path)
    d._processed = {"X-1", "X-2"}
    d._dead_letter = {"Y-1"}
    d._save_state()

    state = SpecOrchDaemon.read_state(tmp_path, str(tmp_path / ".locks") + "/")
    assert "X-1" in state.get("processed", [])
    assert "Y-1" in state.get("dead_letter", [])


def test_read_state_static_does_not_create_lockdir_when_missing(tmp_path: Path) -> None:
    lockdir = tmp_path / ".missing-locks"

    state = SpecOrchDaemon.read_state(tmp_path, str(lockdir) + "/")

    assert state == {}
    assert not lockdir.exists()


def test_read_state_static_does_not_migrate_legacy_json(tmp_path: Path) -> None:
    lockdir = tmp_path / ".locks"
    lockdir.mkdir()
    legacy = lockdir / "daemon_state.json"
    legacy.write_text(json.dumps({"processed": ["LEG-1"], "dead_letter": ["LEG-2"]}))

    state = SpecOrchDaemon.read_state(tmp_path, str(lockdir) + "/")

    assert state["processed"] == ["LEG-1"]
    assert state["dead_letter"] == ["LEG-2"]
    assert legacy.exists()
    assert not (lockdir / "daemon_state.db").exists()
