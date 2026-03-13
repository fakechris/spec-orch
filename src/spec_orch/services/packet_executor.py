"""PacketExecutor — runs a single WorkPacket as an async subprocess.

Supports two modes:
- ``SubprocessPacketExecutor``: raw command execution (default, for testing)
- ``FullPipelinePacketExecutor``: build → verify → gate (production EODF)
"""

from __future__ import annotations

import asyncio
import logging
import time

from spec_orch.domain.models import PacketResult, WorkPacket

logger = logging.getLogger(__name__)


class SubprocessPacketExecutor:
    """Executes a WorkPacket by calling ``codex exec`` as a subprocess."""

    def __init__(self, *, codex_bin: str = "codex", workspace: str = ".") -> None:
        self._codex_bin = codex_bin
        self._workspace = workspace

    async def execute_packet(
        self,
        packet: WorkPacket,
        wave_id: int,
        cancel_event: asyncio.Event,
    ) -> PacketResult:
        start = time.monotonic()

        cmd = [
            self._codex_bin,
            "exec",
            "--prompt",
            packet.builder_prompt or f"Implement {packet.title}",
        ]

        logger.info(
            "packet_started",
            extra={"wave_id": wave_id, "packet_id": packet.packet_id},
        )

        proc: asyncio.subprocess.Process | None = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._workspace,
            )

            async def _wait_or_cancel() -> tuple[bytes, bytes]:
                assert proc is not None
                while True:
                    if cancel_event.is_set():
                        proc.terminate()
                        try:
                            await asyncio.wait_for(proc.wait(), timeout=5.0)
                        except TimeoutError:
                            proc.kill()
                        return b"", b"cancelled by cancel_event"
                    try:
                        out, err = await asyncio.wait_for(
                            proc.communicate(), timeout=1.0,
                        )
                        return out, err
                    except TimeoutError:
                        continue

            stdout_bytes, stderr_bytes = await _wait_or_cancel()
            exit_code = proc.returncode if proc.returncode is not None else -1
        except FileNotFoundError:
            stdout_bytes, stderr_bytes = b"", f"{self._codex_bin} not found".encode()
            exit_code = 127
        except Exception as exc:
            stdout_bytes, stderr_bytes = b"", str(exc).encode()
            exit_code = 1

        elapsed = time.monotonic() - start
        level = "packet_completed" if exit_code == 0 else "packet_failed"
        logger.info(
            level,
            extra={
                "wave_id": wave_id,
                "packet_id": packet.packet_id,
                "exit_code": exit_code,
                "duration_seconds": round(elapsed, 2),
            },
        )

        return PacketResult(
            packet_id=packet.packet_id,
            wave_id=wave_id,
            exit_code=exit_code,
            stdout=stdout_bytes.decode(errors="replace"),
            stderr=stderr_bytes.decode(errors="replace"),
            duration_seconds=round(elapsed, 2),
        )


class FullPipelinePacketExecutor:
    """Executes build → verify → gate for a single WorkPacket.

    Production executor that drives each packet through the full EODF
    pipeline: codex exec build, then run verification commands, then
    aggregate results.
    """

    def __init__(
        self,
        *,
        codex_bin: str = "codex",
        workspace: str = ".",
        verify_commands: dict[str, list[str]] | None = None,
    ) -> None:
        self._codex_bin = codex_bin
        self._workspace = workspace
        self._default_verify = verify_commands or {
            "lint": ["ruff", "check", "."],
            "test": ["python", "-m", "pytest", "-x", "-q"],
        }

    async def execute_packet(
        self,
        packet: WorkPacket,
        wave_id: int,
        cancel_event: asyncio.Event,
    ) -> PacketResult:
        start = time.monotonic()
        log_extra = {"wave_id": wave_id, "packet_id": packet.packet_id}
        logger.info("packet_started", extra=log_extra)

        # Phase 1: Build (codex exec)
        build_exit, build_out, build_err = await self._run_subprocess(
            [self._codex_bin, "exec", "--prompt",
             packet.builder_prompt or f"Implement {packet.title}"],
            cancel_event,
        )

        if cancel_event.is_set() or build_exit != 0:
            return self._make_result(
                packet, wave_id, build_exit, build_out, build_err, start,
            )

        # Phase 2: Verify
        verify_cmds = packet.verification_commands or self._default_verify
        verify_results: list[str] = []
        overall_exit = 0

        for name, cmd in verify_cmds.items():
            if cancel_event.is_set():
                break
            logger.info("verify_step_started", extra={**log_extra, "step": name})
            v_exit, v_out, v_err = await self._run_subprocess(cmd, cancel_event)
            status = "pass" if v_exit == 0 else "fail"
            verify_results.append(f"{name}:{status}")
            if v_exit != 0:
                overall_exit = v_exit
                logger.info(
                    "verify_step_failed",
                    extra={**log_extra, "step": name, "exit_code": v_exit},
                )
                break
            logger.info("verify_step_passed", extra={**log_extra, "step": name})

        combined_out = build_out + "\n--- verify ---\n" + " | ".join(verify_results)
        combined_err = build_err

        final_exit = overall_exit if build_exit == 0 else build_exit
        return self._make_result(
            packet, wave_id, final_exit, combined_out, combined_err, start,
        )

    async def _run_subprocess(
        self, cmd: list[str], cancel_event: asyncio.Event,
    ) -> tuple[int, str, str]:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._workspace,
            )
            while True:
                if cancel_event.is_set():
                    proc.terminate()
                    try:
                        await asyncio.wait_for(proc.wait(), timeout=5.0)
                    except TimeoutError:
                        proc.kill()
                    return -1, "", "cancelled"
                try:
                    out, err = await asyncio.wait_for(proc.communicate(), timeout=2.0)
                    rc = proc.returncode if proc.returncode is not None else -1
                    return rc, out.decode(errors="replace"), err.decode(errors="replace")
                except TimeoutError:
                    continue
        except FileNotFoundError:
            return 127, "", f"{cmd[0]} not found"
        except Exception as exc:
            return 1, "", str(exc)

    @staticmethod
    def _make_result(
        packet: WorkPacket,
        wave_id: int,
        exit_code: int,
        stdout: str,
        stderr: str,
        start: float,
    ) -> PacketResult:
        elapsed = round(time.monotonic() - start, 2)
        level = "packet_completed" if exit_code == 0 else "packet_failed"
        logger.info(
            level,
            extra={
                "wave_id": wave_id,
                "packet_id": packet.packet_id,
                "exit_code": exit_code,
                "duration_seconds": elapsed,
            },
        )
        return PacketResult(
            packet_id=packet.packet_id,
            wave_id=wave_id,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=elapsed,
        )
