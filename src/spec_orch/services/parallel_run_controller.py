"""ParallelRunController — orchestrates wave-based parallel execution of an ExecutionPlan."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from spec_orch.domain.models import (
    ExecutionPlan,
    ExecutionPlanResult,
    ParallelConfig,
    WorkPacket,
)
from spec_orch.services.packet_executor import SubprocessPacketExecutor
from spec_orch.services.wave_executor import AsyncioWaveExecutor

logger = logging.getLogger(__name__)


class ParallelRunController:
    """Runs an ExecutionPlan wave-by-wave with configurable concurrency."""

    def __init__(
        self,
        *,
        repo_root: Path,
        config: ParallelConfig | None = None,
        codex_bin: str = "codex",
    ) -> None:
        self.repo_root = repo_root
        self.config = config or ParallelConfig()
        self._packet_executor = SubprocessPacketExecutor(
            codex_bin=codex_bin,
            workspace=str(repo_root),
        )
        self._wave_executor = AsyncioWaveExecutor(self._packet_executor)

    def run_plan(
        self,
        plan: ExecutionPlan,
        *,
        cancel_event: asyncio.Event | None = None,
    ) -> ExecutionPlanResult:
        """Execute the plan synchronously (wraps asyncio internally)."""
        return asyncio.run(self.run_plan_async(plan, cancel_event=cancel_event))

    async def run_plan_async(
        self,
        plan: ExecutionPlan,
        *,
        cancel_event: asyncio.Event | None = None,
    ) -> ExecutionPlanResult:
        waves: list[list[WorkPacket]] = [w.work_packets for w in plan.waves]
        result = await self._wave_executor.execute_plan(
            waves, self.config, cancel_event,
        )
        return result

    @staticmethod
    def load_plan(mission_id: str, repo_root: Path) -> ExecutionPlan:
        """Load an ExecutionPlan from the mission's specs directory."""
        from spec_orch.services.promotion_service import load_plan

        plan_path = repo_root / "docs" / "specs" / mission_id / "plan.json"
        if not plan_path.exists():
            raise FileNotFoundError(f"No plan found for mission {mission_id}")
        return load_plan(plan_path)
