"""Shared mission execution owner used by daemon and lifecycle manager."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from spec_orch.domain.models import MissionExecutionResult, RoundSummary


class MissionExecutionService:
    """Runs mission execution and returns a normalized result for callers."""

    def __init__(
        self,
        *,
        repo_root: Path,
        round_orchestrator: Any | None,
        codex_bin: str = "codex",
    ) -> None:
        self.repo_root = Path(repo_root)
        self.round_orchestrator = round_orchestrator
        self.codex_bin = codex_bin

    def execute_mission(
        self,
        *,
        mission_id: str,
        initial_round: int = 0,
    ) -> MissionExecutionResult:
        from spec_orch.services.parallel_run_controller import ParallelRunController

        plan = ParallelRunController.load_plan(mission_id, self.repo_root)
        if self.round_orchestrator is not None:
            result = self.round_orchestrator.run_supervised(
                mission_id=mission_id,
                plan=plan,
                initial_round=initial_round,
            )
            blocking_questions: list[str] = []
            if result.last_decision is not None:
                blocking_questions = list(result.last_decision.blocking_questions)
            return MissionExecutionResult(
                mission_id=mission_id,
                completed=result.completed,
                paused=result.paused,
                max_rounds_hit=result.max_rounds_hit,
                summary_markdown=self._summarize_supervised(mission_id, result.rounds, result),
                rounds=result.rounds,
                blocking_questions=blocking_questions,
            )

        controller = ParallelRunController(
            repo_root=self.repo_root,
            codex_bin=self.codex_bin,
        )
        plan_result = controller.run_plan(plan)
        return MissionExecutionResult(
            mission_id=mission_id,
            completed=plan_result.is_success(),
            summary_markdown=self._summarize_parallel(mission_id, plan_result),
        )

    @staticmethod
    def _summarize_supervised(
        mission_id: str,
        rounds: list[RoundSummary],
        result: Any,
    ) -> str:
        succeeded = result.completed and not result.paused and not result.max_rounds_hit
        summary_lines = [
            f"## Mission Execution: {mission_id}",
            "",
            f"**Rounds**: {len(rounds)}",
            f"**Result**: {'✅ Success' if succeeded else '❌ Failed'}",
            "",
        ]
        for round_summary in rounds:
            action = round_summary.decision.action.value if round_summary.decision else "none"
            summary_lines.append(
                f"- Round {round_summary.round_id} / Wave {round_summary.wave_id}: {action}"
            )
        return "\n".join(summary_lines)

    @staticmethod
    def _summarize_parallel(mission_id: str, plan_result: Any) -> str:
        summary_lines = [
            f"## Mission Execution: {mission_id}",
            "",
            f"**Duration**: {plan_result.total_duration:.1f}s",
            f"**Result**: {'✅ Success' if plan_result.is_success() else '❌ Failed'}",
            "",
        ]
        for wave_result in plan_result.wave_results:
            status = "✅" if wave_result.all_succeeded else "❌"
            summary_lines.append(
                "- Wave "
                f"{wave_result.wave_id}: {status} "
                f"({len(wave_result.packet_results)} packets)"
            )
            for packet in wave_result.failed_packets:
                summary_lines.append(f"  - ❌ {packet.packet_id}: exit={packet.exit_code}")
        return "\n".join(summary_lines)
