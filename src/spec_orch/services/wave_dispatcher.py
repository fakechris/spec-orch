from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spec_orch.domain.models import BuilderResult, RoundSummary, Wave, WorkPacket
from spec_orch.runtime_chain.models import ChainPhase, RuntimeChainEvent, RuntimeSubjectKind
from spec_orch.runtime_chain.store import append_chain_event


class WaveDispatcher:
    """Runs one wave of work packets and returns builder results."""

    def __init__(
        self,
        *,
        worker_factory: Any,
        event_logger: Any,
    ) -> None:
        self.worker_factory = worker_factory
        self.event_logger = event_logger

    def run(
        self,
        *,
        host: Any,
        mission_id: str,
        round_id: int,
        wave: Wave,
        round_history: list[RoundSummary],
        chain_id: str,
        chain_root: Path,
        round_span_id: str,
    ) -> list[tuple[WorkPacket, BuilderResult]]:
        results: list[tuple[WorkPacket, BuilderResult]] = []
        last_decision = round_history[-1].decision if round_history else None

        for packet in wave.work_packets:
            session_id = f"mission-{mission_id}-{packet.packet_id}"
            workspace = host._packet_workspace(mission_id, packet)
            workspace.mkdir(parents=True, exist_ok=True)
            packet_span_id = f"{round_span_id}:packet:{packet.packet_id}"
            append_chain_event(
                chain_root,
                RuntimeChainEvent(
                    chain_id=chain_id,
                    span_id=packet_span_id,
                    parent_span_id=round_span_id,
                    subject_kind=RuntimeSubjectKind.PACKET,
                    subject_id=packet.packet_id,
                    phase=ChainPhase.STARTED,
                    status_reason="packet_started",
                    artifact_refs={"workspace": str(workspace)},
                    updated_at=datetime.now(UTC).isoformat(),
                ),
            )

            handle = self.worker_factory.get(session_id)
            if handle is None:
                handle = self.worker_factory.create(session_id=session_id, workspace=workspace)
                prompt = host._build_worker_prompt(
                    mission_id=mission_id,
                    packet=packet,
                    workspace=workspace,
                    decision=None,
                )
            else:
                prompt = host._build_worker_prompt(
                    mission_id=mission_id,
                    packet=packet,
                    workspace=workspace,
                    decision=last_decision,
                )

            run_id = f"mission_{mission_id}_round_{round_id}_{packet.packet_id}"
            activity_logger = None
            try:
                activity_logger = self.event_logger.open_activity_logger(workspace)
                event_logger = self.event_logger.make_event_logger(
                    workspace=workspace,
                    run_id=run_id,
                    issue_id=packet.packet_id,
                    activity_logger=activity_logger,
                )

                self.event_logger.log_and_emit(
                    activity_logger=activity_logger,
                    workspace=workspace,
                    run_id=run_id,
                    issue_id=packet.packet_id,
                    component="mission_worker",
                    event_type="mission_packet_started",
                    message=f"Started packet {packet.packet_id}",
                    data={
                        "mission_id": mission_id,
                        "round_id": round_id,
                        "packet_id": packet.packet_id,
                        "session_id": session_id,
                    },
                )
                try:
                    result = handle.send(
                        prompt=prompt,
                        workspace=workspace,
                        event_logger=event_logger,
                        chain_root=chain_root,
                        chain_id=chain_id,
                        span_id=f"{packet_span_id}:worker",
                        parent_span_id=packet_span_id,
                    )
                except Exception as exc:
                    self.event_logger.log_and_emit(
                        activity_logger=activity_logger,
                        workspace=workspace,
                        run_id=run_id,
                        issue_id=packet.packet_id,
                        component="mission_worker",
                        event_type="mission_packet_completed",
                        severity="error",
                        message=f"Failed packet {packet.packet_id}: {exc}",
                        data={
                            "mission_id": mission_id,
                            "round_id": round_id,
                            "packet_id": packet.packet_id,
                            "succeeded": False,
                            "error": str(exc),
                        },
                    )
                    append_chain_event(
                        chain_root,
                        RuntimeChainEvent(
                            chain_id=chain_id,
                            span_id=packet_span_id,
                            parent_span_id=round_span_id,
                            subject_kind=RuntimeSubjectKind.PACKET,
                            subject_id=packet.packet_id,
                            phase=ChainPhase.FAILED,
                            status_reason="packet_failed",
                            artifact_refs={"workspace": str(workspace)},
                            updated_at=datetime.now(UTC).isoformat(),
                        ),
                    )
                    raise
                self.event_logger.log_and_emit(
                    activity_logger=activity_logger,
                    workspace=workspace,
                    run_id=run_id,
                    issue_id=packet.packet_id,
                    component="mission_worker",
                    event_type="mission_packet_completed",
                    severity="info" if result.succeeded else "error",
                    message=f"Completed packet {packet.packet_id}",
                    data={
                        "mission_id": mission_id,
                        "round_id": round_id,
                        "packet_id": packet.packet_id,
                        "succeeded": result.succeeded,
                        "report_path": str(result.report_path),
                    },
                )
                append_chain_event(
                    chain_root,
                    RuntimeChainEvent(
                        chain_id=chain_id,
                        span_id=packet_span_id,
                        parent_span_id=round_span_id,
                        subject_kind=RuntimeSubjectKind.PACKET,
                        subject_id=packet.packet_id,
                        phase=ChainPhase.COMPLETED if result.succeeded else ChainPhase.DEGRADED,
                        status_reason="packet_completed" if result.succeeded else "packet_degraded",
                        artifact_refs={
                            "workspace": str(workspace),
                            "builder_report": str(result.report_path),
                        },
                        updated_at=datetime.now(UTC).isoformat(),
                    ),
                )
            finally:
                if activity_logger is not None:
                    activity_logger.close()
            results.append((packet, result))

        return results
