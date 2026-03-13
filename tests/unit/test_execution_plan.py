"""Tests for ExecutionPlan, Wave, WorkPacket models, ScoperAdapter, and PromotionService."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from spec_orch.cli import app
from spec_orch.domain.models import (
    ExecutionPlan,
    Mission,
    PlanStatus,
    Wave,
    WorkPacket,
)
from spec_orch.services.promotion_service import (
    PromotionService,
    load_plan,
    save_plan,
)


def test_work_packet_defaults():
    wp = WorkPacket(packet_id="wp-1", title="Test Packet")
    assert wp.run_class == "feature"
    assert wp.depends_on == []
    assert wp.linear_issue_id is None


def test_wave_with_packets():
    wp1 = WorkPacket(packet_id="wp-1", title="Setup")
    wp2 = WorkPacket(packet_id="wp-2", title="Build", depends_on=["wp-1"])
    wave = Wave(wave_number=0, description="Scaffold", work_packets=[wp1, wp2])
    assert len(wave.work_packets) == 2
    assert wave.work_packets[1].depends_on == ["wp-1"]


def test_execution_plan_defaults():
    plan = ExecutionPlan(plan_id="p-1", mission_id="m-1")
    assert plan.status == PlanStatus.DRAFT
    assert plan.waves == []


def test_save_and_load_plan(tmp_path: Path):
    wp = WorkPacket(
        packet_id="wp-1",
        title="Add auth",
        spec_section="## Auth",
        run_class="feature",
        acceptance_criteria=["Login works"],
        builder_prompt="Add login endpoint",
    )
    plan = ExecutionPlan(
        plan_id="plan-test",
        mission_id="auth-mission",
        waves=[
            Wave(wave_number=0, description="Scaffold", work_packets=[wp]),
        ],
    )

    path = tmp_path / "plan.json"
    save_plan(plan, path)
    assert path.exists()

    loaded = load_plan(path)
    assert loaded.plan_id == "plan-test"
    assert loaded.mission_id == "auth-mission"
    assert len(loaded.waves) == 1
    assert loaded.waves[0].work_packets[0].title == "Add auth"


def test_promotion_service_local(tmp_path: Path):
    wp1 = WorkPacket(packet_id="wp-1", title="Task A")
    wp2 = WorkPacket(packet_id="wp-2", title="Task B")
    plan = ExecutionPlan(
        plan_id="p-1",
        mission_id="test-mission",
        waves=[
            Wave(wave_number=0, description="Wave 0", work_packets=[wp1]),
            Wave(wave_number=1, description="Wave 1", work_packets=[wp2]),
        ],
    )

    svc = PromotionService()
    result = svc.promote(plan)

    assert result.status == PlanStatus.EXECUTING
    assert result.waves[0].work_packets[0].linear_issue_id is not None
    assert "LOCAL" in result.waves[0].work_packets[0].linear_issue_id
    assert result.waves[1].work_packets[0].linear_issue_id is not None


def test_promotion_service_to_linear():
    wp = WorkPacket(
        packet_id="wp-1",
        title="Task A",
        builder_prompt="Do it",
        acceptance_criteria=["Done"],
    )
    plan = ExecutionPlan(
        plan_id="p-1",
        mission_id="test",
        waves=[Wave(wave_number=0, description="W0", work_packets=[wp])],
    )

    mock_client = MagicMock()
    mock_client.create_issue.return_value = {
        "id": "uuid-1",
        "identifier": "SON-99",
        "title": "[W0] Task A",
    }

    svc = PromotionService(linear_client=mock_client)
    result = svc.promote(plan, team_key="SON")

    assert result.status == PlanStatus.EXECUTING
    assert result.waves[0].work_packets[0].linear_issue_id == "SON-99"
    mock_client.create_issue.assert_called_once()


def test_plan_show_cli_not_found(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["plan-show", "nonexistent", "--repo-root", str(tmp_path)],
    )
    assert result.exit_code == 1
    assert "no plan found" in result.output


def test_plan_show_cli(tmp_path: Path):
    wp = WorkPacket(packet_id="wp-1", title="Setup DB")
    plan = ExecutionPlan(
        plan_id="p-1",
        mission_id="db-migration",
        waves=[Wave(wave_number=0, description="Scaffold", work_packets=[wp])],
    )
    plan_dir = tmp_path / "docs/specs/db-migration"
    plan_dir.mkdir(parents=True)
    save_plan(plan, plan_dir / "plan.json")

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["plan-show", "db-migration", "--repo-root", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert "wp-1" in result.output
    assert "Setup DB" in result.output


def test_promote_cli_local(tmp_path: Path):
    wp = WorkPacket(packet_id="wp-1", title="Task")
    plan = ExecutionPlan(
        plan_id="p-1",
        mission_id="local-test",
        waves=[Wave(wave_number=0, description="W0", work_packets=[wp])],
    )
    plan_dir = tmp_path / "docs/specs/local-test"
    plan_dir.mkdir(parents=True)
    save_plan(plan, plan_dir / "plan.json")

    runner = CliRunner()
    with patch.dict("os.environ", {"SPEC_ORCH_LINEAR_TOKEN": ""}, clear=False):
        result = runner.invoke(
            app,
            ["promote", "local-test", "--repo-root", str(tmp_path)],
        )
    assert result.exit_code == 0
    assert "promoted 1 work packets" in result.output

    reloaded = load_plan(plan_dir / "plan.json")
    assert reloaded.waves[0].work_packets[0].linear_issue_id is not None
    assert reloaded.waves[0].work_packets[0].linear_issue_id.startswith("LOCAL-")


def test_scoper_adapter_parse_response():
    from spec_orch.services.scoper_adapter import LiteLLMScoperAdapter

    adapter = LiteLLMScoperAdapter(model="test/model")
    mission = Mission(mission_id="test", title="Test")

    mock_message = MagicMock()
    mock_message.content = json.dumps(
        {
            "waves": [
                {
                    "wave_number": 0,
                    "description": "Scaffold",
                    "work_packets": [
                        {
                            "packet_id": "wp-1",
                            "title": "Setup types",
                            "run_class": "feature",
                            "builder_prompt": "Create types",
                        },
                    ],
                },
            ],
        }
    )
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    plan = adapter._parse_response(mock_response, mission)
    assert plan.mission_id == "test"
    assert len(plan.waves) == 1
    assert plan.waves[0].work_packets[0].title == "Setup types"
