"""Tests for parallel wave execution — data classes, protocols, executors, and cancellation."""

from __future__ import annotations

import asyncio
import os
import signal
from unittest.mock import AsyncMock, patch

import pytest

from spec_orch.domain.models import (
    ExecutionPlan,
    ExecutionPlanResult,
    PacketResult,
    ParallelConfig,
    Wave,
    WaveResult,
    WorkPacket,
)
from spec_orch.services.cancellation_handler import CancellationHandler
from spec_orch.services.packet_executor import SubprocessPacketExecutor
from spec_orch.services.parallel_logging import ParallelJsonFormatter
from spec_orch.services.wave_executor import AsyncioWaveExecutor


def _make_packet(pid: str, prompt: str = "echo ok") -> WorkPacket:
    return WorkPacket(packet_id=pid, title=pid, builder_prompt=prompt)


# ── ParallelConfig ──────────────────────────────────────────────────────


class TestParallelConfig:
    def test_default_values(self) -> None:
        cfg = ParallelConfig()
        assert cfg.max_concurrency == 3
        assert cfg.max_concurrency_cap == 0

    def test_effective_limit_default(self) -> None:
        cfg = ParallelConfig()
        cores = os.cpu_count() or 4
        assert cfg.effective_limit() == min(3, cores)

    def test_effective_limit_with_cap(self) -> None:
        cfg = ParallelConfig(max_concurrency=10, max_concurrency_cap=4)
        assert cfg.effective_limit() == 4

    def test_effective_limit_concurrency_below_cap(self) -> None:
        cfg = ParallelConfig(max_concurrency=2, max_concurrency_cap=8)
        assert cfg.effective_limit() == 2


# ── PacketResult ────────────────────────────────────────────────────────


class TestPacketResult:
    def test_create(self) -> None:
        r = PacketResult(
            packet_id="p1", wave_id=0, exit_code=0,
            stdout="ok", stderr="", duration_seconds=1.5,
        )
        assert r.packet_id == "p1"
        assert r.duration_seconds == 1.5


# ── WaveResult ──────────────────────────────────────────────────────────


class TestWaveResult:
    def test_all_succeeded(self) -> None:
        r = WaveResult(
            wave_id=0,
            packet_results=[
                PacketResult("p1", 0, 0, "", "", 1.0),
                PacketResult("p2", 0, 0, "", "", 2.0),
            ],
            all_succeeded=True,
        )
        assert r.failed_packets == []

    def test_failed_packets_property(self) -> None:
        r = WaveResult(
            wave_id=1,
            packet_results=[
                PacketResult("p1", 1, 0, "", "", 1.0),
                PacketResult("p2", 1, 1, "", "error", 2.0),
            ],
            all_succeeded=False,
        )
        assert len(r.failed_packets) == 1
        assert r.failed_packets[0].packet_id == "p2"


# ── ExecutionPlanResult ─────────────────────────────────────────────────


class TestExecutionPlanResult:
    def test_is_success(self) -> None:
        result = ExecutionPlanResult(
            wave_results=[
                WaveResult(0, [], True),
                WaveResult(1, [], True),
            ],
            total_duration=5.0,
        )
        assert result.is_success()

    def test_is_not_success(self) -> None:
        result = ExecutionPlanResult(
            wave_results=[
                WaveResult(0, [], True),
                WaveResult(1, [], False),
            ],
            total_duration=5.0,
        )
        assert not result.is_success()


# ── SubprocessPacketExecutor ────────────────────────────────────────────


class TestSubprocessPacketExecutor:
    @pytest.mark.asyncio
    async def test_execute_success(self) -> None:
        executor = SubprocessPacketExecutor(codex_bin="echo", workspace="/tmp")
        pkt = _make_packet("p1", "hello")
        cancel = asyncio.Event()
        result = await executor.execute_packet(pkt, wave_id=0, cancel_event=cancel)
        assert result.packet_id == "p1"
        assert result.wave_id == 0
        assert result.duration_seconds >= 0

    @pytest.mark.asyncio
    async def test_execute_missing_binary(self) -> None:
        executor = SubprocessPacketExecutor(
            codex_bin="nonexistent_binary_xyz", workspace="/tmp",
        )
        pkt = _make_packet("p1")
        cancel = asyncio.Event()
        result = await executor.execute_packet(pkt, wave_id=0, cancel_event=cancel)
        assert result.exit_code == 127
        assert "not found" in result.stderr

    @pytest.mark.asyncio
    async def test_execute_respects_cancel(self) -> None:
        executor = SubprocessPacketExecutor(codex_bin="sleep", workspace="/tmp")
        pkt = _make_packet("p1", "100")
        cancel = asyncio.Event()

        async def _set_cancel() -> None:
            await asyncio.sleep(0.1)
            cancel.set()

        asyncio.create_task(_set_cancel())
        result = await executor.execute_packet(pkt, wave_id=0, cancel_event=cancel)
        assert "cancelled" in result.stderr or result.exit_code != 0


# ── AsyncioWaveExecutor ────────────────────────────────────────────────


class TestAsyncioWaveExecutor:
    @pytest.mark.asyncio
    async def test_all_packets_succeed(self) -> None:
        pe = SubprocessPacketExecutor(codex_bin="echo", workspace="/tmp")
        we = AsyncioWaveExecutor(pe)
        pkts = [_make_packet(f"p{i}") for i in range(3)]
        cfg = ParallelConfig(max_concurrency=2)
        cancel = asyncio.Event()
        result = await we.execute_wave(pkts, wave_id=0, config=cfg, cancel_event=cancel)
        assert result.wave_id == 0
        assert len(result.packet_results) == 3

    @pytest.mark.asyncio
    async def test_execute_plan_stops_on_failure(self) -> None:
        pe = SubprocessPacketExecutor(codex_bin="false", workspace="/tmp")
        we = AsyncioWaveExecutor(pe)
        wave0 = [_make_packet("p0")]
        wave1 = [_make_packet("p1")]
        cfg = ParallelConfig()
        result = await we.execute_plan([wave0, wave1], cfg)
        assert len(result.wave_results) == 1
        assert not result.is_success()


# ── Concurrency Limiting ───────────────────────────────────────────────


class TestConcurrencyLimiting:
    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrency(self) -> None:
        max_concurrent = 0
        current = 0
        lock = asyncio.Lock()

        async def tracked_task(i: int, sem: asyncio.Semaphore) -> int:
            nonlocal max_concurrent, current
            async with sem:
                async with lock:
                    current += 1
                    max_concurrent = max(max_concurrent, current)
                await asyncio.sleep(0.01)
                async with lock:
                    current -= 1
            return i

        sem = asyncio.Semaphore(2)
        results = await asyncio.gather(*[tracked_task(i, sem) for i in range(6)])
        assert len(results) == 6
        assert max_concurrent <= 2


# ── Fail-Fast ──────────────────────────────────────────────────────────


class TestFailFast:
    @pytest.mark.asyncio
    async def test_gather_raises_on_first_exception(self) -> None:
        async def fail() -> None:
            raise RuntimeError("boom")

        async def slow() -> str:
            await asyncio.sleep(10)
            return "done"

        with pytest.raises(RuntimeError, match="boom"):
            await asyncio.gather(fail(), slow())


# ── Cancellation ───────────────────────────────────────────────────────


class TestCancellation:
    @pytest.mark.asyncio
    async def test_cancel_event_stops_tasks(self) -> None:
        cancel = asyncio.Event()
        completed = False

        async def cancellable() -> None:
            nonlocal completed
            for _ in range(100):
                if cancel.is_set():
                    return
                await asyncio.sleep(0.01)
            completed = True

        task = asyncio.create_task(cancellable())
        await asyncio.sleep(0.02)
        cancel.set()
        await task
        assert not completed


# ── CancellationHandler ────────────────────────────────────────────────


class TestCancellationHandler:
    def test_install_and_uninstall(self) -> None:
        cancel = asyncio.Event()
        handler = CancellationHandler(cancel)
        original = signal.getsignal(signal.SIGINT)
        handler.install()
        assert signal.getsignal(signal.SIGINT) != original
        handler.uninstall()
        assert signal.getsignal(signal.SIGINT) == original

    def test_first_signal_sets_event(self) -> None:
        cancel = asyncio.Event()
        handler = CancellationHandler(cancel)
        handler.install()
        try:
            handler._handle(signal.SIGINT, None)
            assert cancel.is_set()
        finally:
            handler.uninstall()

    def test_second_signal_raises(self) -> None:
        cancel = asyncio.Event()
        handler = CancellationHandler(cancel)
        handler.install()
        try:
            handler._handle(signal.SIGINT, None)
            with pytest.raises(KeyboardInterrupt):
                handler._handle(signal.SIGINT, None)
        finally:
            handler.uninstall()


# ── ParallelJsonFormatter ──────────────────────────────────────────────


class TestParallelJsonFormatter:
    def test_formats_with_extra_fields(self) -> None:
        import json
        import logging

        fmt = ParallelJsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO,
            pathname="", lineno=0, msg="packet_started",
            args=(), exc_info=None,
        )
        record.wave_id = 0  # type: ignore[attr-defined]
        record.packet_id = "p1"  # type: ignore[attr-defined]
        output = fmt.format(record)
        data = json.loads(output)
        assert data["event"] == "packet_started"
        assert data["wave_id"] == 0
        assert data["packet_id"] == "p1"
