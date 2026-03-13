"""Tests for the dashboard data gathering logic."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from spec_orch.dashboard import _gather_missions


@pytest.fixture()
def dashboard_repo(tmp_path: Path) -> Path:
    mid = "test-dash"
    specs = tmp_path / "docs" / "specs" / mid
    specs.mkdir(parents=True)

    (specs / "mission.json").write_text(
        json.dumps(
            {
                "mission_id": mid,
                "title": "Dashboard Test",
                "status": "approved",
                "spec_path": f"docs/specs/{mid}/spec.md",
                "acceptance_criteria": [],
                "constraints": [],
                "interface_contracts": [],
                "created_at": "2026-01-01T00:00:00+00:00",
                "approved_at": "2026-01-01T00:00:00+00:00",
                "completed_at": None,
            }
        )
    )
    (specs / "spec.md").write_text("# Dashboard Test\n")
    (specs / "plan.json").write_text(
        json.dumps(
            {
                "plan_id": "plan-d",
                "mission_id": mid,
                "status": "executing",
                "waves": [
                    {
                        "wave_number": 0,
                        "description": "W0",
                        "work_packets": [
                            {
                                "packet_id": "dp1",
                                "title": "Dash Packet",
                                "spec_section": "",
                                "run_class": "feature",
                                "files_in_scope": [],
                                "files_out_of_scope": [],
                                "depends_on": [],
                                "acceptance_criteria": [],
                                "verification_commands": {},
                                "builder_prompt": "",
                                "linear_issue_id": "SON-99",
                            }
                        ],
                    }
                ],
            }
        )
    )
    return tmp_path


class TestGatherMissions:
    def test_returns_mission_data(self, dashboard_repo: Path) -> None:
        result = _gather_missions(dashboard_repo)
        assert len(result) == 1
        m = result[0]
        assert m["mission_id"] == "test-dash"
        assert m["title"] == "Dashboard Test"
        assert m["plan"] is not None
        assert m["plan"]["wave_count"] == 1
        assert m["plan"]["packet_count"] == 1
        assert m["pipeline_total"] == 11

    def test_empty_repo(self, tmp_path: Path) -> None:
        result = _gather_missions(tmp_path)
        assert result == []

    def test_mission_without_plan(self, tmp_path: Path) -> None:
        mid = "no-plan"
        specs = tmp_path / "docs" / "specs" / mid
        specs.mkdir(parents=True)
        (specs / "mission.json").write_text(
            json.dumps(
                {
                    "mission_id": mid,
                    "title": "No Plan",
                    "status": "drafting",
                    "spec_path": f"docs/specs/{mid}/spec.md",
                    "acceptance_criteria": [],
                    "constraints": [],
                    "interface_contracts": [],
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "approved_at": None,
                    "completed_at": None,
                }
            )
        )
        result = _gather_missions(tmp_path)
        assert len(result) == 1
        assert result[0]["plan"] is None
