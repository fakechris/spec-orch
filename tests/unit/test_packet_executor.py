from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

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

    mock_build_packet_attempt_payload = MagicMock(side_effect=fake_build_packet_attempt_payload)

    with patch(
        "spec_orch.services.packet_executor.build_packet_attempt_payload",
        mock_build_packet_attempt_payload,
    ):
        result = await executor.execute_packet(packet, wave_id=0, cancel_event=cancel)

    assert result.packet_id == "p1"
    mock_build_packet_attempt_payload.assert_called_once()
    assert delegated["packet"] is packet
    assert delegated["wave_id"] == 0
    assert delegated["result"] is result
    assert delegated["owner_kind"] == "packet_executor"


@pytest.mark.asyncio
async def test_subprocess_packet_executor_emits_single_completion_event(
    caplog: pytest.LogCaptureFixture,
) -> None:
    executor = SubprocessPacketExecutor(codex_bin="echo", workspace="/tmp")
    packet = _make_packet("p-single-log", "hello")
    cancel = asyncio.Event()

    with caplog.at_level(logging.INFO, logger="spec_orch.services.packet_executor"):
        result = await executor.execute_packet(packet, wave_id=2, cancel_event=cancel)

    assert result.packet_id == "p-single-log"
    completion_records = [
        record for record in caplog.records if record.msg in {"packet_completed", "packet_failed"}
    ]
    assert len(completion_records) == 1
    assert completion_records[0].msg == "packet_completed"


@pytest.mark.asyncio
async def test_full_pipeline_packet_executor_delegates_attempt_payload_shaping(
    tmp_path: Path,
) -> None:
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

    mock_build_packet_attempt_payload = MagicMock(side_effect=fake_build_packet_attempt_payload)

    with patch(
        "spec_orch.services.packet_executor.build_packet_attempt_payload",
        mock_build_packet_attempt_payload,
    ):
        result = await executor.execute_packet(packet, wave_id=1, cancel_event=cancel)

    assert result.packet_id == "p2"
    mock_build_packet_attempt_payload.assert_called_once()
    assert delegated["packet"] is packet
    assert delegated["wave_id"] == 1
    assert delegated["result"] is result
    assert delegated["owner_kind"] == "packet_executor"
