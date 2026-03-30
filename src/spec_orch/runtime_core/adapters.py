"""Owner-facing compatibility adapters between legacy services and runtime-core."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from spec_orch.domain.models import BuilderResult, PacketResult, WorkPacket
from spec_orch.runtime_core.writers import (
    write_issue_execution_payloads,
    write_round_supervision_payloads,
    write_worker_execution_payloads,
)


def write_issue_attempt_payloads(
    workspace: Path,
    *,
    live: dict[str, Any],
    conclusion: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Path]:
    return write_issue_execution_payloads(
        workspace,
        live=live,
        conclusion=conclusion,
        manifest=manifest,
    )


def _read_builder_report(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def write_worker_attempt_payloads(
    worker_dir: Path,
    *,
    builder_result: BuilderResult,
    session_name: str | None = None,
    extra_report: dict[str, Any] | None = None,
) -> dict[str, Path]:
    builder_report = _read_builder_report(builder_result.report_path) or {
        "succeeded": builder_result.succeeded,
        "command": builder_result.command,
        "stdout": builder_result.stdout,
        "stderr": builder_result.stderr,
        "adapter": builder_result.adapter,
        "agent": builder_result.agent,
        "metadata": builder_result.metadata,
    }
    if session_name:
        builder_report.setdefault("session_name", session_name)
    if extra_report:
        builder_report.update(extra_report)
    return write_worker_execution_payloads(worker_dir, builder_report=builder_report)


def write_round_cycle_payloads(
    round_dir: Path,
    *,
    summary: dict[str, Any],
    decision: dict[str, Any] | None,
) -> dict[str, Path]:
    return write_round_supervision_payloads(round_dir, summary=summary, decision=decision)


def build_packet_attempt_payload(
    packet: WorkPacket,
    *,
    wave_id: int,
    result: PacketResult,
    owner_kind: str,
) -> dict[str, Any]:
    return {
        "packet_id": packet.packet_id,
        "wave_id": wave_id,
        "title": packet.title,
        "run_class": packet.run_class,
        "owner_kind": owner_kind,
        "exit_code": result.exit_code,
        "duration_seconds": result.duration_seconds,
        "status": "succeeded" if result.exit_code == 0 else "failed",
    }


__all__ = [
    "build_packet_attempt_payload",
    "write_issue_attempt_payloads",
    "write_round_cycle_payloads",
    "write_worker_attempt_payloads",
]
