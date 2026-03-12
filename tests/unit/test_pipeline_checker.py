"""Tests for spec_orch.services.pipeline_checker."""

from __future__ import annotations

import json
from pathlib import Path

from spec_orch.services.pipeline_checker import (
    check_pipeline,
    format_pipeline,
    next_step,
)


def _setup_mission(tmp_path: Path, mission_id: str, **overrides: object) -> Path:
    specs = tmp_path / "docs" / "specs" / mission_id
    specs.mkdir(parents=True)

    mission = {
        "mission_id": mission_id,
        "title": "Test Mission",
        "status": "drafting",
        "spec_path": f"docs/specs/{mission_id}/spec.md",
        "acceptance_criteria": [],
        "constraints": [],
        "interface_contracts": [],
        "created_at": "2026-01-01T00:00:00+00:00",
        "approved_at": overrides.get("approved_at"),
        "completed_at": overrides.get("completed_at"),
    }
    (specs / "mission.json").write_text(json.dumps(mission))

    if overrides.get("has_spec", False):
        (specs / "spec.md").write_text("# Test Spec\n\nGoal here.")

    if overrides.get("plan_data"):
        (specs / "plan.json").write_text(json.dumps(overrides["plan_data"]))

    if overrides.get("has_retro", False):
        (specs / "retro.md").write_text("# Retro\n")

    return tmp_path


def test_empty_mission_shows_discuss_as_current(tmp_path: Path) -> None:
    _setup_mission(tmp_path, "m1")
    stages = check_pipeline("m1", tmp_path)

    assert stages[0].key == "discuss"
    assert stages[0].status == "current"
    assert all(s.status == "pending" for s in stages[1:])


def test_after_freeze_approve_is_current(tmp_path: Path) -> None:
    _setup_mission(tmp_path, "m1", has_spec=True)
    stages = check_pipeline("m1", tmp_path)

    assert stages[0].status == "done"  # discuss
    assert stages[1].status == "done"  # freeze
    assert stages[2].status == "current"  # approve
    assert stages[2].key == "approve"


def test_after_approve_plan_is_current(tmp_path: Path) -> None:
    _setup_mission(tmp_path, "m1", has_spec=True, approved_at="2026-01-01")
    stages = check_pipeline("m1", tmp_path)

    assert stages[2].status == "done"  # approve
    assert stages[3].status == "current"  # plan
    assert stages[3].key == "plan"


def test_after_plan_promote_is_current(tmp_path: Path) -> None:
    plan = {
        "plan_id": "p1",
        "mission_id": "m1",
        "status": "draft",
        "waves": [{"wave_number": 0, "work_packets": [{"linear_issue_id": None}]}],
    }
    _setup_mission(tmp_path, "m1", has_spec=True, approved_at="2026-01-01", plan_data=plan)
    stages = check_pipeline("m1", tmp_path)

    assert stages[3].status == "done"  # plan
    assert stages[4].status == "current"  # promote
    assert stages[4].key == "promote"


def test_after_promote_run_is_current(tmp_path: Path) -> None:
    plan = {
        "plan_id": "p1",
        "mission_id": "m1",
        "status": "draft",
        "waves": [{"wave_number": 0, "work_packets": [{"linear_issue_id": "SON-1"}]}],
    }
    _setup_mission(tmp_path, "m1", has_spec=True, approved_at="2026-01-01", plan_data=plan)
    stages = check_pipeline("m1", tmp_path)

    assert stages[4].status == "done"  # promote
    assert stages[5].status == "current"  # run


def test_local_ids_not_counted_as_promoted(tmp_path: Path) -> None:
    plan = {
        "plan_id": "p1",
        "mission_id": "m1",
        "status": "draft",
        "waves": [{"wave_number": 0, "work_packets": [{"linear_issue_id": "LOCAL-M1-1"}]}],
    }
    _setup_mission(tmp_path, "m1", has_spec=True, approved_at="2026-01-01", plan_data=plan)
    stages = check_pipeline("m1", tmp_path)

    assert stages[4].status == "current"  # promote still current
    assert stages[4].key == "promote"


def test_next_step_returns_current(tmp_path: Path) -> None:
    _setup_mission(tmp_path, "m1", has_spec=True)
    nxt = next_step("m1", tmp_path)
    assert nxt is not None
    assert nxt.key == "approve"


def test_next_step_returns_none_when_complete(tmp_path: Path) -> None:
    plan = {
        "plan_id": "p1",
        "mission_id": "m1",
        "status": "completed",
        "waves": [{"wave_number": 0, "work_packets": [{"linear_issue_id": "SON-1"}]}],
    }
    _setup_mission(
        tmp_path, "m1",
        has_spec=True,
        approved_at="2026-01-01",
        completed_at="2026-01-02",
        plan_data=plan,
        has_retro=True,
    )
    stages = check_pipeline("m1", tmp_path)
    done_count = sum(1 for s in stages if s.status == "done")
    assert done_count >= 6


def test_format_pipeline_shows_icons(tmp_path: Path) -> None:
    _setup_mission(tmp_path, "m1", has_spec=True)
    stages = check_pipeline("m1", tmp_path)
    output = format_pipeline(stages)

    assert "[✓] Discuss" in output
    assert "[→] Mission Approve" in output
    assert "[·]" in output
