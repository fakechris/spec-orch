"""Tests for Mission model and MissionService."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from spec_orch.cli import app
from spec_orch.domain.models import Mission, MissionStatus
from spec_orch.services.lifecycle_manager import MissionLifecycleManager, MissionPhase
from spec_orch.services.mission_service import MissionService


def test_mission_defaults():
    m = Mission(mission_id="test-1", title="Test Mission")
    assert m.status == MissionStatus.DRAFTING
    assert m.approved_at is None
    assert m.completed_at is None


def test_create_mission(tmp_path: Path):
    svc = MissionService(repo_root=tmp_path)
    m = svc.create_mission("Auth Revamp", mission_id="auth-revamp")

    assert m.mission_id == "auth-revamp"
    assert m.title == "Auth Revamp"
    assert m.status == MissionStatus.DRAFTING

    spec_file = tmp_path / m.spec_path
    assert spec_file.exists()
    assert "# Auth Revamp" in spec_file.read_text()

    meta_path = tmp_path / "docs/specs/auth-revamp/mission.json"
    assert meta_path.exists()


def test_create_mission_auto_id(tmp_path: Path):
    svc = MissionService(repo_root=tmp_path)
    m = svc.create_mission("Add User Auth")
    assert "add-user-auth" in m.mission_id


def test_create_mission_with_criteria(tmp_path: Path):
    svc = MissionService(repo_root=tmp_path)
    m = svc.create_mission(
        "New Feature",
        mission_id="new-feat",
        acceptance_criteria=["Tests pass", "Docs updated"],
        constraints=["No breaking changes"],
    )
    spec_text = (tmp_path / m.spec_path).read_text()
    assert "- Tests pass" in spec_text
    assert "- No breaking changes" in spec_text


def test_approve_mission(tmp_path: Path):
    svc = MissionService(repo_root=tmp_path)
    svc.create_mission("Test", mission_id="test-1")
    m = svc.approve_mission("test-1")
    assert m.status == MissionStatus.APPROVED
    assert m.approved_at is not None
    mgr = MissionLifecycleManager(tmp_path)
    state = mgr.get_state("test-1")
    assert state is not None
    assert state.phase == MissionPhase.APPROVED


def test_get_mission(tmp_path: Path):
    svc = MissionService(repo_root=tmp_path)
    svc.create_mission("Test", mission_id="test-1")
    m = svc.get_mission("test-1")
    assert m.mission_id == "test-1"


def test_get_mission_unknown_status_falls_back_to_drafting(tmp_path: Path, caplog) -> None:
    svc = MissionService(repo_root=tmp_path)
    mission_dir = tmp_path / "docs" / "specs" / "test-unknown"
    mission_dir.mkdir(parents=True)
    (mission_dir / "mission.json").write_text(
        """
{
  "mission_id": "test-unknown",
  "title": "Test Unknown",
  "status": "mystery_status",
  "spec_path": "docs/specs/test-unknown/spec.md",
  "acceptance_criteria": [],
  "constraints": [],
  "interface_contracts": [],
  "created_at": "2026-04-03T00:00:00+00:00",
  "approved_at": null,
  "completed_at": null
}
""".strip()
        + "\n"
    )
    (mission_dir / "spec.md").write_text("# Test Unknown\n")

    mission = svc.get_mission("test-unknown")

    assert mission.status == MissionStatus.DRAFTING
    assert "unknown mission status" in caplog.text.lower()


def test_get_mission_not_found(tmp_path: Path):
    svc = MissionService(repo_root=tmp_path)
    with pytest.raises(FileNotFoundError):
        svc.get_mission("nonexistent")


def test_list_missions(tmp_path: Path):
    svc = MissionService(repo_root=tmp_path)
    svc.create_mission("First", mission_id="first")
    svc.create_mission("Second", mission_id="second")
    missions = svc.list_missions()
    assert len(missions) == 2
    ids = {m.mission_id for m in missions}
    assert ids == {"first", "second"}


def test_list_missions_empty(tmp_path: Path):
    svc = MissionService(repo_root=tmp_path)
    assert svc.list_missions() == []


def test_update_status_completed(tmp_path: Path):
    svc = MissionService(repo_root=tmp_path)
    svc.create_mission("Test", mission_id="test-1")
    m = svc.update_status("test-1", MissionStatus.COMPLETED)
    assert m.status == MissionStatus.COMPLETED
    assert m.completed_at is not None
    mgr = MissionLifecycleManager(tmp_path)
    state = mgr.get_state("test-1")
    assert state is not None
    assert state.phase == MissionPhase.COMPLETED


def test_get_mission_projects_lifecycle_phase_to_status(tmp_path: Path) -> None:
    svc = MissionService(repo_root=tmp_path)
    svc.create_mission("Projected", mission_id="projected-1")
    mgr = MissionLifecycleManager(tmp_path)
    mgr.begin_tracking("projected-1")
    mgr.plan_complete("projected-1")
    mgr.promotion_complete("projected-1", ["SPC-1"])

    mission = svc.get_mission("projected-1")

    assert mission.status == MissionStatus.IN_PROGRESS


def test_list_missions_projects_failed_lifecycle_status(tmp_path: Path) -> None:
    svc = MissionService(repo_root=tmp_path)
    svc.create_mission("Projected", mission_id="projected-failed")
    mgr = MissionLifecycleManager(tmp_path)
    mgr.begin_tracking("projected-failed")
    mgr.mark_failed("projected-failed", "boom")

    missions = svc.list_missions()
    mission = next(m for m in missions if m.mission_id == "projected-failed")

    assert mission.status == MissionStatus.FAILED


def test_mission_cli_create(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["mission", "create", "Test Mission", "--repo-root", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert "mission created" in result.output


def test_mission_cli_approve(tmp_path: Path):
    runner = CliRunner()
    runner.invoke(
        app,
        ["mission", "create", "Test", "--id", "t-1", "--repo-root", str(tmp_path)],
    )
    result = runner.invoke(
        app,
        ["mission", "approve", "t-1", "--repo-root", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert "approved" in result.output


def test_mission_cli_status(tmp_path: Path):
    runner = CliRunner()
    runner.invoke(
        app,
        ["mission", "create", "Test", "--id", "t-1", "--repo-root", str(tmp_path)],
    )
    result = runner.invoke(
        app,
        ["mission", "status", "--repo-root", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert "t-1" in result.output
    assert "drafting" in result.output


def test_mission_cli_show(tmp_path: Path):
    runner = CliRunner()
    runner.invoke(
        app,
        ["mission", "create", "Test", "--id", "t-1", "--repo-root", str(tmp_path)],
    )
    result = runner.invoke(
        app,
        ["mission", "show", "t-1", "--repo-root", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert "# Test" in result.output


def test_issue_model_has_mission_fields():
    from spec_orch.domain.models import Issue

    issue = Issue(
        issue_id="TEST-1",
        title="Test",
        summary="Summary",
        mission_id="mission-1",
        spec_section="## Scope",
        run_class="feature",
    )
    assert issue.mission_id == "mission-1"
    assert issue.spec_section == "## Scope"
    assert issue.run_class == "feature"
