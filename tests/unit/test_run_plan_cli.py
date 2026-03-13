"""Tests for run-plan CLI command and ParallelRunController.load_plan."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from spec_orch.cli import app
from spec_orch.services.parallel_run_controller import ParallelRunController

runner = CliRunner()


@pytest.fixture()
def mission_with_plan(tmp_path: Path) -> tuple[Path, str]:
    mission_id = "test-mission"
    specs = tmp_path / "docs" / "specs" / mission_id
    specs.mkdir(parents=True)

    (specs / "mission.json").write_text(json.dumps({
        "mission_id": mission_id,
        "title": "Test Mission",
        "status": "approved",
        "spec_path": f"docs/specs/{mission_id}/spec.md",
        "acceptance_criteria": [],
        "constraints": [],
        "interface_contracts": [],
        "created_at": "2026-01-01T00:00:00+00:00",
        "approved_at": "2026-01-01T00:00:00+00:00",
        "completed_at": None,
    }))

    (specs / "spec.md").write_text("# Test\n")

    (specs / "plan.json").write_text(json.dumps({
        "plan_id": "plan-test",
        "mission_id": mission_id,
        "status": "executing",
        "waves": [
            {
                "wave_number": 0,
                "description": "Scaffold",
                "work_packets": [
                    {
                        "packet_id": "p1",
                        "title": "Task A",
                        "spec_section": "",
                        "run_class": "feature",
                        "files_in_scope": [],
                        "files_out_of_scope": [],
                        "depends_on": [],
                        "acceptance_criteria": [],
                        "verification_commands": {},
                        "builder_prompt": "echo hello",
                        "linear_issue_id": None,
                    },
                ],
            },
        ],
    }))
    return tmp_path, mission_id


class TestRunPlanCLI:
    def test_dry_run(self, mission_with_plan: tuple[Path, str]) -> None:
        repo, mid = mission_with_plan
        result = runner.invoke(app, ["run-plan", mid, "--repo-root", str(repo), "--dry-run"])
        assert result.exit_code == 0
        assert "dry run" in result.output.lower()
        assert "Task A" in result.output

    def test_missing_plan(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["run-plan", "nonexistent", "--repo-root", str(tmp_path)])
        assert result.exit_code == 1
        assert "no plan found" in result.output


class TestLoadPlan:
    def test_load_plan(self, mission_with_plan: tuple[Path, str]) -> None:
        repo, mid = mission_with_plan
        plan = ParallelRunController.load_plan(mid, repo)
        assert plan.plan_id == "plan-test"
        assert len(plan.waves) == 1
        assert plan.waves[0].work_packets[0].packet_id == "p1"

    def test_load_plan_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            ParallelRunController.load_plan("nope", tmp_path)
