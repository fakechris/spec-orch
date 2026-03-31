"""Mission execute-review-decide loop."""

from __future__ import annotations

import inspect
import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any, TypeVar
from uuid import uuid4

from spec_orch.acceptance_core.calibration import (
    FixtureGraduationStage,
    append_fixture_graduation_event,
    build_fixture_graduation_event,
    dashboard_surface_pack_v1,
    load_fixture_graduation_events,
    qualifies_for_fixture_candidate,
    write_fixture_candidate_seed,
)
from spec_orch.acceptance_core.models import (
    AcceptanceRunMode,
    build_acceptance_judgments,
    run_mode_from_legacy_acceptance_mode,
)
from spec_orch.acceptance_core.routing import (
    AcceptanceRequest,
    AcceptanceRoutingDecision,
    AcceptanceSurfacePackRef,
    build_acceptance_routing_decision,
)
from spec_orch.acceptance_runtime.graph_registry import graph_definition_for
from spec_orch.acceptance_runtime.runner import run_acceptance_graph
from spec_orch.decision_core.interventions import build_intervention_from_record
from spec_orch.decision_core.records import build_round_review_decision_record
from spec_orch.decision_core.review_queue import append_intervention
from spec_orch.domain.models import (
    AcceptanceCampaign,
    AcceptanceInteractionStep,
    AcceptanceMode,
    AcceptanceReviewResult,
    BuilderResult,
    ExecutionPlan,
    GateInput,
    Issue,
    IssueContext,
    Mission,
    PlanPatch,
    ReviewSummary,
    RoundAction,
    RoundArtifacts,
    RoundDecision,
    RoundStatus,
    RoundSummary,
    Wave,
    WorkPacket,
)
from spec_orch.domain.protocols import (
    AcceptanceEvaluatorAdapter,
    SupervisorAdapter,
    VisualEvaluatorAdapter,
    WorkerHandleFactory,
)
from spec_orch.runtime_chain.models import (
    ChainPhase,
    RuntimeChainEvent,
    RuntimeChainStatus,
    RuntimeSubjectKind,
)
from spec_orch.runtime_chain.store import append_chain_event, write_chain_status
from spec_orch.runtime_core.writers import write_round_supervision_payloads
from spec_orch.services.acceptance.browser_evidence import collect_playwright_browser_evidence
from spec_orch.services.event_bus import Event, EventBus, EventTopic
from spec_orch.services.gate_service import GatePolicy, GateService
from spec_orch.services.io import atomic_write_json
from spec_orch.services.node_context_registry import get_node_context_spec
from spec_orch.services.resource_loader import load_json_resource
from spec_orch.services.run_event_logger import RunEventLogger
from spec_orch.services.telemetry_service import TelemetryService
from spec_orch.services.verification_service import VerificationService

logger = logging.getLogger(__name__)
T = TypeVar("T")


def _load_repo_fixture_json(repo_root: Path, fixture_name: str) -> dict[str, Any]:
    return load_json_resource(resource_name=fixture_name, repo_root=repo_root)


def _substitute_fresh_campaign_placeholders(value: Any, *, mission_id: str) -> Any:
    if isinstance(value, str):
        return value.replace("{mission_id}", mission_id)
    if isinstance(value, list):
        return [
            _substitute_fresh_campaign_placeholders(item, mission_id=mission_id) for item in value
        ]
    if isinstance(value, dict):
        return {
            _substitute_fresh_campaign_placeholders(key, mission_id=mission_id): (
                _substitute_fresh_campaign_placeholders(item, mission_id=mission_id)
            )
            for key, item in value.items()
        }
    return value


def build_fresh_acpx_post_run_campaign(repo_root: Path, mission_id: str) -> AcceptanceCampaign:
    payload = _load_repo_fixture_json(repo_root, "fresh_acpx_campaign.json")
    substituted = _substitute_fresh_campaign_placeholders(payload, mission_id=mission_id)
    return AcceptanceCampaign.from_dict(substituted)


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
        visual_evaluator: VisualEvaluatorAdapter | None = None,
        acceptance_evaluator: AcceptanceEvaluatorAdapter | None = None,
        acceptance_filer: Any | None = None,
        event_bus: EventBus | None = None,
        max_rounds: int = DEFAULT_MAX_ROUNDS,
        live_stream: IO[str] | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.supervisor = supervisor
        self.worker_factory = worker_factory
        self.context_assembler = context_assembler
        self.visual_evaluator = visual_evaluator
        self.acceptance_evaluator = acceptance_evaluator
        self.acceptance_filer = acceptance_filer
        self.event_bus = event_bus
        self.max_rounds = max_rounds
        self._event_logger = RunEventLogger(
            telemetry_service=TelemetryService(),
            live_stream=live_stream,
        )

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
        chain_root = self._mission_operator_dir(mission_id) / "runtime_chain"
        chain_id = self._new_chain_id(mission_id)
        mission_span_id = f"{chain_id}:mission"
        updated_at = datetime.now(UTC).isoformat()
        append_chain_event(
            chain_root,
            RuntimeChainEvent(
                chain_id=chain_id,
                span_id=mission_span_id,
                parent_span_id=None,
                subject_kind=RuntimeSubjectKind.MISSION,
                subject_id=mission_id,
                phase=ChainPhase.STARTED,
                status_reason="mission_supervision_started",
                artifact_refs={"mission_root": str(self._mission_dir(mission_id))},
                updated_at=updated_at,
            ),
        )
        write_chain_status(
            chain_root,
            RuntimeChainStatus(
                chain_id=chain_id,
                active_span_id=mission_span_id,
                subject_kind=RuntimeSubjectKind.MISSION,
                subject_id=mission_id,
                phase=ChainPhase.STARTED,
                status_reason="mission_supervision_started",
                artifact_refs={"mission_root": str(self._mission_dir(mission_id))},
                updated_at=updated_at,
            ),
        )

        while round_id < self.max_rounds and current_wave_idx < len(plan.waves):
            round_id += 1
            wave = plan.waves[current_wave_idx]
            round_dir = self._round_dir(mission_id, round_id)
            round_dir.mkdir(parents=True, exist_ok=True)
            round_span_id = f"{chain_id}:round:{round_id:02d}"
            append_chain_event(
                chain_root,
                RuntimeChainEvent(
                    chain_id=chain_id,
                    span_id=round_span_id,
                    parent_span_id=mission_span_id,
                    subject_kind=RuntimeSubjectKind.ROUND,
                    subject_id=f"round-{round_id:02d}",
                    phase=ChainPhase.STARTED,
                    status_reason="round_started",
                    artifact_refs={"round_dir": str(round_dir)},
                    updated_at=datetime.now(UTC).isoformat(),
                ),
            )

            summary = RoundSummary(
                round_id=round_id,
                wave_id=current_wave_idx,
                status=RoundStatus.EXECUTING,
            )
            try:
                worker_results = self._dispatch_wave(
                    mission_id=mission_id,
                    round_id=round_id,
                    wave=wave,
                    round_history=round_history,
                    chain_id=chain_id,
                    chain_root=chain_root,
                    round_span_id=round_span_id,
                )
            except Exception as exc:
                summary.status = RoundStatus.FAILED
                summary.completed_at = datetime.now(UTC).isoformat()
                summary.worker_results = [{"error": str(exc), "wave_id": current_wave_idx}]
                self._persist_round(round_dir, summary)
                append_chain_event(
                    chain_root,
                    RuntimeChainEvent(
                        chain_id=chain_id,
                        span_id=round_span_id,
                        parent_span_id=mission_span_id,
                        subject_kind=RuntimeSubjectKind.ROUND,
                        subject_id=f"round-{round_id:02d}",
                        phase=ChainPhase.FAILED,
                        status_reason="round_failed",
                        artifact_refs={"round_dir": str(round_dir)},
                        updated_at=datetime.now(UTC).isoformat(),
                    ),
                )
                round_history.append(summary)
                return RoundOrchestratorResult(completed=False, rounds=round_history)
            summary.worker_results = [
                self._serialize_result(packet, result) for packet, result in worker_results
            ]
            summary.status = RoundStatus.COLLECTING

            artifacts = self._collect_artifacts(
                mission_id=mission_id,
                round_id=round_id,
                wave=wave,
                worker_results=worker_results,
                round_dir=round_dir,
            )
            supervisor_issue = self._build_supervisor_issue(
                mission_id=mission_id,
                round_id=round_id,
                wave=wave,
            )
            self._write_supervisor_task_spec(
                round_dir=round_dir,
                mission_id=mission_id,
                wave=wave,
            )
            summary.status = RoundStatus.REVIEWING

            assembled_context = self.context_assembler.assemble(
                get_node_context_spec("supervisor"),
                supervisor_issue,
                round_dir,
                repo_root=self.repo_root,
            )
            context = self._build_supervisor_context(
                mission_id=mission_id,
                round_id=round_id,
                wave=wave,
                issue=supervisor_issue,
                assembled_context=assembled_context,
                artifacts=artifacts,
            )
            decision = self._call_runtime_chain_aware(
                self.supervisor.review_round,
                round_artifacts=artifacts,
                plan=plan,
                round_history=round_history,
                context=context,
                chain_root=chain_root,
                chain_id=chain_id,
                span_id=f"{round_span_id}:supervisor",
                parent_span_id=round_span_id,
            )
            summary.decision = decision
            summary.status = RoundStatus.DECIDED
            summary.completed_at = datetime.now(UTC).isoformat()
            self._persist_round(round_dir, summary)
            append_chain_event(
                chain_root,
                RuntimeChainEvent(
                    chain_id=chain_id,
                    span_id=round_span_id,
                    parent_span_id=mission_span_id,
                    subject_kind=RuntimeSubjectKind.ROUND,
                    subject_id=f"round-{round_id:02d}",
                    phase=ChainPhase.COMPLETED,
                    status_reason="round_completed",
                    artifact_refs={"round_dir": str(round_dir)},
                    updated_at=datetime.now(UTC).isoformat(),
                ),
            )
            round_history.append(summary)
            self._run_acceptance_evaluation(
                mission_id=mission_id,
                round_id=round_id,
                round_dir=round_dir,
                worker_results=worker_results,
                artifacts=artifacts,
                summary=summary,
                chain_root=chain_root,
                chain_id=chain_id,
                round_span_id=round_span_id,
            )

            self._apply_session_ops(mission_id, decision)

            if decision.action is RoundAction.CONTINUE:
                current_wave_idx += 1
                if current_wave_idx >= len(plan.waves):
                    return RoundOrchestratorResult(completed=True, rounds=round_history)
                continue
            if decision.action is RoundAction.RETRY:
                if decision.plan_patch is not None:
                    plan = self._apply_plan_patch(
                        plan,
                        current_wave_idx=current_wave_idx,
                        patch=decision.plan_patch,
                    )
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
                self._create_human_intervention(
                    mission_id=mission_id,
                    round_id=round_id,
                    decision=decision,
                )
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
            workspace = self._packet_workspace(mission_id, packet)
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

            run_id = f"mission_{mission_id}_round_{round_id}_{packet.packet_id}"
            activity_logger = None
            try:
                activity_logger = self._event_logger.open_activity_logger(workspace)
                event_logger = self._event_logger.make_event_logger(
                    workspace=workspace,
                    run_id=run_id,
                    issue_id=packet.packet_id,
                    activity_logger=activity_logger,
                )

                self._event_logger.log_and_emit(
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
                    self._event_logger.log_and_emit(
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
                self._event_logger.log_and_emit(
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

    def _collect_artifacts(
        self,
        *,
        mission_id: str,
        round_id: int,
        wave: Wave,
        worker_results: list[tuple[WorkPacket, BuilderResult]],
        round_dir: Path,
    ) -> RoundArtifacts:
        visual_evaluation = self._run_visual_evaluation(
            mission_id=mission_id,
            round_id=round_id,
            wave=wave,
            worker_results=worker_results,
            round_dir=round_dir,
        )
        verification_outputs: list[dict[str, Any]] = []
        gate_verdicts: list[dict[str, Any]] = []
        manifest_paths: list[str] = []
        verification_service = VerificationService()
        gate_service = GateService(
            policy=GatePolicy(required_conditions={"builder", "verification"})
        )

        for packet, result in worker_results:
            workspace = self._packet_workspace(mission_id, packet)
            if result.report_path.exists():
                manifest_paths.append(str(result.report_path))
            for file_path in packet.files_in_scope:
                scoped_path = workspace / file_path
                if scoped_path.exists():
                    manifest_paths.append(str(scoped_path))
            if not packet.verification_commands:
                continue

            verification = verification_service.run(
                issue=Issue(
                    issue_id=packet.packet_id,
                    title=packet.title,
                    summary=packet.title,
                    verification_commands=dict(packet.verification_commands),
                    context=IssueContext(),
                    acceptance_criteria=list(packet.acceptance_criteria),
                ),
                workspace=workspace,
            )
            verification_outputs.append(
                {
                    "packet_id": packet.packet_id,
                    "workspace": str(workspace),
                    "all_passed": verification.all_passed,
                    "step_results": dict(verification.step_results),
                    "details": {
                        step: {
                            "command": detail.command,
                            "exit_code": detail.exit_code,
                            "stdout": detail.stdout,
                            "stderr": detail.stderr,
                        }
                        for step, detail in verification.details.items()
                    },
                }
            )
            scope_proof = self._build_packet_scope_proof(
                workspace=workspace,
                packet=packet,
                report_path=result.report_path,
            )
            gate = gate_service.evaluate(
                GateInput(
                    builder_succeeded=result.succeeded,
                    verification=verification,
                    review=ReviewSummary(verdict="not_applicable"),
                )
            )
            failed_conditions = list(gate.failed_conditions)
            if not scope_proof["all_in_scope"] and "scope" not in failed_conditions:
                failed_conditions.append("scope")
            gate_verdicts.append(
                {
                    "packet_id": packet.packet_id,
                    "mergeable": gate.mergeable and scope_proof["all_in_scope"],
                    "failed_conditions": failed_conditions,
                    "scope": scope_proof,
                }
            )

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
            verification_outputs=verification_outputs,
            gate_verdicts=gate_verdicts,
            manifest_paths=self._unique_preserve_order(manifest_paths),
            worker_session_ids=[
                f"mission-{mission_id}-{packet.packet_id}" for packet, _ in worker_results
            ],
            visual_evaluation=visual_evaluation,
        )

    def _build_packet_scope_proof(
        self,
        *,
        workspace: Path,
        packet: WorkPacket,
        report_path: Path,
    ) -> dict[str, Any]:
        allowed = [str(path).strip() for path in packet.files_in_scope if str(path).strip()]
        allowed_set = set(allowed)
        excluded_paths = {report_path.resolve()}
        excluded_prefixes = ("telemetry/",)
        excluded_filenames = {"btw_context.md", "task.spec.md"}
        realized_files: list[str] = []
        for path in workspace.rglob("*"):
            if not path.is_file():
                continue
            try:
                resolved = path.resolve()
            except OSError:
                resolved = path
            if resolved in excluded_paths:
                continue
            relative_path = path.relative_to(workspace).as_posix()
            if relative_path.startswith(excluded_prefixes) or relative_path in excluded_filenames:
                continue
            realized_files.append(relative_path)
        realized_files = self._unique_preserve_order(realized_files)
        out_of_scope_files = [path for path in realized_files if path not in allowed_set]
        return {
            "allowed_files": allowed,
            "realized_files": realized_files,
            "out_of_scope_files": out_of_scope_files,
            "all_in_scope": not out_of_scope_files,
        }

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
        write_round_supervision_payloads(
            round_dir,
            summary=summary.to_dict(),
            decision=summary.decision.to_dict() if summary.decision is not None else None,
        )

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

    def _create_human_intervention(
        self,
        *,
        mission_id: str,
        round_id: int,
        decision: RoundDecision,
    ) -> None:
        record = build_round_review_decision_record(
            mission_id=mission_id,
            round_id=round_id,
            owner="round_orchestrator",
            decision=decision,
        )
        intervention = build_intervention_from_record(
            record,
            intervention_id=f"{mission_id}-round-{round_id}-approval",
        )
        append_intervention(
            self.repo_root,
            mission_id,
            round_id=round_id,
            intervention=intervention,
            decision_record_id=record.record_id,
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

        files_to_read: list[str] = []
        target_files: list[str] = []
        for rel_path in packet.files_in_scope:
            normalized = str(rel_path).strip()
            if not normalized:
                continue
            if (workspace / normalized).exists():
                files_to_read.append(normalized)
            else:
                target_files.append(normalized)

        issue = Issue(
            issue_id=packet.packet_id,
            title=packet.title,
            summary=base_prompt,
            builder_prompt=base_prompt,
            verification_commands=dict(packet.verification_commands),
            context=IssueContext(
                files_to_read=files_to_read,
                target_files=target_files,
            ),
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
        telemetry_dir = result.report_path.parent / "telemetry"
        return {
            "packet_id": packet.packet_id,
            "succeeded": result.succeeded,
            "adapter": result.adapter,
            "agent": result.agent,
            "report_path": str(result.report_path),
            "incoming_events_path": self._maybe_path(telemetry_dir / "incoming_events.jsonl"),
            "events_path": self._maybe_path(telemetry_dir / "events.jsonl"),
            "activity_log_path": self._maybe_path(telemetry_dir / "activity.log"),
        }

    @staticmethod
    def _maybe_path(path: Path) -> str | None:
        if path.exists():
            return str(path)
        return None

    def _mission_dir(self, mission_id: str) -> Path:
        return self.repo_root / "docs" / "specs" / mission_id

    def _mission_operator_dir(self, mission_id: str) -> Path:
        path = self._mission_dir(mission_id) / "operator"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _call_runtime_chain_aware(func: Callable[..., T], /, **kwargs: Any) -> T:
        signature = inspect.signature(func)
        supported_kwargs = {
            name: value for name, value in kwargs.items() if name in signature.parameters
        }
        return func(**supported_kwargs)

    @staticmethod
    def _new_chain_id(mission_id: str) -> str:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        return f"chain_{mission_id}_{timestamp}_{uuid4().hex[:8]}"

    def _round_dir(self, mission_id: str, round_id: int) -> Path:
        return self._mission_dir(mission_id) / "rounds" / f"round-{round_id:02d}"

    def _packet_workspace(self, mission_id: str, packet: WorkPacket) -> Path:
        return self._mission_dir(mission_id) / "workers" / packet.packet_id

    def _run_visual_evaluation(
        self,
        *,
        mission_id: str,
        round_id: int,
        wave: Wave,
        worker_results: list[tuple[WorkPacket, BuilderResult]],
        round_dir: Path,
    ) -> Any | None:
        if self.visual_evaluator is None:
            return None
        try:
            result = self.visual_evaluator.evaluate_round(
                mission_id=mission_id,
                round_id=round_id,
                wave=wave,
                worker_results=worker_results,
                repo_root=self.repo_root,
                round_dir=round_dir,
            )
        except Exception:
            logger.exception("Visual evaluation failed for %s round %s", mission_id, round_id)
            return None
        if result is not None:
            atomic_write_json(round_dir / "visual_evaluation.json", result.to_dict())
        return result

    def _run_acceptance_evaluation(
        self,
        *,
        mission_id: str,
        round_id: int,
        round_dir: Path,
        worker_results: list[tuple[WorkPacket, BuilderResult]],
        artifacts: RoundArtifacts,
        summary: RoundSummary,
        chain_root: Path,
        chain_id: str,
        round_span_id: str,
    ) -> AcceptanceReviewResult | None:
        if self.acceptance_evaluator is None:
            return None
        acceptance_artifacts = self._build_acceptance_artifacts(
            mission_id=mission_id,
            round_id=round_id,
            artifacts=artifacts,
            summary=summary,
        )
        campaign = self._build_acceptance_campaign(
            mission_id=mission_id,
            artifacts=acceptance_artifacts,
        )
        routing_decision = self._build_acceptance_routing_decision(
            mission_id=mission_id,
            artifacts=acceptance_artifacts,
        )
        browser_evidence = self._collect_acceptance_browser_evidence(
            mission_id=mission_id,
            round_id=round_id,
            round_dir=round_dir,
            campaign=campaign,
        )
        if browser_evidence is not None:
            acceptance_artifacts["browser_evidence"] = browser_evidence
        try:
            graph_trace = self._run_acceptance_graph_trace(
                mission_id=mission_id,
                round_id=round_id,
                round_dir=round_dir,
                campaign=campaign,
                routing_decision=routing_decision,
                acceptance_artifacts=acceptance_artifacts,
                chain_root=chain_root,
                chain_id=chain_id,
                round_span_id=round_span_id,
            )
        except Exception as exc:
            logger.exception(
                "Acceptance graph trace failed for %s round %s",
                mission_id,
                round_id,
            )
            acceptance_artifacts["graph_trace_error"] = str(exc)
        else:
            if graph_trace:
                acceptance_artifacts.update(graph_trace)
        try:
            result = self._call_runtime_chain_aware(
                self.acceptance_evaluator.evaluate_acceptance,
                mission_id=mission_id,
                round_id=round_id,
                round_dir=round_dir,
                worker_results=worker_results,
                artifacts=acceptance_artifacts,
                repo_root=self.repo_root,
                campaign=campaign,
                chain_root=chain_root,
                chain_id=chain_id,
                span_id=f"{round_span_id}:acceptance-review",
                parent_span_id=round_span_id,
            )
        except Exception:
            logger.exception("Acceptance evaluation failed for %s round %s", mission_id, round_id)
            return None
        if result is None:
            return None
        if self.acceptance_filer is not None:
            try:
                result = self.acceptance_filer.apply(
                    result,
                    mission_id=mission_id,
                    round_id=round_id,
                )
            except Exception as exc:
                result = self._mark_acceptance_filing_failure(result, str(exc))
        atomic_write_json(round_dir / "acceptance_review.json", result.to_dict())
        judgments = build_acceptance_judgments(result)
        try:
            from spec_orch.services.memory.service import get_memory_service

            memory = get_memory_service(repo_root=self.repo_root)
            memory.record_acceptance_judgments(
                mission_id=mission_id,
                round_id=round_id,
                judgments=judgments,
            )
            self._record_fixture_candidate_graduations(
                mission_id=mission_id,
                source_record_id=f"acceptance:round-{round_id}",
                judgments=judgments,
                review=result,
                memory=memory,
            )
        except Exception:
            logger.warning(
                "Failed to record acceptance judgments to memory",
                extra={"mission_id": mission_id, "round_id": round_id},
                exc_info=True,
            )
        return result

    def _run_acceptance_graph_trace(
        self,
        *,
        mission_id: str,
        round_id: int,
        round_dir: Path,
        campaign: AcceptanceCampaign,
        routing_decision: AcceptanceRoutingDecision,
        acceptance_artifacts: dict[str, Any],
        chain_root: Path,
        chain_id: str,
        round_span_id: str,
    ) -> dict[str, Any]:
        if self.acceptance_evaluator is None:
            return {}
        step_invoker = getattr(self.acceptance_evaluator, "invoke_acceptance_graph_step", None)
        if not callable(step_invoker):
            return {}
        try:
            from spec_orch.services.memory.service import get_memory_service

            memory = get_memory_service(repo_root=self.repo_root)
        except Exception:
            memory = None
        graph = graph_definition_for(routing_decision.graph_profile)
        observability_root = (
            self.repo_root
            / "docs"
            / "specs"
            / mission_id
            / "operator"
            / "observability"
            / f"round-{round_id:02d}-acceptance-graph"
        )
        trace = run_acceptance_graph(
            base_dir=round_dir,
            run_id=f"acceptance-{routing_decision.graph_profile.value}",
            graph=graph,
            mission_id=mission_id,
            round_id=round_id,
            goal=campaign.goal,
            target=f"mission:{mission_id}",
            evidence=acceptance_artifacts,
            compare_overlay=routing_decision.compare_overlay,
            invoke=lambda system_prompt, user_prompt: step_invoker(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            ),
            chain_root=chain_root,
            chain_id=chain_id,
            span_id=f"{round_span_id}:acceptance-graph",
            parent_span_id=round_span_id,
            observability_root=observability_root,
            memory_service=memory,
        )
        normalized: dict[str, Any] = {"graph_profile": trace["graph_profile"]}
        graph_run_path = Path(trace["graph_run"])
        if graph_run_path.is_absolute():
            try:
                normalized["graph_run"] = str(graph_run_path.relative_to(self.repo_root))
            except ValueError:
                normalized["graph_run"] = str(graph_run_path)
        else:
            normalized["graph_run"] = str(graph_run_path)

        step_artifacts: list[str] = []
        for item in trace.get("step_artifacts", []):
            path = Path(item)
            if path.is_absolute():
                try:
                    step_artifacts.append(str(path.relative_to(self.repo_root)))
                except ValueError:
                    step_artifacts.append(str(path))
            else:
                step_artifacts.append(str(path))
        normalized["step_artifacts"] = step_artifacts
        normalized["graph_transitions"] = [
            str(item) for item in trace.get("graph_transitions", []) if str(item).strip()
        ]
        normalized["final_transition"] = str(trace.get("final_transition", "") or "")
        return normalized

    def _record_fixture_candidate_graduations(
        self,
        *,
        mission_id: str,
        source_record_id: str,
        judgments: list[Any],
        review: AcceptanceReviewResult,
        memory: Any,
    ) -> None:
        reviewed_findings = memory.get_reviewed_acceptance_findings(top_k=200)
        existing_events = load_fixture_graduation_events(self.repo_root, mission_id)
        existing_markers = {
            str(
                event.get("dedupe_key") or event.get("finding_id") or event.get("judgment_id") or ""
            )
            for event in existing_events
            if isinstance(event, dict)
        }
        for judgment in judgments:
            candidate = getattr(judgment, "candidate", None)
            if candidate is None:
                continue
            repeat_count = self._fixture_candidate_repeat_count(
                judgment=judgment,
                reviewed_findings=reviewed_findings,
            )
            if not qualifies_for_fixture_candidate(judgment, repeat_count=repeat_count):
                continue
            marker = str(
                candidate.dedupe_key or candidate.finding_id or judgment.judgment_id or ""
            ).strip()
            if marker and marker in existing_markers:
                continue
            payload = build_fixture_graduation_event(
                mission_id=mission_id,
                judgment=judgment,
                stage=FixtureGraduationStage.FIXTURE_CANDIDATE,
                source_record_id=source_record_id,
                repeat_count=repeat_count,
                review_artifacts=review.artifacts if isinstance(review.artifacts, dict) else {},
            )
            append_fixture_graduation_event(
                self.repo_root,
                mission_id=mission_id,
                judgment_id=str(payload["judgment_id"]),
                finding_id=str(payload.get("finding_id") or ""),
                stage=FixtureGraduationStage.FIXTURE_CANDIDATE,
                summary=str(payload["summary"]),
                source_record_id=str(payload["source_record_id"]),
                evidence_refs=list(payload.get("evidence_refs", [])),
                repeat_count=int(payload.get("repeat_count", 0)),
                dedupe_key=str(payload.get("dedupe_key") or ""),
                baseline_ref=str(payload.get("baseline_ref") or ""),
                graph_profile=str(payload.get("graph_profile") or ""),
                graph_run=str(payload.get("graph_run") or ""),
                step_artifacts=list(payload.get("step_artifacts", [])),
                graph_transitions=list(payload.get("graph_transitions", [])),
                final_transition=str(payload.get("final_transition") or ""),
                workflow_tuning_notes=list(payload.get("workflow_tuning_notes", [])),
                route=str(payload.get("route") or ""),
                origin_step=str(payload.get("origin_step") or ""),
                promotion_test=str(payload.get("promotion_test") or ""),
            )
            write_fixture_candidate_seed(
                self.repo_root,
                mission_id=mission_id,
                event=payload,
                review_payload=review.to_dict(),
            )
            if marker:
                existing_markers.add(marker)

    @staticmethod
    def _fixture_candidate_repeat_count(
        *,
        judgment: Any,
        reviewed_findings: list[dict[str, Any]],
    ) -> int:
        candidate = getattr(judgment, "candidate", None)
        if candidate is None:
            return 0
        dedupe_key = str(candidate.dedupe_key or "").strip()
        if dedupe_key:
            count = sum(1 for item in reviewed_findings if item.get("dedupe_key") == dedupe_key)
            if count > 1:
                return count
        route = str(candidate.route or "").strip()
        baseline_ref = str(candidate.baseline_ref or "").strip()
        if route or baseline_ref:
            count = 0
            for item in reviewed_findings:
                if route and item.get("route") != route:
                    continue
                if baseline_ref and item.get("baseline_ref") != baseline_ref:
                    continue
                count += 1
            if count:
                return count
        return 1

    def _collect_acceptance_browser_evidence(
        self,
        *,
        mission_id: str,
        round_id: int,
        round_dir: Path,
        campaign: AcceptanceCampaign,
    ) -> dict[str, Any] | None:
        try:
            return collect_playwright_browser_evidence(
                mission_id=mission_id,
                round_id=round_id,
                round_dir=round_dir,
                paths=self._acceptance_browser_routes(campaign),
                interaction_plans=campaign.interaction_plans,
            )
        except Exception:
            logger.exception(
                "Acceptance browser evidence collection failed for %s round %s",
                mission_id,
                round_id,
            )
            return None

    @staticmethod
    def _mark_acceptance_filing_failure(
        result: AcceptanceReviewResult,
        error: str,
    ) -> AcceptanceReviewResult:
        if result.issue_proposals:
            proposals = [
                replace(proposal, filing_status="failed", filing_error=error)
                for proposal in result.issue_proposals
            ]
            return replace(result, issue_proposals=proposals)
        return replace(
            result,
            artifacts={**result.artifacts, "filing_error": error},
        )

    def _build_acceptance_artifacts(
        self,
        *,
        mission_id: str,
        round_id: int,
        artifacts: RoundArtifacts,
        summary: RoundSummary,
    ) -> dict[str, Any]:
        mission = self._load_mission(mission_id)
        fresh_execution = self._build_fresh_execution_evidence(
            mission_id=mission_id,
            round_id=round_id,
            artifacts=artifacts,
        )
        workflow_replay = {
            "proof_type": "workflow_replay",
            "review_routes": {
                "overview": f"/?mission={mission_id}&mode=missions&tab=overview",
                "transcript": (
                    f"/?mission={mission_id}&mode=missions&tab=transcript&round={round_id}"
                ),
                "approvals": (
                    f"/?mission={mission_id}&mode=missions&tab=approvals&round={round_id}"
                ),
                "visual_qa": f"/?mission={mission_id}&mode=missions&tab=visual&round={round_id}",
                "costs": f"/?mission={mission_id}&mode=missions&tab=costs&round={round_id}",
                "acceptance": (
                    f"/?mission={mission_id}&mode=missions&tab=acceptance&round={round_id}"
                ),
            },
            "workflow_assertions": self._build_workflow_assertions(),
        }
        return {
            "mission": {
                "mission_id": mission_id,
                "title": mission.title if mission is not None else mission_id,
                "acceptance_criteria": list(mission.acceptance_criteria) if mission else [],
                "constraints": list(mission.constraints) if mission else [],
            },
            "round_summary": summary.to_dict(),
            "round_artifacts": {
                "round_id": artifacts.round_id,
                "mission_id": artifacts.mission_id,
                "builder_reports": artifacts.builder_reports,
                "verification_outputs": artifacts.verification_outputs,
                "gate_verdicts": artifacts.gate_verdicts,
                "manifest_paths": artifacts.manifest_paths,
                "diff_summary": artifacts.diff_summary,
                "worker_session_ids": artifacts.worker_session_ids,
                "visual_evaluation": (
                    artifacts.visual_evaluation.to_dict()
                    if artifacts.visual_evaluation is not None
                    else None
                ),
            },
            "fresh_execution": fresh_execution,
            "workflow_replay": workflow_replay,
            "proof_split": {
                "fresh_execution": fresh_execution,
                "workflow_replay": workflow_replay,
            },
            "review_routes": workflow_replay["review_routes"],
            "workflow_assertions": workflow_replay["workflow_assertions"],
        }

    def _build_fresh_execution_evidence(
        self,
        *,
        mission_id: str,
        round_id: int,
        artifacts: RoundArtifacts,
    ) -> dict[str, Any]:
        round_dir = self._round_dir(mission_id, round_id)
        mission_bootstrap = self._read_operator_json(mission_id, "mission_bootstrap.json")
        launch = self._read_operator_json(mission_id, "launch.json")
        normalized_launch = dict(launch)
        last_launch = normalized_launch.get("last_launch", {})
        if isinstance(last_launch, dict):
            state = last_launch.get("state")
            if isinstance(state, dict) and "state" not in normalized_launch:
                normalized_launch["state"] = dict(state)
        daemon_run = self._read_operator_json(mission_id, "daemon_run.json")
        builder_execution_summary = {
            "builder_reports": artifacts.builder_reports,
            "worker_session_ids": artifacts.worker_session_ids,
        }
        return {
            "proof_type": "fresh_execution",
            "mission_bootstrap": mission_bootstrap,
            "launch": normalized_launch,
            "daemon_run": daemon_run,
            "fresh_round_path": str(round_dir),
            "builder_execution_summary": builder_execution_summary,
        }

    def _read_operator_json(self, mission_id: str, filename: str) -> dict[str, Any]:
        path = self._mission_dir(mission_id) / "operator" / filename
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _build_acceptance_campaign(
        self,
        *,
        mission_id: str,
        artifacts: dict[str, Any],
        mode_override: AcceptanceMode | None = None,
    ) -> AcceptanceCampaign:
        routing_decision = self._build_acceptance_routing_decision(
            mission_id=mission_id,
            artifacts=artifacts,
            mode_override=mode_override,
        )
        mode = self._resolve_acceptance_mode(mode_override=mode_override)
        review_routes = artifacts.get("review_routes", {})
        if mode is AcceptanceMode.EXPLORATORY and not isinstance(review_routes, dict):
            review_routes = {}
        if mode is AcceptanceMode.EXPLORATORY and not review_routes:
            review_routes = self._default_dashboard_review_routes(mission_id)
        effective_artifacts = (
            {**artifacts, "review_routes": review_routes}
            if isinstance(review_routes, dict) and review_routes
            else artifacts
        )
        primary_routes = self._acceptance_primary_routes(
            mission_id=mission_id,
            artifacts=effective_artifacts,
            mode=mode,
        )
        mission = self._load_mission(mission_id)
        related_routes = self._acceptance_related_routes(
            primary_routes=primary_routes,
            review_routes=review_routes if isinstance(review_routes, dict) else {},
            mode=mode,
        )
        coverage_expectations = list(mission.acceptance_criteria) if mission is not None else []
        if mode is AcceptanceMode.EXPLORATORY:
            coverage_expectations = [
                "operator can establish launcher context",
                "operator can inspect mission detail from the overview surface",
                "operator can expand into adjacent mission surfaces",
                "operator can inspect at least one deeper evidence surface",
            ]
        workflow_assertions = [
            str(assertion)
            for assertion in artifacts.get("workflow_assertions", [])
            if str(assertion).strip()
        ]
        if mode is AcceptanceMode.WORKFLOW and not workflow_assertions:
            workflow_assertions = self._build_workflow_assertions()
        filing_policy = {
            AcceptanceMode.FEATURE_SCOPED: "in_scope_only",
            AcceptanceMode.IMPACT_SWEEP: "auto_file_regressions_only",
            AcceptanceMode.WORKFLOW: "auto_file_broken_flows_only",
            AcceptanceMode.EXPLORATORY: "hold_ux_concerns_for_operator_review",
        }[mode]
        exploration_budget = {
            AcceptanceMode.FEATURE_SCOPED: "tight",
            AcceptanceMode.IMPACT_SWEEP: "medium",
            AcceptanceMode.WORKFLOW: "bounded",
            AcceptanceMode.EXPLORATORY: "wide",
        }[mode]
        goal = {
            AcceptanceMode.FEATURE_SCOPED: (
                "Verify the declared feature and directly affected routes."
            ),
            AcceptanceMode.IMPACT_SWEEP: (
                "Sweep nearby routes for regressions caused by this round."
            ),
            AcceptanceMode.WORKFLOW: (
                "Verify the operator can complete launcher and mission-control steps end-to-end."
            ),
            AcceptanceMode.EXPLORATORY: "Dogfood the output from an operator perspective.",
        }[mode]
        min_primary_routes = {
            AcceptanceMode.FEATURE_SCOPED: max(1, len(primary_routes)),
            AcceptanceMode.IMPACT_SWEEP: max(1, len(primary_routes)),
            AcceptanceMode.WORKFLOW: max(1, len(primary_routes)),
            AcceptanceMode.EXPLORATORY: max(1, len(primary_routes)),
        }[mode]
        related_route_budget = {
            AcceptanceMode.FEATURE_SCOPED: 1,
            AcceptanceMode.IMPACT_SWEEP: 3,
            AcceptanceMode.WORKFLOW: 5,
            AcceptanceMode.EXPLORATORY: 4,
        }[mode]
        interaction_budget = {
            AcceptanceMode.FEATURE_SCOPED: "tight",
            AcceptanceMode.IMPACT_SWEEP: "moderate",
            AcceptanceMode.WORKFLOW: "moderate",
            AcceptanceMode.EXPLORATORY: "wide",
        }[mode]
        required_interactions = {
            AcceptanceMode.FEATURE_SCOPED: ["verify declared feature flow"],
            AcceptanceMode.IMPACT_SWEEP: [
                "verify declared feature flow",
                "sweep adjacent mission surfaces",
            ],
            AcceptanceMode.WORKFLOW: [
                "open launcher",
                "switch across operator modes",
                "select the mission",
                "open the core mission detail tabs",
                "confirm workflow surfaces stay reachable end-to-end",
            ],
            AcceptanceMode.EXPLORATORY: [
                "complete the intended operator task",
                "switch into adjacent surfaces when the task suggests it",
            ],
        }[mode]
        seed_routes = primary_routes if mode is AcceptanceMode.EXPLORATORY else []
        allowed_expansions = related_routes if mode is AcceptanceMode.EXPLORATORY else []
        critique_focus = (
            [
                "information architecture confusion",
                "ambiguous terminology",
                "discoverability gaps",
                "context switching friction",
            ]
            if mode is AcceptanceMode.EXPLORATORY
            else []
        )
        stop_conditions = (
            [
                "stop when the route budget is exhausted",
                "stop when no adjacent surface adds new operator evidence",
                "stop after confirming a materially broken flow",
            ]
            if mode is AcceptanceMode.EXPLORATORY
            else []
        )
        evidence_budget = "bounded" if mode is AcceptanceMode.EXPLORATORY else ""
        interaction_plans = self._build_acceptance_interaction_plans(
            mode=mode,
            primary_routes=primary_routes,
            related_routes=related_routes,
            mission_id=mission_id,
        )
        return AcceptanceCampaign(
            mode=mode,
            goal=goal,
            primary_routes=primary_routes,
            related_routes=related_routes,
            interaction_plans=interaction_plans,
            coverage_expectations=coverage_expectations + workflow_assertions,
            required_interactions=required_interactions,
            min_primary_routes=min_primary_routes,
            related_route_budget=related_route_budget,
            interaction_budget=interaction_budget,
            filing_policy=filing_policy,
            exploration_budget=exploration_budget,
            seed_routes=seed_routes,
            allowed_expansions=allowed_expansions,
            critique_focus=critique_focus,
            stop_conditions=stop_conditions,
            evidence_budget=evidence_budget or routing_decision.action_budget,
        )

    def _build_acceptance_routing_decision(
        self,
        *,
        mission_id: str,
        artifacts: dict[str, Any],
        mode_override: AcceptanceMode | None = None,
    ) -> AcceptanceRoutingDecision:
        mode = self._resolve_acceptance_mode(mode_override=mode_override)
        run_mode = run_mode_from_legacy_acceptance_mode(mode)
        review_routes = artifacts.get("review_routes", {})
        surface_pack = dashboard_surface_pack_v1(mission_id)
        surface_pack_ref = AcceptanceSurfacePackRef(
            pack_key=surface_pack.pack_key,
            subject_kind=surface_pack.subject_kind,
            subject_id=surface_pack.subject_id,
        )
        request = AcceptanceRequest(
            goal={
                AcceptanceRunMode.VERIFY: "Verify mission acceptance criteria.",
                AcceptanceRunMode.REPLAY: "Replay the mission workflow against collected evidence.",
                AcceptanceRunMode.EXPLORE: "Dogfood the mission from an operator perspective.",
                AcceptanceRunMode.RECON: "Map the mission acceptance surface conservatively.",
            }[run_mode],
            target=f"mission:{mission_id}",
            constraints=(
                ["compare overlay enabled"]
                if isinstance(review_routes, dict) and review_routes.get("compare") is True
                else []
            ),
        )
        decision = build_acceptance_routing_decision(
            request,
            contract_strength="strong" if mode is not AcceptanceMode.EXPLORATORY else "medium",
            surface_familiarity="known" if review_routes else "unknown",
            baseline_available=run_mode is AcceptanceRunMode.REPLAY,
            surface_pack_ref=surface_pack_ref,
        )
        return AcceptanceRoutingDecision(
            base_run_mode=decision.base_run_mode,
            compare_overlay=decision.compare_overlay,
            budget_profile=decision.budget_profile,
            graph_profile=decision.graph_profile,
            evidence_plan=list(decision.evidence_plan),
            risk_posture=decision.risk_posture,
            route_budget=decision.route_budget,
            action_budget=decision.action_budget,
            recon_fallback_reason=decision.recon_fallback_reason,
            surface_pack_ref=surface_pack_ref,
            routing_inputs=decision.routing_inputs,
        )

    @staticmethod
    def _resolve_acceptance_mode(mode_override: AcceptanceMode | None = None) -> AcceptanceMode:
        if mode_override is not None:
            return mode_override
        raw_mode = os.getenv("SPEC_ORCH_ACCEPTANCE_MODE", AcceptanceMode.FEATURE_SCOPED.value)
        try:
            return AcceptanceMode(raw_mode.strip().lower())
        except ValueError:
            logger.warning(
                "Invalid SPEC_ORCH_ACCEPTANCE_MODE=%r; falling back to feature_scoped",
                raw_mode,
            )
            return AcceptanceMode.FEATURE_SCOPED

    def _acceptance_primary_routes(
        self,
        *,
        mission_id: str,
        artifacts: dict[str, Any],
        mode: AcceptanceMode,
    ) -> list[str]:
        paths_env = os.getenv("SPEC_ORCH_VISUAL_EVAL_PATHS", "").strip()
        if paths_env:
            env_routes = [part.strip() for part in paths_env.split(",") if part.strip()]
            if env_routes:
                return self._unique_preserve_order(env_routes)
        review_routes = artifacts.get("review_routes", {})
        overview_route = ""
        if isinstance(review_routes, dict):
            raw_overview = review_routes.get("overview")
            if isinstance(raw_overview, str):
                overview_route = raw_overview.strip()
        if mode is AcceptanceMode.WORKFLOW:
            return [
                "/",
                f"/?mission={mission_id}&mode=missions&tab=overview",
            ]
        if mode is AcceptanceMode.EXPLORATORY:
            return self._unique_preserve_order(
                [
                    "/",
                    overview_route or f"/?mission={mission_id}&mode=missions&tab=overview",
                ]
            )
        return ["/"]

    def _acceptance_related_routes(
        self,
        *,
        primary_routes: list[str],
        review_routes: dict[str, Any],
        mode: AcceptanceMode,
    ) -> list[str]:
        budget = {
            AcceptanceMode.FEATURE_SCOPED: 1,
            AcceptanceMode.IMPACT_SWEEP: 3,
            AcceptanceMode.WORKFLOW: 5,
            AcceptanceMode.EXPLORATORY: 4,
        }[mode]
        candidates = [
            route
            for route in review_routes.values()
            if isinstance(route, str) and route and route not in primary_routes
        ]
        priority = self._acceptance_route_priority(mode)
        candidates = sorted(
            self._unique_preserve_order(candidates),
            key=lambda route: (priority.get(self._route_tab_key(route), 99), route),
        )
        return candidates[:budget]

    @staticmethod
    def _default_dashboard_review_routes(mission_id: str) -> dict[str, str]:
        base = f"/?mission={mission_id}&mode=missions&tab="
        return {
            "overview": f"{base}overview",
            "transcript": f"{base}transcript",
            "approvals": f"{base}approvals",
            "acceptance": f"{base}acceptance",
            "visual_qa": f"{base}visual",
            "costs": f"{base}costs",
        }

    @staticmethod
    def _acceptance_route_priority(mode: AcceptanceMode) -> dict[str, int]:
        if mode is AcceptanceMode.WORKFLOW:
            return {
                "transcript": 0,
                "approvals": 1,
                "acceptance": 2,
                "visual": 3,
                "costs": 4,
                "overview": 5,
            }
        if mode is AcceptanceMode.IMPACT_SWEEP:
            return {
                "transcript": 0,
                "visual": 1,
                "costs": 2,
                "approvals": 3,
                "acceptance": 4,
                "overview": 5,
            }
        if mode is AcceptanceMode.EXPLORATORY:
            return {
                "transcript": 0,
                "acceptance": 1,
                "costs": 2,
                "visual": 3,
                "approvals": 4,
                "overview": 5,
            }
        return {
            "transcript": 0,
            "visual": 1,
            "costs": 2,
            "approvals": 3,
            "acceptance": 4,
            "overview": 5,
        }

    def _build_acceptance_interaction_plans(
        self,
        *,
        mode: AcceptanceMode,
        primary_routes: list[str],
        related_routes: list[str],
        mission_id: str,
    ) -> dict[str, list[AcceptanceInteractionStep]]:
        plans: dict[str, list[AcceptanceInteractionStep]] = {}
        for route in self._unique_preserve_order([*primary_routes, *related_routes]):
            plan = self._interaction_plan_for_route(route, mode=mode, mission_id=mission_id)
            if plan:
                plans[route] = plan
        return plans

    def _interaction_plan_for_route(
        self,
        route: str,
        *,
        mode: AcceptanceMode,
        mission_id: str,
    ) -> list[AcceptanceInteractionStep]:
        if mode is AcceptanceMode.WORKFLOW:
            return self._workflow_interaction_plan_for_route(route, mission_id=mission_id)
        if mode is AcceptanceMode.EXPLORATORY:
            return self._exploratory_interaction_plan_for_route(route, mission_id=mission_id)
        if "mission=" not in route:
            return []
        restore_label = self._route_tab_label(route)
        labels_by_mode: dict[AcceptanceMode, list[str]] = {
            AcceptanceMode.FEATURE_SCOPED: ["Transcript"],
            AcceptanceMode.IMPACT_SWEEP: ["Transcript", "Visual QA"],
            AcceptanceMode.EXPLORATORY: ["Transcript", "Approvals", "Visual QA", "Costs"],
        }
        steps = [
            AcceptanceInteractionStep(
                action="click_text",
                target=label,
                description=f"Open the {label} surface from the mission workbench.",
            )
            for label in labels_by_mode[mode]
            if label != restore_label
        ]
        if restore_label and steps:
            steps.append(
                AcceptanceInteractionStep(
                    action="click_text",
                    target=restore_label,
                    description=f"Return to the {restore_label} surface after the sweep.",
                )
            )
        return steps

    def _exploratory_interaction_plan_for_route(
        self,
        route: str,
        *,
        mission_id: str,
    ) -> list[AcceptanceInteractionStep]:
        escaped_mission_id = self._css_attr_escape(mission_id)
        if route == "/":
            return [
                AcceptanceInteractionStep(
                    action="click_selector",
                    target='[data-automation-target="open-launcher"]',
                    description="Open the launcher to establish operator context.",
                ),
                AcceptanceInteractionStep(
                    action="wait_for_selector",
                    target='[data-automation-target="launcher-action"][data-launcher-action="refresh-readiness"]',
                    description=(
                        "Confirm launcher actions are visible before exploring mission surfaces."
                    ),
                ),
            ]
        if "tab=overview" in route:
            return [
                AcceptanceInteractionStep(
                    action="wait_for_selector",
                    target=(
                        '[data-automation-target="mission-detail-ready"]'
                        f'[data-mission-id="{escaped_mission_id}"]'
                    ),
                    description=(
                        "Confirm mission detail is ready before branching into adjacent surfaces."
                    ),
                ),
                AcceptanceInteractionStep(
                    action="click_selector",
                    target='[data-automation-target="mission-tab"][data-tab-key="transcript"]',
                    description="Probe the transcript surface from the overview entry point.",
                ),
                AcceptanceInteractionStep(
                    action="wait_for_selector",
                    target='[data-automation-target="mission-tab"][data-tab-key="transcript"][data-active="true"]',
                    description="Confirm the transcript branch became active.",
                ),
            ]
        if "tab=transcript" in route:
            return [
                AcceptanceInteractionStep(
                    action="click_selector",
                    target='[data-automation-target="transcript-filter"][data-filter-key="all"]',
                    description="Reset transcript filters before judging discoverability.",
                    timeout_ms=1500,
                ),
                AcceptanceInteractionStep(
                    action="wait_for_selector",
                    target='[data-automation-target="transcript-filter"][data-filter-key="all"][data-active="true"]',
                    description="Confirm transcript evidence is shown in the broadest view.",
                    timeout_ms=1500,
                ),
                AcceptanceInteractionStep(
                    action="click_selector",
                    target='[data-automation-target="packet-row"]',
                    description=(
                        "Open the first visible packet to inspect concrete operator evidence."
                    ),
                    timeout_ms=1500,
                ),
                AcceptanceInteractionStep(
                    action="wait_for_selector",
                    target='[data-automation-target="packet-row"][data-active="true"]',
                    description="Confirm a packet was selected before judging transcript clarity.",
                    timeout_ms=1500,
                ),
                AcceptanceInteractionStep(
                    action="click_selector",
                    target='[data-automation-target="transcript-block"]',
                    description=(
                        "Inspect the first visible transcript block for context continuity."
                    ),
                    timeout_ms=1500,
                ),
            ]
        if "tab=acceptance" in route:
            return [
                AcceptanceInteractionStep(
                    action="click_selector",
                    target=(
                        '[data-automation-target="internal-route"]'
                        '[data-route-label="Open acceptance review"]'
                    ),
                    description=(
                        "Follow the acceptance affordance exposed by the mission context rail."
                    ),
                    timeout_ms=1500,
                )
            ]
        if "tab=costs" in route:
            return [
                AcceptanceInteractionStep(
                    action="click_selector",
                    target=(
                        '[data-automation-target="internal-route"]'
                        '[data-route-label="Open cost review"]'
                    ),
                    description="Follow the costs affordance exposed by the mission context rail.",
                    timeout_ms=1500,
                )
            ]
        if "tab=visual" in route:
            return [
                AcceptanceInteractionStep(
                    action="click_selector",
                    target=(
                        '[data-automation-target="internal-route"]'
                        '[data-route-label="Open visual review"]'
                    ),
                    description=(
                        "Open the visual review affordance to inspect deeper visual evidence."
                    ),
                    timeout_ms=1500,
                )
            ]
        return []

    def _workflow_interaction_plan_for_route(
        self,
        route: str,
        *,
        mission_id: str,
    ) -> list[AcceptanceInteractionStep]:
        escaped_mission_id = self._css_attr_escape(mission_id)
        if route == "/":
            return [
                AcceptanceInteractionStep(
                    action="click_selector",
                    target='[data-automation-target="open-launcher"]',
                    description="Open the launcher from the dashboard header.",
                ),
                AcceptanceInteractionStep(
                    action="click_selector",
                    target='[data-automation-target="launcher-action"][data-launcher-action="refresh-readiness"]',
                    description=(
                        "Refresh launcher readiness to confirm the launcher actions remain usable."
                    ),
                ),
                AcceptanceInteractionStep(
                    action="wait_for_selector",
                    target='[data-automation-target="launcher-action"][data-launcher-action="refresh-readiness"].is-complete',
                    description="Confirm launcher readiness refresh completed successfully.",
                ),
                AcceptanceInteractionStep(
                    action="click_selector",
                    target='[data-automation-target="operator-mode"][data-mode-key="missions"]',
                    description="Switch mission control into the All Missions inventory.",
                ),
                AcceptanceInteractionStep(
                    action="wait_for_selector",
                    target='[data-automation-target="operator-mode"][data-mode-key="missions"][data-active="true"]',
                    description="Confirm the mission inventory mode became active.",
                ),
                AcceptanceInteractionStep(
                    action="click_selector",
                    target='[data-automation-target="operator-mode"][data-mode-key="approvals"]',
                    description="Open the decision queue mode from mission control.",
                ),
                AcceptanceInteractionStep(
                    action="wait_for_selector",
                    target='[data-automation-target="operator-mode"][data-mode-key="approvals"][data-active="true"]',
                    description="Confirm the decision queue mode became active.",
                ),
                AcceptanceInteractionStep(
                    action="click_selector",
                    target='[data-automation-target="operator-mode"][data-mode-key="evidence"]',
                    description="Open the deep evidence mode from mission control.",
                ),
                AcceptanceInteractionStep(
                    action="wait_for_selector",
                    target='[data-automation-target="operator-mode"][data-mode-key="evidence"][data-active="true"]',
                    description="Confirm the deep evidence mode became active.",
                ),
                AcceptanceInteractionStep(
                    action="click_selector",
                    target='[data-automation-target="operator-mode"][data-mode-key="inbox"]',
                    description="Return to the Needs Attention mode from mission control.",
                ),
                AcceptanceInteractionStep(
                    action="wait_for_selector",
                    target='[data-automation-target="operator-mode"][data-mode-key="inbox"][data-active="true"]',
                    description="Confirm the Needs Attention mode became active.",
                ),
                AcceptanceInteractionStep(
                    action="click_selector",
                    target='[data-automation-target="operator-mode"][data-mode-key="missions"]',
                    description=(
                        "Return to the mission inventory before selecting the target mission."
                    ),
                ),
                AcceptanceInteractionStep(
                    action="wait_for_selector",
                    target='[data-automation-target="operator-mode"][data-mode-key="missions"][data-active="true"]',
                    description="Confirm the mission inventory mode became active again.",
                ),
                AcceptanceInteractionStep(
                    action="click_selector",
                    target=(
                        '[data-automation-target="mission-card"]'
                        f'[data-mission-id="{escaped_mission_id}"]'
                    ),
                    description="Select the target mission from the mission list.",
                ),
                AcceptanceInteractionStep(
                    action="wait_for_selector",
                    target=(
                        '[data-automation-target="mission-detail-ready"]'
                        f'[data-mission-id="{escaped_mission_id}"]'
                    ),
                    description="Confirm the selected mission detail surface finished loading.",
                ),
            ]
        if "tab=overview" in route:
            return [
                AcceptanceInteractionStep(
                    action="click_selector",
                    target='[data-automation-target="mission-tab"][data-tab-key="transcript"]',
                    description="Open the transcript tab from mission detail.",
                ),
                AcceptanceInteractionStep(
                    action="wait_for_selector",
                    target='[data-automation-target="mission-tab"][data-tab-key="transcript"][data-active="true"]',
                    description="Confirm the transcript tab became active.",
                ),
                AcceptanceInteractionStep(
                    action="click_selector",
                    target='[data-automation-target="mission-tab"][data-tab-key="approvals"]',
                    description="Open the approvals tab from mission detail.",
                ),
                AcceptanceInteractionStep(
                    action="wait_for_selector",
                    target='[data-automation-target="mission-tab"][data-tab-key="approvals"][data-active="true"]',
                    description="Confirm the approvals tab became active.",
                ),
                AcceptanceInteractionStep(
                    action="click_selector",
                    target='[data-automation-target="mission-tab"][data-tab-key="visual-qa"]',
                    description="Open the Visual QA tab from mission detail.",
                ),
                AcceptanceInteractionStep(
                    action="wait_for_selector",
                    target='[data-automation-target="mission-tab"][data-tab-key="visual-qa"][data-active="true"]',
                    description="Confirm the Visual QA tab became active.",
                ),
                AcceptanceInteractionStep(
                    action="click_selector",
                    target='[data-automation-target="mission-tab"][data-tab-key="acceptance"]',
                    description="Open the Acceptance tab from mission detail.",
                ),
                AcceptanceInteractionStep(
                    action="wait_for_selector",
                    target='[data-automation-target="mission-tab"][data-tab-key="acceptance"][data-active="true"]',
                    description="Confirm the Acceptance tab became active.",
                ),
                AcceptanceInteractionStep(
                    action="click_selector",
                    target='[data-automation-target="mission-tab"][data-tab-key="costs"]',
                    description="Open the Costs tab from mission detail.",
                ),
                AcceptanceInteractionStep(
                    action="wait_for_selector",
                    target='[data-automation-target="mission-tab"][data-tab-key="costs"][data-active="true"]',
                    description="Confirm the Costs tab became active.",
                ),
                AcceptanceInteractionStep(
                    action="click_selector",
                    target='[data-automation-target="mission-tab"][data-tab-key="overview"]',
                    description="Return to the overview tab after the workflow sweep.",
                ),
                AcceptanceInteractionStep(
                    action="wait_for_selector",
                    target='[data-automation-target="mission-tab"][data-tab-key="overview"][data-active="true"]',
                    description="Confirm the overview tab became active again.",
                ),
            ]
        return []

    @staticmethod
    def _css_attr_escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    @staticmethod
    def _build_workflow_assertions() -> list[str]:
        return [
            "launcher panel can be opened from the header",
            "needs attention mode can be selected from mission control",
            "missions mode can be selected from mission control",
            "decision queue mode can be selected from mission control",
            "deep evidence mode can be selected from mission control",
            "the target mission can be selected from the mission list",
            "the transcript tab can be opened from mission detail",
            "the approvals surface exposes actionable operator controls when present",
            "the visual QA tab can be opened from mission detail",
            "the acceptance tab can be opened from mission detail",
            "the costs tab can be opened from mission detail",
        ]

    @staticmethod
    def _route_tab_label(route: str) -> str:
        tab = RoundOrchestrator._route_tab_key(route)
        return {
            "overview": "Overview",
            "transcript": "Transcript",
            "approvals": "Approvals",
            "visual": "Visual QA",
            "visual-qa": "Visual QA",
            "acceptance": "Acceptance",
            "costs": "Costs",
        }.get(tab, "Overview")

    @staticmethod
    def _route_tab_key(route: str) -> str:
        if "tab=" not in route:
            return "overview"
        return route.split("tab=", 1)[1].split("&", 1)[0]

    def _acceptance_browser_routes(self, campaign: AcceptanceCampaign) -> list[str]:
        return self._unique_preserve_order(
            [
                *campaign.primary_routes,
                *campaign.related_routes[: campaign.related_route_budget],
            ]
        )

    def _build_supervisor_issue(
        self,
        *,
        mission_id: str,
        round_id: int,
        wave: Wave,
    ) -> Issue:
        mission = self._load_mission(mission_id)
        mission_title = mission.title if mission is not None else f"Mission {mission_id}"
        acceptance_criteria = self._unique_preserve_order(
            [
                *(mission.acceptance_criteria if mission is not None else []),
                *[
                    criterion
                    for packet in wave.work_packets
                    for criterion in packet.acceptance_criteria
                ],
            ]
        )
        constraints = list(mission.constraints) if mission is not None else []
        files_to_read = self._unique_preserve_order(
            [path for packet in wave.work_packets for path in packet.files_in_scope]
        )
        architecture_notes = self._build_supervisor_notes(mission, wave)
        return Issue(
            issue_id=mission_id,
            title=mission_title,
            summary=f"Round {round_id} review for wave {wave.wave_number}",
            acceptance_criteria=acceptance_criteria,
            context=IssueContext(
                files_to_read=files_to_read,
                constraints=constraints,
                architecture_notes=architecture_notes,
            ),
            mission_id=mission_id,
        )

    def _write_supervisor_task_spec(
        self,
        *,
        round_dir: Path,
        mission_id: str,
        wave: Wave,
    ) -> None:
        mission = self._load_mission(mission_id)
        mission_spec = self._load_mission_spec(mission)
        wave_lines = [
            "",
            "## Active Wave",
            "",
            f"- Wave {wave.wave_number}: {wave.description}",
            "",
            "## Active Packets",
            "",
        ]
        for packet in wave.work_packets:
            wave_lines.append(f"- {packet.packet_id}: {packet.title}")
        task_spec = mission_spec or f"# {mission.title if mission else mission_id}\n"
        task_spec = task_spec.rstrip() + "\n" + "\n".join(wave_lines) + "\n"
        (round_dir / "task.spec.md").write_text(task_spec, encoding="utf-8")

    def _build_supervisor_context(
        self,
        *,
        mission_id: str,
        round_id: int,
        wave: Wave,
        issue: Issue,
        assembled_context: Any,
        artifacts: RoundArtifacts,
    ) -> dict[str, Any]:
        mission = self._load_mission(mission_id)
        return {
            "mission": {
                "mission_id": mission_id,
                "title": mission.title if mission is not None else issue.title,
                "constraints": list(issue.context.constraints),
                "acceptance_criteria": list(issue.acceptance_criteria),
            },
            "wave": {
                "round_id": round_id,
                "wave_number": wave.wave_number,
                "description": wave.description,
                "packet_ids": [packet.packet_id for packet in wave.work_packets],
                "packet_titles": [packet.title for packet in wave.work_packets],
            },
            "assembled_context": assembled_context,
            "visual_evaluation": (
                artifacts.visual_evaluation.to_dict()
                if artifacts.visual_evaluation is not None
                else None
            ),
        }

    def _load_mission(self, mission_id: str) -> Mission | None:
        from spec_orch.services.mission_service import MissionService

        try:
            return MissionService(self.repo_root).get_mission(mission_id)
        except Exception:
            return None

    def _load_mission_spec(self, mission: Mission | None) -> str:
        if mission is None or not mission.spec_path:
            return ""
        spec_path = self.repo_root / mission.spec_path
        if not spec_path.exists():
            return ""
        return spec_path.read_text(encoding="utf-8")

    @staticmethod
    def _build_supervisor_notes(mission: Mission | None, wave: Wave) -> str:
        notes = [f"Wave {wave.wave_number}: {wave.description}"]
        if mission is not None and mission.interface_contracts:
            notes.extend(["", "Interface Contracts:"])
            notes.extend([f"- {item}" for item in mission.interface_contracts])
        return "\n".join(notes)

    @staticmethod
    def _unique_preserve_order(items: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for item in items:
            if item and item not in seen:
                seen.add(item)
                ordered.append(item)
        return ordered
