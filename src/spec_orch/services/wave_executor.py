"""WaveExecutor — runs all packets in a wave with semaphore-based concurrency."""

from __future__ import annotations

import asyncio
import logging
import time

from spec_orch.domain.models import (
    ExecutionPlanResult,
    ParallelConfig,
    WaveResult,
    WorkPacket,
)
from spec_orch.domain.protocols import PacketExecutor

logger = logging.getLogger(__name__)


class AsyncioWaveExecutor:
    """Executes wave packets concurrently using asyncio + Semaphore."""

    def __init__(self, packet_executor: PacketExecutor) -> None:
        self._packet_executor = packet_executor

    async def execute_wave(
        self,
        wave: list[WorkPacket],
        wave_id: int,
        config: ParallelConfig,
        cancel_event: asyncio.Event,
    ) -> WaveResult:
        limit = config.effective_limit()
        sem = asyncio.Semaphore(limit)

        logger.info(
            "wave_started",
            extra={
                "wave_id": wave_id,
                "packet_count": len(wave),
                "concurrency_limit": limit,
            },
        )

        async def _guarded(pkt: WorkPacket) -> None:
            async with sem:
                if cancel_event.is_set():
                    return
                result = await self._packet_executor.execute_packet(
                    pkt,
                    wave_id,
                    cancel_event,
                )
                results.append(result)
                if result.exit_code != 0:
                    cancel_event.set()

        results: list = []
        tasks = [asyncio.create_task(_guarded(p)) for p in wave]

        try:
            await asyncio.gather(*tasks)
        except Exception:
            cancel_event.set()
            for t in tasks:
                t.cancel()

        all_ok = all(r.exit_code == 0 for r in results) and len(results) == len(wave)
        level = "wave_completed" if all_ok else "wave_failed"
        logger.info(
            level,
            extra={"wave_id": wave_id, "all_succeeded": all_ok},
        )

        return WaveResult(
            wave_id=wave_id,
            packet_results=results,
            all_succeeded=all_ok,
        )

    async def execute_plan(
        self,
        waves: list[list[WorkPacket]],
        config: ParallelConfig,
        cancel_event: asyncio.Event | None = None,
    ) -> ExecutionPlanResult:
        if cancel_event is None:
            cancel_event = asyncio.Event()

        start = time.monotonic()
        wave_results: list[WaveResult] = []

        logger.info(
            "execution_started",
            extra={"wave_count": len(waves)},
        )

        for wave_id, wave_packets in enumerate(waves):
            if cancel_event.is_set():
                break

            wave_cancel = asyncio.Event()
            result = await self.execute_wave(
                wave_packets,
                wave_id,
                config,
                wave_cancel,
            )
            wave_results.append(result)

            if not result.all_succeeded:
                logger.info(
                    "execution_aborted",
                    extra={
                        "wave_id": wave_id,
                        "reason": "wave_failed",
                    },
                )
                break

        elapsed = time.monotonic() - start
        plan_result = ExecutionPlanResult(
            wave_results=wave_results,
            total_duration=round(elapsed, 2),
        )

        level = "execution_completed" if plan_result.is_success() else "execution_failed"
        logger.info(
            level,
            extra={
                "total_duration": plan_result.total_duration,
                "success": plan_result.is_success(),
            },
        )
        return plan_result
