"""Mission execute-review-decide loop."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spec_orch.domain.models import (
    BuilderResult,
    ExecutionPlan,
    Issue,
    IssueContext,
    PlanPatch,
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
        round_history = self._load_history(mission_id, up_to_round=initial_round)
        plan = self._replay_plan_patches(plan, round_history)
        current_wave_idx = self._determine_start_wave(plan, round_history)
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
            try:
                worker_results = self._dispatch_wave(
                    mission_id=mission_id,
                    wave=wave,
                    round_history=round_history,
                )
            except Exception as exc:
                summary.status = RoundStatus.FAILED
                summary.completed_at = datetime.now(UTC).isoformat()
                summary.worker_results = [{"error": str(exc), "wave_id": current_wave_idx}]
                self._persist_round(round_dir, summary)
                round_history.append(summary)
                return RoundOrchestratorResult(completed=False, rounds=round_history)
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
            if decision.action is RoundAction.REPLAN_REMAINING:
                if decision.plan_patch is not None:
                    plan = self._apply_plan_patch(
                        plan,
                        current_wave_idx=current_wave_idx,
                        patch=decision.plan_patch,
                    )
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
                prompt = self._build_worker_prompt(
                    mission_id=mission_id,
                    packet=packet,
                    workspace=workspace,
                    decision=None,
                )
            else:
                prompt = self._build_worker_prompt(
                    mission_id=mission_id,
                    packet=packet,
                    workspace=workspace,
                    decision=last_decision,
                )

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

    def _load_history(self, mission_id: str, *, up_to_round: int) -> list[RoundSummary]:
        if up_to_round <= 0:
            return []
        rounds_dir = self._mission_dir(mission_id) / "rounds"
        if not rounds_dir.exists():
            return []

        history: list[RoundSummary] = []
        for round_dir in sorted(rounds_dir.glob("round-*")):
            summary_path = round_dir / "round_summary.json"
            if not summary_path.exists():
                continue
            try:
                summary = RoundSummary.from_dict(
                    json.loads(summary_path.read_text(encoding="utf-8"))
                )
            except Exception:
                continue
            if summary.round_id <= up_to_round:
                history.append(summary)
        return history

    def _replay_plan_patches(
        self,
        plan: ExecutionPlan,
        round_history: list[RoundSummary],
    ) -> ExecutionPlan:
        updated_plan = plan
        for summary in round_history:
            decision = summary.decision
            if decision is None or decision.plan_patch is None:
                continue
            updated_plan = self._apply_plan_patch(
                updated_plan,
                current_wave_idx=summary.wave_id,
                patch=decision.plan_patch,
            )
        return updated_plan

    @staticmethod
    def _determine_start_wave(plan: ExecutionPlan, round_history: list[RoundSummary]) -> int:
        if not round_history:
            return 0
        last_round = round_history[-1]
        last_action = last_round.decision.action if last_round.decision else None
        if last_action is RoundAction.CONTINUE:
            return min(last_round.wave_id + 1, len(plan.waves))
        return min(last_round.wave_id, max(len(plan.waves) - 1, 0))

    def _apply_plan_patch(
        self,
        plan: ExecutionPlan,
        *,
        current_wave_idx: int,
        patch: PlanPatch,
    ) -> ExecutionPlan:
        updated_waves = list(plan.waves)
        for wave_idx in range(current_wave_idx, len(updated_waves)):
            wave = updated_waves[wave_idx]
            packets: list[WorkPacket] = []
            for packet in wave.work_packets:
                if packet.packet_id in patch.removed_packet_ids:
                    continue
                patch_data = patch.modified_packets.get(packet.packet_id)
                if patch_data:
                    packet = replace(
                        packet,
                        title=patch_data.get("title", packet.title),
                        spec_section=patch_data.get("spec_section", packet.spec_section),
                        run_class=patch_data.get("run_class", packet.run_class),
                        files_in_scope=patch_data.get("files_in_scope", packet.files_in_scope),
                        files_out_of_scope=patch_data.get(
                            "files_out_of_scope", packet.files_out_of_scope
                        ),
                        depends_on=patch_data.get("depends_on", packet.depends_on),
                        acceptance_criteria=patch_data.get(
                            "acceptance_criteria", packet.acceptance_criteria
                        ),
                        verification_commands=patch_data.get(
                            "verification_commands", packet.verification_commands
                        ),
                        builder_prompt=patch_data.get("builder_prompt", packet.builder_prompt),
                    )
                packets.append(packet)
            updated_waves[wave_idx] = replace(wave, work_packets=packets)

        if patch.added_packets:
            target_wave_idx = min(current_wave_idx, len(updated_waves) - 1)
            if target_wave_idx >= 0:
                target_wave = updated_waves[target_wave_idx]
                added_packets = [
                    self._packet_from_patch(packet_data) for packet_data in patch.added_packets
                ]
                updated_waves[target_wave_idx] = replace(
                    target_wave,
                    work_packets=[*target_wave.work_packets, *added_packets],
                )

        return replace(plan, waves=updated_waves)

    @staticmethod
    def _packet_from_patch(packet_data: dict[str, Any]) -> WorkPacket:
        return WorkPacket(
            packet_id=str(packet_data["packet_id"]),
            title=packet_data.get("title", str(packet_data["packet_id"])),
            spec_section=packet_data.get("spec_section", ""),
            run_class=packet_data.get("run_class", "feature"),
            files_in_scope=packet_data.get("files_in_scope", []),
            files_out_of_scope=packet_data.get("files_out_of_scope", []),
            depends_on=packet_data.get("depends_on", []),
            acceptance_criteria=packet_data.get("acceptance_criteria", []),
            verification_commands=packet_data.get("verification_commands", {}),
            builder_prompt=packet_data.get("builder_prompt", ""),
            linear_issue_id=packet_data.get("linear_issue_id"),
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
        if decision is None:
            return self._build_initial_prompt(packet)
        if packet.builder_prompt:
            if decision.summary:
                return f"{decision.summary}\n\nUpdated packet brief:\n{packet.builder_prompt}"
            return packet.builder_prompt
        if not decision.summary:
            return self._build_initial_prompt(packet)
        return f"{decision.summary}\n\nContinue work on packet: {packet.title}"

    def _build_worker_prompt(
        self,
        *,
        mission_id: str,
        packet: WorkPacket,
        workspace: Path,
        decision: RoundDecision | None,
    ) -> str:
        from spec_orch.services.run_controller import RunController

        if decision is None:
            base_prompt = self._build_initial_prompt(packet)
        else:
            base_prompt = self._build_followup_prompt(packet, decision)

        issue = Issue(
            issue_id=packet.packet_id,
            title=packet.title,
            summary=base_prompt,
            builder_prompt=base_prompt,
            verification_commands=dict(packet.verification_commands),
            context=IssueContext(files_to_read=list(packet.files_in_scope)),
            acceptance_criteria=list(packet.acceptance_criteria),
            mission_id=mission_id,
            spec_section=packet.spec_section or None,
            run_class=packet.run_class,
        )
        return RunController._render_builder_envelope(
            issue,
            workspace,
            repo_root=self.repo_root,
        )

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
