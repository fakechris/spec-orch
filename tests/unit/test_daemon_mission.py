"""Tests for daemon mission-level plan execution."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from spec_orch.services.daemon import DaemonConfig, SpecOrchDaemon
from spec_orch.services.readiness_checker import ReadinessChecker

_COMPLETE_DESC = (
    "## Goal\nDo something.\n\n## Acceptance Criteria\n"
    "- [ ] Done\n\n## Files in Scope\n- `src/x.py`\n"
)

_MISSION_DESC = (
    "## Goal\nExecute mission plan.\n\n## Acceptance Criteria\n"
    "- [ ] All waves pass\n\n## Files in Scope\n- `src/x.py`\n"
    "\nReferences plan.json for mission-level execution."
)


def _make_plan_json(repo_root: Path, mission_id: str) -> Path:
    plan_dir = repo_root / "docs" / "specs" / mission_id
    plan_dir.mkdir(parents=True)
    plan = {
        "plan_id": "plan-1",
        "mission_id": mission_id,
        "waves": [
            {
                "wave_number": 1,
                "description": "Foundation",
                "work_packets": [
                    {
                        "packet_id": "pkt-1",
                        "title": "Setup",
                        "spec_section": "1",
                        "files_in_scope": ["src/x.py"],
                        "acceptance_criteria": ["works"],
                    }
                ],
            }
        ],
        "status": "approved",
    }
    plan_path = plan_dir / "plan.json"
    plan_path.write_text(json.dumps(plan))
    return plan_path


def test_detect_mission_from_plan_file(tmp_path: Path) -> None:
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)

    _make_plan_json(tmp_path, "SPC-20")
    result = daemon._detect_mission("SPC-20", {"description": "anything"})
    assert result == "SPC-20"


def test_detect_mission_from_description(tmp_path: Path) -> None:
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)

    _make_plan_json(tmp_path, "SPC-21")
    result = daemon._detect_mission(
        "SPC-21", {"description": "Uses plan.json for execution"}
    )
    assert result == "SPC-21"


def test_detect_mission_returns_none_without_plan(tmp_path: Path) -> None:
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)

    result = daemon._detect_mission("SPC-22", {"description": "no plan"})
    assert result is None


def test_execute_mission_success(tmp_path: Path) -> None:
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)
    daemon._readiness_checker = ReadinessChecker()

    _make_plan_json(tmp_path, "SPC-30")
    client = MagicMock()

    mock_result = MagicMock()
    mock_result.is_success.return_value = True
    mock_result.total_duration = 5.0
    mock_result.wave_results = [
        MagicMock(wave_id=1, all_succeeded=True, packet_results=[], failed_packets=[]),
    ]

    with patch(
        "spec_orch.services.parallel_run_controller.ParallelRunController"
    ) as MockPRC:
        mock_prc = MockPRC.return_value
        mock_prc.run_plan.return_value = mock_result
        MockPRC.load_plan.return_value = MagicMock(waves=[])

        daemon._execute_mission("SPC-30", "SPC-30", {"id": "uid-30"}, client)

    assert "SPC-30" in daemon._processed
    client.update_issue_state.assert_called_with("uid-30", "In Review")


def test_execute_mission_failure(tmp_path: Path) -> None:
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)
    daemon._readiness_checker = ReadinessChecker()

    _make_plan_json(tmp_path, "SPC-31")
    client = MagicMock()

    mock_result = MagicMock()
    mock_result.is_success.return_value = False
    mock_result.total_duration = 3.0
    mock_result.wave_results = [
        MagicMock(
            wave_id=1,
            all_succeeded=False,
            packet_results=[MagicMock(packet_id="pkt-1", exit_code=1)],
            failed_packets=[MagicMock(packet_id="pkt-1", exit_code=1)],
        ),
    ]

    with patch(
        "spec_orch.services.parallel_run_controller.ParallelRunController"
    ) as MockPRC:
        mock_prc = MockPRC.return_value
        mock_prc.run_plan.return_value = mock_result
        MockPRC.load_plan.return_value = MagicMock(waves=[])

        daemon._execute_mission("SPC-31", "SPC-31", {"id": "uid-31"}, client)

    assert "SPC-31" not in daemon._processed
    client.update_issue_state.assert_called_once_with("uid-31", "Ready")


def test_poll_routes_to_mission_when_plan_exists(tmp_path: Path) -> None:
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)
    daemon._write_back = MagicMock()
    daemon._readiness_checker = ReadinessChecker()

    _make_plan_json(tmp_path, "SPC-40")

    mock_client = MagicMock()
    mock_client.list_issues.return_value = [
        {"id": "uid-40", "identifier": "SPC-40", "description": _MISSION_DESC},
    ]

    mock_controller = MagicMock()

    mock_plan_result = MagicMock()
    mock_plan_result.is_success.return_value = True
    mock_plan_result.total_duration = 1.0
    mock_plan_result.wave_results = []

    with patch(
        "spec_orch.services.parallel_run_controller.ParallelRunController"
    ) as MockPRC:
        mock_prc = MockPRC.return_value
        mock_prc.run_plan.return_value = mock_plan_result
        MockPRC.load_plan.return_value = MagicMock(waves=[])

        daemon._poll_and_run(mock_client, mock_controller)

    mock_controller.advance_to_completion.assert_not_called()
    assert "SPC-40" in daemon._processed
