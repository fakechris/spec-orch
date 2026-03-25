"""Mission execute-review-decide loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spec_orch.domain.models import (
    BuilderResult,
    ExecutionPlan,
    Issue,
    RoundAction,
    RoundArtifacts,
    RoundDecision,
    RoundStatus,
    RoundSummary,
    Wave,
    WorkPacket,
)
from spec_orch.domain.protocols import SupervisorAdapter, WorkerHandleFactory
from spec_orch.services.event_bus import Event, EventBus, EventTopic
from spec_orch.services.io import atomic_write_json
from spec_orch.services.node_context_registry import get_node_context_spec


@dataclass
class RoundOrchestratorResult:
    completed: bool
    paused: bool = False
    max_rounds_hit: bool = False
    rounds: list[RoundSummary] = field(default_factory=list)

    @property
    def last_decision(self) -> RoundDecision | None:
        if self.rounds and self.rounds[-1].decision is not None:
            return self.rounds[-1].decision
        return None


class RoundOrchestrator:
    """Runs wave-boundary supervised rounds for a mission."""

    DEFAULT_MAX_ROUNDS = 20

    def __init__(
        self,
        *,
        repo_root: Path,
        supervisor: SupervisorAdapter,
        worker_factory: WorkerHandleFactory,
        context_assembler: Any,
        event_bus: EventBus | None = None,
        max_rounds: int = DEFAULT_MAX_ROUNDS,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.supervisor = supervisor
        self.worker_factory = worker_factory
        self.context_assembler = context_assembler
        self.event_bus = event_bus
        self.max_rounds = max_rounds

    def run_supervised(
        self,
        *,
        mission_id: str,
        plan: ExecutionPlan,
        initial_round: int = 0,
    ) -> RoundOrchestratorResult:
        round_history: list[RoundSummary] = []
        current_wave_idx = 0
        round_id = initial_round

        while round_id < self.max_rounds and current_wave_idx < len(plan.waves):
            round_id += 1
            wave = plan.waves[current_wave_idx]
            round_dir = self._round_dir(mission_id, round_id)
            round_dir.mkdir(parents=True, exist_ok=True)

            summary = RoundSummary(
                round_id=round_id,
                wave_id=current_wave_idx,
                status=RoundStatus.EXECUTING,
            )
            worker_results = self._dispatch_wave(
                mission_id=mission_id,
                wave=wave,
                round_history=round_history,
            )
            summary.worker_results = [
                self._serialize_result(packet, result) for packet, result in worker_results
            ]
            summary.status = RoundStatus.COLLECTING

            artifacts = self._collect_artifacts(
                mission_id=mission_id,
                round_id=round_id,
                worker_results=worker_results,
            )
            summary.status = RoundStatus.REVIEWING

            context = self.context_assembler.assemble(
                get_node_context_spec("supervisor"),
                Issue(
                    issue_id=mission_id,
                    title=f"Mission {mission_id}",
                    summary=f"Round {round_id} review",
                ),
                self._mission_dir(mission_id),
                repo_root=self.repo_root,
            )
            decision = self.supervisor.review_round(
                round_artifacts=artifacts,
                plan=plan,
                round_history=round_history,
                context=context,
            )
            summary.decision = decision
            summary.status = RoundStatus.DECIDED
            summary.completed_at = datetime.now(UTC).isoformat()
            self._persist_round(round_dir, summary)
            round_history.append(summary)

            self._apply_session_ops(mission_id, decision)

            if decision.action is RoundAction.CONTINUE:
                current_wave_idx += 1
                if current_wave_idx >= len(plan.waves):
                    return RoundOrchestratorResult(completed=True, rounds=round_history)
                continue
            if decision.action is RoundAction.RETRY:
                continue
            if decision.action is RoundAction.ASK_HUMAN:
                self._emit_round_paused(mission_id, round_id, decision)
                return RoundOrchestratorResult(
                    completed=False,
                    paused=True,
                    rounds=round_history,
                )
            if decision.action is RoundAction.STOP:
                return RoundOrchestratorResult(completed=True, rounds=round_history)
            return RoundOrchestratorResult(completed=False, rounds=round_history)

        return RoundOrchestratorResult(
            completed=False,
            max_rounds_hit=current_wave_idx < len(plan.waves),
            rounds=round_history,
        )

    def _dispatch_wave(
        self,
        *,
        mission_id: str,
        wave: Wave,
        round_history: list[RoundSummary],
    ) -> list[tuple[WorkPacket, BuilderResult]]:
        results: list[tuple[WorkPacket, BuilderResult]] = []
        last_decision = round_history[-1].decision if round_history else None

        for packet in wave.work_packets:
            session_id = f"mission-{mission_id}-{packet.packet_id}"
            workspace = self._packet_workspace(mission_id, packet)
            workspace.mkdir(parents=True, exist_ok=True)

            handle = self.worker_factory.get(session_id)
            if handle is None:
                handle = self.worker_factory.create(session_id=session_id, workspace=workspace)
                prompt = self._build_initial_prompt(packet)
            else:
                prompt = self._build_followup_prompt(packet, last_decision)

            result = handle.send(prompt=prompt, workspace=workspace)
            results.append((packet, result))

        return results

    def _collect_artifacts(
        self,
        *,
        mission_id: str,
        round_id: int,
        worker_results: list[tuple[WorkPacket, BuilderResult]],
    ) -> RoundArtifacts:
        return RoundArtifacts(
            round_id=round_id,
            mission_id=mission_id,
            builder_reports=[
                {
                    "packet_id": packet.packet_id,
                    "succeeded": result.succeeded,
                    "adapter": result.adapter,
                    "agent": result.agent,
                    "report_path": str(result.report_path),
                }
                for packet, result in worker_results
            ],
            worker_session_ids=[
                f"mission-{mission_id}-{packet.packet_id}" for packet, _ in worker_results
            ],
        )

    def _persist_round(self, round_dir: Path, summary: RoundSummary) -> None:
        atomic_write_json(round_dir / "round_summary.json", summary.to_dict())
        if summary.decision is not None:
            atomic_write_json(round_dir / "round_decision.json", summary.decision.to_dict())

    def _apply_session_ops(self, mission_id: str, decision: RoundDecision) -> None:
        mission_workspace = self._mission_dir(mission_id)
        for session_id in decision.session_ops.cancel:
            handle = self.worker_factory.get(session_id)
            if handle is not None:
                handle.cancel(mission_workspace)
                handle.close(mission_workspace)
        for session_id in decision.session_ops.spawn:
            self.worker_factory.create(session_id=session_id, workspace=mission_workspace)

    def _emit_round_paused(self, mission_id: str, round_id: int, decision: RoundDecision) -> None:
        if self.event_bus is None:
            return
        self.event_bus.publish(
            Event(
                topic=EventTopic.SYSTEM,
                payload={
                    "mission_id": mission_id,
                    "round_id": round_id,
                    "blocking_questions": decision.blocking_questions,
                    "state": "paused",
                },
                source="round_orchestrator",
            )
        )

    def _build_initial_prompt(self, packet: WorkPacket) -> str:
        return packet.builder_prompt or f"Implement {packet.title}"

    def _build_followup_prompt(
        self,
        packet: WorkPacket,
        decision: RoundDecision | None,
    ) -> str:
        if decision is None or not decision.summary:
            return self._build_initial_prompt(packet)
        return f"{decision.summary}\n\nContinue work on packet: {packet.title}"

    def _serialize_result(self, packet: WorkPacket, result: BuilderResult) -> dict[str, Any]:
        return {
            "packet_id": packet.packet_id,
            "succeeded": result.succeeded,
            "adapter": result.adapter,
            "agent": result.agent,
            "report_path": str(result.report_path),
        }

    def _mission_dir(self, mission_id: str) -> Path:
        return self.repo_root / "docs" / "specs" / mission_id

    def _round_dir(self, mission_id: str, round_id: int) -> Path:
        return self._mission_dir(mission_id) / "rounds" / f"round-{round_id:02d}"

    def _packet_workspace(self, mission_id: str, packet: WorkPacket) -> Path:
        return self._mission_dir(mission_id) / "workers" / packet.packet_id
