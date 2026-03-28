"""Mission execute-review-decide loop."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any

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
from spec_orch.services.acceptance.browser_evidence import collect_playwright_browser_evidence
from spec_orch.services.event_bus import Event, EventBus, EventTopic
from spec_orch.services.io import atomic_write_json
from spec_orch.services.node_context_registry import get_node_context_spec
from spec_orch.services.run_event_logger import RunEventLogger
from spec_orch.services.telemetry_service import TelemetryService

logger = logging.getLogger(__name__)


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
                    round_id=round_id,
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
            self._run_acceptance_evaluation(
                mission_id=mission_id,
                round_id=round_id,
                round_dir=round_dir,
                worker_results=worker_results,
                artifacts=artifacts,
                summary=summary,
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
            visual_evaluation=visual_evaluation,
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
        browser_evidence = self._collect_acceptance_browser_evidence(
            mission_id=mission_id,
            round_id=round_id,
            round_dir=round_dir,
            campaign=campaign,
        )
        if browser_evidence is not None:
            acceptance_artifacts["browser_evidence"] = browser_evidence
        try:
            result = self.acceptance_evaluator.evaluate_acceptance(
                mission_id=mission_id,
                round_id=round_id,
                round_dir=round_dir,
                worker_results=worker_results,
                artifacts=acceptance_artifacts,
                repo_root=self.repo_root,
                campaign=campaign,
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
        return result

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
            "review_routes": {
                "transcript": (
                    f"/?mission={mission_id}&mode=missions&tab=transcript&round={round_id}"
                ),
                "visual_qa": f"/?mission={mission_id}&mode=missions&tab=visual&round={round_id}",
                "costs": f"/?mission={mission_id}&mode=missions&tab=costs&round={round_id}",
                "acceptance": (
                    f"/?mission={mission_id}&mode=missions&tab=acceptance&round={round_id}"
                ),
            },
        }

    def _build_acceptance_campaign(
        self,
        *,
        mission_id: str,
        artifacts: dict[str, Any],
    ) -> AcceptanceCampaign:
        mode = self._resolve_acceptance_mode()
        review_routes = artifacts.get("review_routes", {})
        primary_routes = self._acceptance_primary_routes(artifacts)
        mission = self._load_mission(mission_id)
        related_routes = self._acceptance_related_routes(
            primary_routes=primary_routes,
            review_routes=review_routes if isinstance(review_routes, dict) else {},
            mode=mode,
        )
        coverage_expectations = list(mission.acceptance_criteria) if mission is not None else []
        filing_policy = {
            AcceptanceMode.FEATURE_SCOPED: "in_scope_only",
            AcceptanceMode.IMPACT_SWEEP: "auto_file_regressions_only",
            AcceptanceMode.EXPLORATORY: "hold_ux_concerns_for_operator_review",
        }[mode]
        exploration_budget = {
            AcceptanceMode.FEATURE_SCOPED: "tight",
            AcceptanceMode.IMPACT_SWEEP: "medium",
            AcceptanceMode.EXPLORATORY: "wide",
        }[mode]
        goal = {
            AcceptanceMode.FEATURE_SCOPED: (
                "Verify the declared feature and directly affected routes."
            ),
            AcceptanceMode.IMPACT_SWEEP: (
                "Sweep nearby routes for regressions caused by this round."
            ),
            AcceptanceMode.EXPLORATORY: "Dogfood the output from an operator perspective.",
        }[mode]
        min_primary_routes = {
            AcceptanceMode.FEATURE_SCOPED: max(1, len(primary_routes)),
            AcceptanceMode.IMPACT_SWEEP: max(1, len(primary_routes)),
            AcceptanceMode.EXPLORATORY: 1,
        }[mode]
        related_route_budget = {
            AcceptanceMode.FEATURE_SCOPED: 1,
            AcceptanceMode.IMPACT_SWEEP: 3,
            AcceptanceMode.EXPLORATORY: 5,
        }[mode]
        interaction_budget = {
            AcceptanceMode.FEATURE_SCOPED: "tight",
            AcceptanceMode.IMPACT_SWEEP: "moderate",
            AcceptanceMode.EXPLORATORY: "wide",
        }[mode]
        required_interactions = {
            AcceptanceMode.FEATURE_SCOPED: ["verify declared feature flow"],
            AcceptanceMode.IMPACT_SWEEP: [
                "verify declared feature flow",
                "sweep adjacent mission surfaces",
            ],
            AcceptanceMode.EXPLORATORY: [
                "complete the intended operator task",
                "switch into adjacent surfaces when the task suggests it",
            ],
        }[mode]
        interaction_plans = self._build_acceptance_interaction_plans(
            mode=mode,
            primary_routes=primary_routes,
            related_routes=related_routes,
        )
        return AcceptanceCampaign(
            mode=mode,
            goal=goal,
            primary_routes=primary_routes,
            related_routes=related_routes,
            interaction_plans=interaction_plans,
            coverage_expectations=coverage_expectations,
            required_interactions=required_interactions,
            min_primary_routes=min_primary_routes,
            related_route_budget=related_route_budget,
            interaction_budget=interaction_budget,
            filing_policy=filing_policy,
            exploration_budget=exploration_budget,
        )

    @staticmethod
    def _resolve_acceptance_mode() -> AcceptanceMode:
        raw_mode = os.getenv("SPEC_ORCH_ACCEPTANCE_MODE", AcceptanceMode.FEATURE_SCOPED.value)
        try:
            return AcceptanceMode(raw_mode.strip().lower())
        except ValueError:
            logger.warning(
                "Invalid SPEC_ORCH_ACCEPTANCE_MODE=%r; falling back to feature_scoped",
                raw_mode,
            )
            return AcceptanceMode.FEATURE_SCOPED

    def _acceptance_primary_routes(self, artifacts: dict[str, Any]) -> list[str]:
        paths_env = os.getenv("SPEC_ORCH_VISUAL_EVAL_PATHS", "").strip()
        if paths_env:
            env_routes = [part.strip() for part in paths_env.split(",") if part.strip()]
            if env_routes:
                return self._unique_preserve_order(env_routes)
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
            AcceptanceMode.EXPLORATORY: 5,
        }[mode]
        candidates = [
            route
            for route in review_routes.values()
            if isinstance(route, str) and route and route not in primary_routes
        ]
        return self._unique_preserve_order(candidates)[:budget]

    def _build_acceptance_interaction_plans(
        self,
        *,
        mode: AcceptanceMode,
        primary_routes: list[str],
        related_routes: list[str],
    ) -> dict[str, list[AcceptanceInteractionStep]]:
        plans: dict[str, list[AcceptanceInteractionStep]] = {}
        for route in self._unique_preserve_order([*primary_routes, *related_routes]):
            plan = self._interaction_plan_for_route(route, mode=mode)
            if plan:
                plans[route] = plan
        return plans

    def _interaction_plan_for_route(
        self,
        route: str,
        *,
        mode: AcceptanceMode,
    ) -> list[AcceptanceInteractionStep]:
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

    @staticmethod
    def _route_tab_label(route: str) -> str:
        tab = ""
        if "tab=" in route:
            tab = route.split("tab=", 1)[1].split("&", 1)[0]
        return {
            "overview": "Overview",
            "transcript": "Transcript",
            "approvals": "Approvals",
            "visual": "Visual QA",
            "visual-qa": "Visual QA",
            "acceptance": "Acceptance",
            "costs": "Costs",
        }.get(tab, "Overview")

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
