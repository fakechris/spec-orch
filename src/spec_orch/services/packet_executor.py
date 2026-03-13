"""PacketExecutor — runs a single WorkPacket as an async subprocess."""

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
