from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from spec_orch.domain.models import (
    ExecutionPlan,
    RoundAction,
    RoundDecision,
    RoundStatus,
    RoundSummary,
    Wave,
    WorkPacket,
)


def _make_plan() -> ExecutionPlan:
    return ExecutionPlan(
        plan_id="plan-1",
        mission_id="mission-1",
        waves=[
            Wave(
                wave_number=0,
                description="Foundation",
                work_packets=[WorkPacket(packet_id="pkt-1", title="Task 1")],
            )
        ],
    )


def test_execute_supervised_returns_summary_and_blocking_questions(tmp_path: Path) -> None:
    from spec_orch.domain.models import MissionExecutionResult
    from spec_orch.services.mission_execution_service import MissionExecutionService
    from spec_orch.services.round_orchestrator import RoundOrchestratorResult

    stub_orchestrator = MagicMock()
    stub_orchestrator.run_supervised.return_value = RoundOrchestratorResult(
        completed=False,
        paused=True,
        rounds=[
            RoundSummary(
                round_id=1,
                wave_id=0,
                status=RoundStatus.DECIDED,
                decision=RoundDecision(
                    action=RoundAction.ASK_HUMAN,
                    summary="Need approval.",
                    blocking_questions=["Approve the rollout?"],
                ),
            )
        ],
    )

    service = MissionExecutionService(
        repo_root=tmp_path,
        round_orchestrator=stub_orchestrator,
    )

    with patch(
        "spec_orch.services.parallel_run_controller.ParallelRunController.load_plan"
    ) as load:
        load.return_value = _make_plan()
        result = service.execute_mission(mission_id="mission-1", initial_round=0)

    assert isinstance(result, MissionExecutionResult)
    assert result.paused is True
    assert result.blocking_questions == ["Approve the rollout?"]
    assert "Mission Execution: mission-1" in result.summary_markdown
    assert "Round 1 / Wave 0: ask_human" in result.summary_markdown


def test_execute_unsupervised_falls_back_to_parallel_run_controller(tmp_path: Path) -> None:
    from spec_orch.services.mission_execution_service import MissionExecutionService

    mock_plan_result = MagicMock()
    mock_plan_result.is_success.return_value = True
    mock_plan_result.total_duration = 4.0
    mock_plan_result.wave_results = [
        MagicMock(wave_id=0, all_succeeded=True, packet_results=[], failed_packets=[]),
    ]

    with patch("spec_orch.services.parallel_run_controller.ParallelRunController") as MockPRC:
        MockPRC.load_plan.return_value = _make_plan()
        MockPRC.return_value.run_plan.return_value = mock_plan_result

        service = MissionExecutionService(
            repo_root=tmp_path,
            round_orchestrator=None,
        )
        result = service.execute_mission(mission_id="mission-1")

    assert result.completed is True
    assert result.paused is False
    assert "Duration" in result.summary_markdown
    assert "Success" in result.summary_markdown
