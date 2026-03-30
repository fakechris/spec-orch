from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from spec_orch.domain.models import PacketResult, WorkPacket
from spec_orch.services.packet_executor import FullPipelinePacketExecutor, SubprocessPacketExecutor


def _make_packet(pid: str, prompt: str = "echo ok") -> WorkPacket:
    return WorkPacket(packet_id=pid, title=pid, builder_prompt=prompt)


@pytest.mark.asyncio
async def test_subprocess_packet_executor_delegates_attempt_payload_shaping() -> None:
    executor = SubprocessPacketExecutor(codex_bin="echo", workspace="/tmp")
    packet = _make_packet("p1", "hello")
    cancel = asyncio.Event()
    delegated: dict[str, object] = {}

    def fake_build_packet_attempt_payload(
        packet: WorkPacket,
        *,
        wave_id: int,
        result: PacketResult,
        owner_kind: str,
    ) -> dict[str, object]:
        delegated["packet"] = packet
        delegated["wave_id"] = wave_id
        delegated["result"] = result
        delegated["owner_kind"] = owner_kind
        return {"packet_id": packet.packet_id}

    with patch(
        "spec_orch.services.packet_executor.build_packet_attempt_payload",
        fake_build_packet_attempt_payload,
    ):
        result = await executor.execute_packet(packet, wave_id=0, cancel_event=cancel)

    assert result.packet_id == "p1"
    assert delegated["packet"] is packet
    assert delegated["wave_id"] == 0
    assert delegated["result"] is result
    assert delegated["owner_kind"] == "packet_executor"


@pytest.mark.asyncio
async def test_full_pipeline_packet_executor_delegates_attempt_payload_shaping(tmp_path: Path) -> None:
    executor = FullPipelinePacketExecutor(
        codex_bin="python",
        workspace=str(tmp_path),
        verify_commands={"check": ["python", "-c", "print('ok')"]},
    )
    packet = _make_packet("p2", "print('hello')")
    cancel = asyncio.Event()
    delegated: dict[str, object] = {}

    def fake_build_packet_attempt_payload(
        packet: WorkPacket,
        *,
        wave_id: int,
        result: PacketResult,
        owner_kind: str,
    ) -> dict[str, object]:
        delegated["packet"] = packet
        delegated["wave_id"] = wave_id
        delegated["result"] = result
        delegated["owner_kind"] = owner_kind
        return {"packet_id": packet.packet_id}

    with patch(
        "spec_orch.services.packet_executor.build_packet_attempt_payload",
        fake_build_packet_attempt_payload,
    ):
        result = await executor.execute_packet(packet, wave_id=1, cancel_event=cancel)

    assert result.packet_id == "p2"
    assert delegated["packet"] is packet
    assert delegated["wave_id"] == 1
    assert delegated["result"] is result
    assert delegated["owner_kind"] == "packet_executor"
