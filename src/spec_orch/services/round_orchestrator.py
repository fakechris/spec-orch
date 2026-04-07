"""Mission execute-review-decide loop."""

from __future__ import annotations

import inspect
import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any, TypeVar
from uuid import uuid4

from spec_orch.acceptance_core.calibration import dashboard_surface_pack_v1
from spec_orch.acceptance_core.models import AcceptanceRunMode, run_mode_from_legacy_acceptance_mode
from spec_orch.acceptance_core.routing import (
    AcceptanceRequest,
    AcceptanceRoutingDecision,
    AcceptanceSurfacePackRef,
    build_acceptance_routing_decision,
)
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
    Issue,
    IssueContext,
    Mission,
    PlanPatch,
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
from spec_orch.runtime_core.writers import write_round_supervision_payloads
from spec_orch.services.acceptance_pipeline import AcceptancePipeline
from spec_orch.services.artifact_collector import ArtifactCollector
from spec_orch.services.event_bus import Event, EventBus, EventTopic
from spec_orch.services.io import atomic_write_json
from spec_orch.services.plan_patch_applier import PlanPatchApplier
from spec_orch.services.resource_loader import load_json_resource
from spec_orch.services.round_chain_recorder import RoundChainRecorder
from spec_orch.services.round_review_coordinator import RoundReviewCoordinator
from spec_orch.services.run_event_logger import RunEventLogger
from spec_orch.services.telemetry_service import TelemetryService
from spec_orch.services.wave_dispatcher import WaveDispatcher

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
        gate_policy: Any | None = None,
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
        self._acceptance_pipeline = AcceptancePipeline(
            repo_root=self.repo_root,
            acceptance_evaluator=acceptance_evaluator,
            acceptance_filer=acceptance_filer,
        )
        self._event_logger = RunEventLogger(
            telemetry_service=TelemetryService(),
            live_stream=live_stream,
        )
        self._wave_dispatcher = WaveDispatcher(
            worker_factory=worker_factory,
            event_logger=self._event_logger,
        )
        self._artifact_collector = ArtifactCollector(
            repo_root=self.repo_root, gate_policy=gate_policy
        )
        self._round_review_coordinator = RoundReviewCoordinator()
        self._plan_patch_applier = PlanPatchApplier()

    def run_supervised(
        self,
        *,
        mission_id: str,
        plan: ExecutionPlan,
        initial_round: int = 0,
    ) -> RoundOrchestratorResult:
        # -- load history and replay patches --
        round_history = self._load_history(mission_id, up_to_round=initial_round)
        plan = self._plan_patch_applier.replay_patches(plan, round_history)
        current_wave_idx = PlanPatchApplier.determine_start_wave(plan, round_history)
        round_id = initial_round

        # -- initialise chain recorder --
        chain_root = self._mission_operator_dir(mission_id) / "runtime_chain"
        chain_id = self._new_chain_id(mission_id)
        mission_span_id = f"{chain_id}:mission"
        chain = RoundChainRecorder(
            chain_root=chain_root,
            chain_id=chain_id,
            mission_span_id=mission_span_id,
        )
        chain.record_mission_started(
            mission_id=mission_id,
            mission_root=str(self._mission_dir(mission_id)),
        )

        # -- main round loop --
        while round_id < self.max_rounds and current_wave_idx < len(plan.waves):
            round_id += 1
            wave = plan.waves[current_wave_idx]
            round_dir = self._round_dir(mission_id, round_id)
            round_dir.mkdir(parents=True, exist_ok=True)
            round_span_id = chain.round_span_id(round_id)
            chain.record_round_started(round_id=round_id, round_dir=round_dir)

            summary = RoundSummary(
                round_id=round_id,
                wave_id=current_wave_idx,
                status=RoundStatus.EXECUTING,
            )

            # dispatch
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
                chain.record_round_failed(round_id=round_id, round_dir=round_dir)
                round_history.append(summary)
                return RoundOrchestratorResult(completed=False, rounds=round_history)

            summary.worker_results = [
                self._serialize_result(packet, result) for packet, result in worker_results
            ]
            summary.status = RoundStatus.COLLECTING

            # collect
            artifacts = self._collect_artifacts(
                mission_id=mission_id,
                round_id=round_id,
                wave=wave,
                worker_results=worker_results,
                round_dir=round_dir,
            )

            # review
            decision = self._review_round(
                mission_id=mission_id,
                round_id=round_id,
                round_dir=round_dir,
                wave=wave,
                artifacts=artifacts,
                plan=plan,
                round_history=round_history,
                summary=summary,
                chain_root=chain_root,
                chain_id=chain_id,
                round_span_id=round_span_id,
            )
            round_history.append(summary)

            # accept
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

            # record chain + persist
            chain.record_round_completed(round_id=round_id, round_dir=round_dir)
            self._apply_session_ops(mission_id, decision)

            # advance
            if decision.action is RoundAction.CONTINUE:
                current_wave_idx += 1
                if current_wave_idx >= len(plan.waves):
                    return RoundOrchestratorResult(completed=True, rounds=round_history)
                continue
            if decision.action is RoundAction.RETRY:
                if decision.plan_patch is not None:
                    plan = self._plan_patch_applier.apply(
                        plan,
                        current_wave_idx=current_wave_idx,
                        patch=decision.plan_patch,
                    )
                continue
            if decision.action is RoundAction.REPLAN_REMAINING:
                if decision.plan_patch is not None:
                    plan = self._plan_patch_applier.apply(
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
        return self._wave_dispatcher.run(
            host=self,
            mission_id=mission_id,
            round_id=round_id,
            wave=wave,
            round_history=round_history,
            chain_id=chain_id,
            chain_root=chain_root,
            round_span_id=round_span_id,
        )

    def _collect_artifacts(
        self,
        *,
        mission_id: str,
        round_id: int,
        wave: Wave,
        worker_results: list[tuple[WorkPacket, BuilderResult]],
        round_dir: Path,
    ) -> RoundArtifacts:
        return self._artifact_collector.collect(
            host=self,
            mission_id=mission_id,
            round_id=round_id,
            wave=wave,
            worker_results=worker_results,
            round_dir=round_dir,
        )

    def _build_packet_scope_proof(
        self,
        *,
        workspace: Path,
        packet: WorkPacket,
        report_path: Path,
    ) -> dict[str, Any]:
        return self._artifact_collector.build_packet_scope_proof(
            workspace=workspace,
            packet=packet,
            report_path=report_path,
        )

    def _load_realized_files_from_report(
        self,
        *,
        workspace: Path,
        packet: WorkPacket,
        report_path: Path,
    ) -> list[str] | None:
        return self._artifact_collector.load_realized_files_from_report(
            workspace=workspace,
            packet=packet,
            report_path=report_path,
        )

    def _is_transient_verification_support_file(
        self, packet: WorkPacket, relative_path: str
    ) -> bool:
        return self._artifact_collector.is_transient_verification_support_file(
            packet, relative_path
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
        return self._plan_patch_applier.replay_patches(plan, round_history)

    @staticmethod
    def _determine_start_wave(plan: ExecutionPlan, round_history: list[RoundSummary]) -> int:
        return PlanPatchApplier.determine_start_wave(plan, round_history)

    def _apply_plan_patch(
        self,
        plan: ExecutionPlan,
        *,
        current_wave_idx: int,
        patch: PlanPatch,
    ) -> ExecutionPlan:
        return self._plan_patch_applier.apply(plan, current_wave_idx=current_wave_idx, patch=patch)

    @staticmethod
    def _packet_from_patch(packet_data: dict[str, Any]) -> WorkPacket:
        return PlanPatchApplier.packet_from_patch(packet_data)

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

    def _review_round(
        self,
        *,
        mission_id: str,
        round_id: int,
        round_dir: Path,
        wave: Wave,
        artifacts: RoundArtifacts,
        plan: ExecutionPlan,
        round_history: list[RoundSummary],
        summary: RoundSummary,
        chain_root: Path,
        chain_id: str,
        round_span_id: str,
    ) -> RoundDecision:
        return self._round_review_coordinator.review(
            host=self,
            mission_id=mission_id,
            round_id=round_id,
            round_dir=round_dir,
            wave=wave,
            artifacts=artifacts,
            plan=plan,
            round_history=round_history,
            summary=summary,
            chain_root=chain_root,
            chain_id=chain_id,
            round_span_id=round_span_id,
        )

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
        return self._acceptance_pipeline.run(
            host=self,
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
        return self._acceptance_pipeline.run_graph_trace(
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

    def _record_fixture_candidate_graduations(
        self,
        *,
        mission_id: str,
        source_record_id: str,
        judgments: list[Any],
        review: AcceptanceReviewResult,
        memory: Any,
    ) -> None:
        self._acceptance_pipeline.record_fixture_candidate_graduations(
            mission_id=mission_id,
            source_record_id=source_record_id,
            judgments=judgments,
            review=review,
            memory=memory,
        )

    @staticmethod
    def _fixture_candidate_repeat_count(
        *,
        judgment: Any,
        reviewed_findings: list[dict[str, Any]],
    ) -> int:
        return AcceptancePipeline.fixture_candidate_repeat_count(
            judgment=judgment,
            reviewed_findings=reviewed_findings,
        )

    def _collect_acceptance_browser_evidence(
        self,
        *,
        mission_id: str,
        round_id: int,
        round_dir: Path,
        campaign: AcceptanceCampaign,
    ) -> dict[str, Any] | None:
        return self._acceptance_pipeline.collect_browser_evidence(
            host=self,
            mission_id=mission_id,
            round_id=round_id,
            round_dir=round_dir,
            campaign=campaign,
        )

    @staticmethod
    def _mark_acceptance_filing_failure(
        result: AcceptanceReviewResult,
        error: str,
    ) -> AcceptanceReviewResult:
        return AcceptancePipeline.mark_filing_failure(result, error)

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
                "judgment": (f"/?mission={mission_id}&mode=missions&tab=judgment&round={round_id}"),
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
            "judgment": f"{base}judgment",
            "visual_qa": f"{base}visual",
            "costs": f"{base}costs",
        }

    @staticmethod
    def _acceptance_route_priority(mode: AcceptanceMode) -> dict[str, int]:
        if mode is AcceptanceMode.WORKFLOW:
            return {
                "transcript": 0,
                "approvals": 1,
                "judgment": 2,
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
                "judgment": 1,
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
            "judgment": 4,
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
                    action="wait_for_selector",
                    target=(
                        '[data-automation-target="mission-detail-ready"]'
                        f'[data-mission-id="{escaped_mission_id}"]'
                    ),
                    description=(
                        "Confirm mission detail is ready before judging transcript discoverability."
                    ),
                    timeout_ms=4000,
                ),
                AcceptanceInteractionStep(
                    action="wait_for_selector",
                    target='[data-automation-target="transcript-filter"][data-filter-key="all"]',
                    description="Confirm transcript controls are visible on the route.",
                    timeout_ms=4000,
                ),
                AcceptanceInteractionStep(
                    action="click_selector",
                    target='[data-automation-target="transcript-filter"][data-filter-key="all"]',
                    description="Reset transcript filters before judging discoverability.",
                    timeout_ms=4000,
                ),
                AcceptanceInteractionStep(
                    action="wait_for_selector",
                    target='[data-automation-target="transcript-filter"][data-filter-key="all"][data-active="true"]',
                    description=("Confirm transcript evidence is shown in the broadest view."),
                    timeout_ms=4000,
                ),
                AcceptanceInteractionStep(
                    action="wait_for_selector",
                    target='[data-automation-target="transcript-block"]',
                    description=(
                        "Wait for the transcript timeline to expose at least one evidence block."
                    ),
                    timeout_ms=4000,
                ),
                AcceptanceInteractionStep(
                    action="click_selector",
                    target='[data-automation-target="transcript-block"][data-active="true"]',
                    description=(
                        "Inspect the currently active transcript block for context continuity."
                    ),
                    timeout_ms=4000,
                ),
                AcceptanceInteractionStep(
                    action="wait_for_selector",
                    target='[data-automation-target="transcript-inspector"]',
                    description=(
                        "Confirm transcript evidence details are visible after selecting a block."
                    ),
                    timeout_ms=4000,
                ),
            ]
        if "tab=judgment" in route:
            return [
                AcceptanceInteractionStep(
                    action="click_selector",
                    target=(
                        '[data-automation-target="internal-route"]'
                        '[data-route-label="Open raw acceptance artifact"]'
                    ),
                    description=(
                        "Follow the raw acceptance artifact bridge exposed by Judgment Workbench."
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
                    target='[data-automation-target="mission-tab"][data-tab-key="judgment"]',
                    description="Open the Judgment tab from mission detail.",
                ),
                AcceptanceInteractionStep(
                    action="wait_for_selector",
                    target='[data-automation-target="mission-tab"][data-tab-key="judgment"][data-active="true"]',
                    description="Confirm the Judgment tab became active.",
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
            "the judgment tab can be opened from mission detail",
            "the costs tab can be opened from mission detail",
        ]

    @staticmethod
    def _route_tab_label(route: str) -> str:
        tab = RoundOrchestrator._route_tab_key(route)
        return {
            "overview": "Overview",
            "transcript": "Transcript",
            "approvals": "Approvals",
            "judgment": "Judgment",
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
