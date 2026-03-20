from __future__ import annotations

import inspect
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any

from spec_orch.domain.compliance import (
    default_turn_contract_compliance,
    evaluate_pre_action_narration_compliance,
)
from spec_orch.domain.models import (
    BuilderResult,
    FlowTransitionEvent,
    FlowType,
    GateInput,
    GateVerdict,
    Issue,
    ReviewSummary,
    RunResult,
    RunState,
    VerificationSummary,
)
from spec_orch.domain.protocols import BuilderAdapter, IssueSource, PlannerAdapter, ReviewAdapter
from spec_orch.flow_engine.engine import FlowEngine
from spec_orch.flow_engine.flow_router import FlowRouter
from spec_orch.flow_engine.mapper import FlowMapper
from spec_orch.services.activity_logger import ActivityLogger
from spec_orch.services.artifact_service import ArtifactService
from spec_orch.services.codex_exec_builder_adapter import CodexExecBuilderAdapter
from spec_orch.services.context_assembler import ContextAssembler
from spec_orch.services.deviation_service import (
    detect_deviations,
    overwrite_deviations,
)
from spec_orch.services.fixture_issue_source import FixtureIssueSource
from spec_orch.services.gate_service import GateService
from spec_orch.services.node_context_registry import get_node_context_spec
from spec_orch.services.review_adapter import LocalReviewAdapter
from spec_orch.services.run_artifact_service import RunArtifactService
from spec_orch.services.run_event_logger import RunEventLogger
from spec_orch.services.run_progress import RunProgressSnapshot
from spec_orch.services.run_report_writer import RunReportWriter
from spec_orch.services.spec_snapshot_service import (
    create_initial_snapshot,
    read_spec_snapshot,
    write_spec_snapshot,
)
from spec_orch.services.telemetry_service import TelemetryService
from spec_orch.services.verification_service import VerificationService
from spec_orch.services.workspace_service import WorkspaceService

logger = logging.getLogger(__name__)

_MAX_ADVANCE_ITERATIONS = 10
_FLOW_ORDER: dict[FlowType, int] = {FlowType.HOTFIX: 0, FlowType.STANDARD: 1, FlowType.FULL: 2}


def record_flow_transition(event: FlowTransitionEvent) -> None:
    """Record a flow transition event to MemoryService and log."""
    import logging

    logging.getLogger(__name__).info(
        "Flow transition: %s → %s (trigger=%s, issue=%s)",
        event.from_flow,
        event.to_flow,
        event.trigger,
        event.issue_id,
    )

    try:
        from spec_orch.services.memory.service import get_memory_service
        from spec_orch.services.memory.types import MemoryEntry, MemoryLayer

        tag = "flow-promotion" if "promotion" in event.trigger else "flow-demotion"
        svc = get_memory_service()
        svc.store(
            MemoryEntry(
                key=f"flow-transition-{event.issue_id}-{event.timestamp}",
                content=(
                    f"Flow transition: {event.from_flow} → {event.to_flow} "
                    f"(trigger={event.trigger})"
                ),
                layer=MemoryLayer.EPISODIC,
                tags=[
                    tag,
                    f"issue:{event.issue_id}",
                    f"from:{event.from_flow}",
                    f"to:{event.to_flow}",
                ],
                metadata={
                    "from_flow": event.from_flow,
                    "to_flow": event.to_flow,
                    "trigger": event.trigger,
                    "issue_id": event.issue_id,
                    "run_id": event.run_id,
                    "timestamp": event.timestamp,
                },
            )
        )
    except Exception:
        logging.getLogger(__name__).debug(
            "Failed to write flow transition to memory", exc_info=True
        )


class RunController:
    def __init__(
        self,
        *,
        repo_root: Path,
        codex_executable: str = "codex",
        pi_executable: str = "pi",
        builder_adapter: BuilderAdapter | None = None,
        issue_source: IssueSource | None = None,
        planner_adapter: PlannerAdapter | None = None,
        review_adapter: ReviewAdapter | None = None,
        live_stream: IO[str] | None = None,
        flow_engine: FlowEngine | None = None,
        flow_mapper: FlowMapper | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.artifact_service = ArtifactService()
        self.builder_adapter: BuilderAdapter = builder_adapter or CodexExecBuilderAdapter(
            executable=codex_executable
        )
        self.planner_adapter: PlannerAdapter | None = planner_adapter
        self.gate_service = GateService()
        self.review_adapter: ReviewAdapter = review_adapter or LocalReviewAdapter()
        self.run_artifact_service = RunArtifactService()
        self.telemetry_service = TelemetryService()
        self.verification_service = VerificationService()
        self.workspace_service = WorkspaceService(repo_root=self.repo_root)
        self.issue_source: IssueSource = issue_source or FixtureIssueSource(
            repo_root=self.repo_root
        )
        self._live_stream = live_stream
        self.flow_engine = flow_engine or FlowEngine()
        self.flow_mapper = flow_mapper or FlowMapper()
        self.context_assembler = ContextAssembler()
        self._flow_router: FlowRouter | None = None
        self._memory_service: Any | None = None
        self._event_logger = RunEventLogger(
            telemetry_service=self.telemetry_service,
            live_stream=live_stream,
        )
        self._report_writer = RunReportWriter()

    def _get_memory(self) -> Any | None:
        """Lazily obtain the MemoryService singleton."""
        if self._memory_service is not None:
            return self._memory_service
        try:
            from spec_orch.services.memory.service import get_memory_service

            self._memory_service = get_memory_service(repo_root=self.repo_root)
        except Exception:
            from spec_orch.services.event_bus import emit_fallback_safe

            emit_fallback_safe(
                "MemoryService",
                "memory_service",
                "no_memory",
                "MemoryService initialization failed",
            )
        return self._memory_service

    def _resolve_flow(self, issue: Issue) -> FlowType:
        """Determine the FlowType for an issue.

        Uses FlowRouter (hybrid rule+LLM) when available, otherwise
        falls back to static FlowMapper.
        """
        if self._flow_router is not None:
            decision = self._flow_router.route(issue)
            logger.info(
                "FlowRouter decision: %s (confidence=%.2f, source=%s) — %s",
                decision.recommended_flow,
                decision.confidence,
                decision.source,
                decision.reasoning,
            )
            if decision.source == "fallback":
                self._emit_fallback(
                    "FlowRouter",
                    "llm_routing",
                    "static_rules",
                    decision.reasoning,
                    issue.issue_id,
                )
            return decision.recommended_flow

        logger.info(
            "FlowRouter not configured; using static FlowMapper for %s",
            issue.issue_id,
        )
        self._emit_fallback(
            "FlowRouter",
            "hybrid_router",
            "static_mapper",
            "FlowRouter not configured",
            issue.issue_id,
        )
        resolved = self.flow_mapper.resolve_flow_type(
            issue.run_class,
            labels=issue.labels,
        )
        return resolved or FlowType.STANDARD

    @staticmethod
    def _emit_fallback(
        component: str,
        primary: str,
        fallback: str,
        reason: str,
        issue_id: str = "",
    ) -> None:
        RunEventLogger.emit_fallback(
            component=component,
            primary=primary,
            fallback=fallback,
            reason=reason,
            issue_id=issue_id,
        )

    @staticmethod
    def _supports_context_kwarg(method: Any) -> bool:
        try:
            return "context" in inspect.signature(method).parameters
        except (TypeError, ValueError):
            return False

    def run_issue(self, issue_id: str, flow_type: FlowType | None = None) -> RunResult:
        issue = self.issue_source.load(issue_id)
        resolved_flow = flow_type or self._resolve_flow(issue)
        workspace = self.workspace_service.prepare_issue_workspace(issue.issue_id)
        run_id = self.telemetry_service.new_run_id(issue.issue_id)

        run_snap = RunProgressSnapshot.create(run_id=run_id, issue_id=issue.issue_id)

        with self._event_logger.open_activity_logger(workspace) as activity_logger:
            self._event_logger.log_and_emit(
                activity_logger=activity_logger,
                workspace=workspace,
                run_id=run_id,
                issue_id=issue.issue_id,
                component="run_controller",
                event_type="run_started",
                message="Started issue run.",
            )

            task_spec, progress = self.artifact_service.write_initial_artifacts(
                workspace=workspace,
                issue_id=issue.issue_id,
                issue_title=issue.title,
            )

            existing_snapshot = read_spec_snapshot(workspace)
            if existing_snapshot is not None and existing_snapshot.approved:
                self._event_logger.log_and_emit(
                    activity_logger=activity_logger,
                    workspace=workspace,
                    run_id=run_id,
                    issue_id=issue.issue_id,
                    component="spec",
                    event_type="spec_snapshot_preserved",
                    message=f"Preserved existing spec snapshot v{existing_snapshot.version}.",
                    data={"version": existing_snapshot.version, "approved": True},
                )
            else:
                snapshot = create_initial_snapshot(issue, approved=True)
                write_spec_snapshot(workspace, snapshot)
                self._event_logger.log_and_emit(
                    activity_logger=activity_logger,
                    workspace=workspace,
                    run_id=run_id,
                    issue_id=issue.issue_id,
                    component="spec",
                    event_type="spec_snapshot_created",
                    message="Created and auto-approved spec snapshot v1.",
                    data={"version": 1, "approved": True},
                )

            run_snap.mark_stage_start("builder")
            builder = self._run_builder(
                issue=issue,
                workspace=workspace,
                run_id=run_id,
                activity_logger=activity_logger,
            )
            run_snap.mark_stage_complete("builder", success=builder.succeeded)
            run_snap.save(workspace)

            run_snap.mark_stage_start("verification")
            self._event_logger.log_and_emit(
                activity_logger=activity_logger,
                workspace=workspace,
                run_id=run_id,
                issue_id=issue.issue_id,
                component="verification",
                event_type="verification_started",
                message="Started verification steps.",
            )
            verification = self.verification_service.run(issue=issue, workspace=workspace)
            v_passed = sum(1 for v in verification.step_results.values() if v)
            v_total = len(verification.step_results)
            run_snap.mark_stage_complete(
                "verification",
                success=all(verification.step_results.values())
                if verification.step_results
                else True,
                detail=f"{v_passed}/{v_total} checks passed",
            )
            run_snap.save(workspace)

            self._event_logger.log_verification_events(
                workspace=workspace,
                issue_id=issue.issue_id,
                run_id=run_id,
                verification=verification,
                activity_logger=activity_logger,
            )

            run_snap.mark_stage_start("review")
            review = self.review_adapter.initialize(
                issue_id=issue.issue_id,
                workspace=workspace,
                builder_turn_contract_compliance=builder.metadata.get("turn_contract_compliance"),
            )
            run_snap.mark_stage_complete("review", success=review.verdict != "rejected")
            run_snap.save(workspace)

            self._event_logger.log_and_emit(
                activity_logger=activity_logger,
                workspace=workspace,
                run_id=run_id,
                issue_id=issue.issue_id,
                component="review",
                event_type="review_initialized",
                message="Initialized local review state.",
                data={"verdict": review.verdict},
            )

            run_snap.mark_stage_start("gate")
            gate, explain, report = self._finalize_run(
                issue=issue,
                workspace=workspace,
                run_id=run_id,
                builder=builder,
                verification=verification,
                review=review,
                human_acceptance=False,
                accepted_by=None,
                activity_logger=activity_logger,
                state=RunState.GATE_EVALUATED,
                flow_type=resolved_flow,
            )
            run_snap.mark_stage_complete("gate", success=gate.mergeable)
            run_snap.save(workspace)

            self._handle_gate_flow_signals(
                gate=gate,
                resolved_flow=resolved_flow,
                issue_id=issue.issue_id,
                run_id=run_id,
                activity_logger=activity_logger,
                workspace=workspace,
            )

        return RunResult(
            issue=issue,
            workspace=workspace,
            task_spec=task_spec,
            progress=progress,
            explain=explain,
            report=report,
            builder=builder,
            review=review,
            gate=gate,
            state=RunState.GATE_EVALUATED,
        )

    def _handle_gate_flow_signals(
        self,
        gate: GateVerdict,
        resolved_flow: FlowType,
        issue_id: str,
        run_id: str,
        activity_logger: ActivityLogger | None = None,
        workspace: Path = Path("."),
    ) -> None:
        """Process promotion, demotion, and backtrack signals from GateVerdict."""
        now = datetime.now(UTC).isoformat()

        if gate.promotion_required and gate.promotion_target:
            try:
                target_flow = FlowType(gate.promotion_target)
            except ValueError:
                self._event_logger.log_and_emit(
                    activity_logger=activity_logger,
                    workspace=workspace,
                    run_id=run_id,
                    issue_id=issue_id,
                    component="flow_engine",
                    event_type="promotion_invalid_target",
                    message=f"Invalid promotion target: {gate.promotion_target!r}",
                )
                return
            if _FLOW_ORDER.get(target_flow, 0) <= _FLOW_ORDER.get(resolved_flow, 0):
                self._event_logger.log_and_emit(
                    activity_logger=activity_logger,
                    workspace=workspace,
                    run_id=run_id,
                    issue_id=issue_id,
                    component="flow_engine",
                    event_type="promotion_same_or_lower",
                    message=f"Promotion target {target_flow} is not higher than {resolved_flow}",
                )
                return
            event = FlowTransitionEvent(
                from_flow=resolved_flow.value,
                to_flow=target_flow.value,
                trigger="promotion_required",
                timestamp=now,
                issue_id=issue_id,
                run_id=run_id,
            )
            record_flow_transition(event)
            self._event_logger.log_and_emit(
                activity_logger=activity_logger,
                workspace=workspace,
                run_id=run_id,
                issue_id=issue_id,
                component="flow_engine",
                event_type="flow_promoted",
                message=f"Flow promoted: {resolved_flow.value} → {target_flow.value}",
                data={"from_flow": resolved_flow.value, "to_flow": target_flow.value},
            )

        if gate.demotion_suggested and gate.demotion_target:
            event = FlowTransitionEvent(
                from_flow=resolved_flow.value,
                to_flow=gate.demotion_target,
                trigger="demotion_suggested",
                timestamp=now,
                issue_id=issue_id,
                run_id=run_id,
            )
            record_flow_transition(event)
            self._event_logger.log_and_emit(
                activity_logger=activity_logger,
                workspace=workspace,
                run_id=run_id,
                issue_id=issue_id,
                component="flow_engine",
                event_type="flow_demotion_suggested",
                message=f"Demotion suggested: {resolved_flow.value} → {gate.demotion_target}",
                data={"from_flow": resolved_flow.value, "to_flow": gate.demotion_target},
            )

        if gate.backtrack_reason:
            target_step = self.flow_engine.get_backtrack_target(
                resolved_flow, "gate", gate.backtrack_reason
            )
            self._event_logger.log_and_emit(
                activity_logger=activity_logger,
                workspace=workspace,
                run_id=run_id,
                issue_id=issue_id,
                component="flow_engine",
                event_type="backtrack_signal",
                message=f"Backtrack: reason={gate.backtrack_reason}, target_step={target_step}",
                data={
                    "reason": gate.backtrack_reason,
                    "target_step": target_step,
                },
            )

    def _load_existing_run(
        self,
        issue_id: str,
    ) -> tuple[Issue, Path, dict, str, BuilderResult, RunState]:
        """Load issue, workspace, report data, run_id, builder, and current
        state for an existing run.  Validates the issue_id and falls back to
        report.json when the issue source is unavailable."""
        if Path(issue_id).name != issue_id:
            raise ValueError(f"Invalid issue_id: {issue_id}")

        workspace = self.workspace_service.issue_workspace_path(issue_id)
        if not workspace.exists():
            raise FileNotFoundError(f"workspace not found for issue {issue_id}")

        report_data = RunReportWriter.load_persisted_run_payload(workspace)
        run_id: str = report_data["run_id"]
        builder = RunReportWriter.builder_from_report(report_data, workspace)

        raw_state = report_data.get("state")
        try:
            current_state = RunState(raw_state) if raw_state else RunState.GATE_EVALUATED
        except ValueError:
            current_state = RunState.GATE_EVALUATED

        try:
            issue = self.issue_source.load(issue_id)
        except Exception:
            issue = RunReportWriter.issue_from_report(report_data)

        return issue, workspace, report_data, run_id, builder, current_state

    def review_issue(
        self,
        issue_id: str,
        *,
        verdict: str,
        reviewed_by: str,
    ) -> RunResult:
        issue, workspace, report_data, run_id, builder, _prev_state = self._load_existing_run(
            issue_id
        )
        verification = RunReportWriter.verification_from_report(report_data)
        review = self.review_adapter.review(
            issue_id=issue.issue_id,
            workspace=workspace,
            verdict=verdict,
            reviewed_by=reviewed_by,
            builder_turn_contract_compliance=builder.metadata.get("turn_contract_compliance"),
        )
        human_acceptance = report_data["human_acceptance"]["accepted"]
        accepted_by = report_data["human_acceptance"]["accepted_by"]
        gate, explain, updated_report = self._finalize_run(
            issue=issue,
            workspace=workspace,
            run_id=run_id,
            builder=builder,
            verification=verification,
            review=review,
            human_acceptance=human_acceptance,
            accepted_by=accepted_by,
            state=RunState.GATE_EVALUATED,
            flow_type=self._resolve_flow(issue),
        )
        self.telemetry_service.log_event(
            workspace=workspace,
            run_id=run_id,
            issue_id=issue.issue_id,
            component="review",
            event_type="review_completed",
            message="Recorded review verdict.",
            data={"verdict": verdict, "reviewed_by": reviewed_by},
        )

        return RunResult(
            issue=issue,
            workspace=workspace,
            task_spec=workspace / "task.spec.md",
            progress=workspace / "progress.md",
            explain=explain,
            report=updated_report,
            builder=builder,
            review=review,
            gate=gate,
            state=RunState.GATE_EVALUATED,
        )

    def accept_issue(self, issue_id: str, *, accepted_by: str) -> RunResult:
        issue, workspace, report_data, run_id, builder, _prev_state = self._load_existing_run(
            issue_id
        )
        self.artifact_service.write_acceptance_artifact(
            workspace=workspace,
            issue_id=issue.issue_id,
            accepted_by=accepted_by,
        )
        verification = RunReportWriter.verification_from_report(report_data)
        review = RunReportWriter.review_from_report(report_data, workspace)
        gate, explain, updated_report = self._finalize_run(
            issue=issue,
            workspace=workspace,
            run_id=run_id,
            builder=builder,
            verification=verification,
            review=review,
            human_acceptance=True,
            accepted_by=accepted_by,
            state=RunState.ACCEPTED,
            flow_type=self._resolve_flow(issue),
        )
        self.telemetry_service.log_event(
            workspace=workspace,
            run_id=run_id,
            issue_id=issue.issue_id,
            component="acceptance",
            event_type="acceptance_recorded",
            message="Recorded human acceptance.",
            data={"accepted_by": accepted_by},
        )

        return RunResult(
            issue=issue,
            workspace=workspace,
            task_spec=workspace / "task.spec.md",
            progress=workspace / "progress.md",
            explain=explain,
            report=updated_report,
            builder=builder,
            review=review,
            gate=gate,
            state=RunState.ACCEPTED,
        )

    def rerun_issue(self, issue_id: str) -> RunResult:
        """Re-run verification and gate on an existing workspace.

        Resets review to pending since code may have changed.
        Falls back to report.json if issue source is unavailable.
        """
        issue, workspace, report_data, run_id, builder, _prev_state = self._load_existing_run(
            issue_id
        )

        with self._event_logger.open_activity_logger(workspace) as activity_logger:
            review = self.review_adapter.initialize(
                issue_id=issue.issue_id,
                workspace=workspace,
                builder_turn_contract_compliance=builder.metadata.get("turn_contract_compliance"),
            )
            acceptance_data = report_data.get("human_acceptance", {})
            human_acceptance = acceptance_data.get("accepted", False)
            accepted_by = acceptance_data.get("accepted_by")

            self._event_logger.log_and_emit(
                activity_logger=activity_logger,
                workspace=workspace,
                run_id=run_id,
                issue_id=issue.issue_id,
                component="verification",
                event_type="rerun_verification_started",
                message="Re-running verification steps.",
            )
            verification = self.verification_service.run(
                issue=issue,
                workspace=workspace,
            )
            self._event_logger.log_verification_events(
                workspace=workspace,
                issue_id=issue.issue_id,
                run_id=run_id,
                verification=verification,
                activity_logger=activity_logger,
            )

            gate, explain, updated_report = self._finalize_run(
                issue=issue,
                workspace=workspace,
                run_id=run_id,
                builder=builder,
                verification=verification,
                review=review,
                human_acceptance=human_acceptance,
                accepted_by=accepted_by,
                activity_logger=activity_logger,
                state=RunState.GATE_EVALUATED,
                flow_type=self._resolve_flow(issue),
            )
            self._event_logger.log_and_emit(
                activity_logger=activity_logger,
                workspace=workspace,
                run_id=run_id,
                issue_id=issue.issue_id,
                component="run_controller",
                event_type="rerun_completed",
                message="Completed re-run with fresh verification.",
                data={
                    "mergeable": gate.mergeable,
                    "failed_conditions": gate.failed_conditions,
                },
            )

        return RunResult(
            issue=issue,
            workspace=workspace,
            task_spec=workspace / "task.spec.md",
            progress=workspace / "progress.md",
            explain=explain,
            report=updated_report,
            builder=builder,
            review=review,
            gate=gate,
            state=RunState.GATE_EVALUATED,
        )

    def get_state(self, issue_id: str) -> RunState:
        """Return the current persisted state for *issue_id*."""
        workspace = self.workspace_service.issue_workspace_path(issue_id)
        state = RunReportWriter.read_state(workspace)
        if state is None:
            return RunState.DRAFT
        return state

    def advance_to_completion(self, issue_id: str, flow_type: FlowType | None = None) -> RunResult:
        """Drive *issue_id* through the full pipeline until GATE_EVALUATED or FAILED.

        Unlike ``advance()`` which executes a single transition, this loops
        continuously.  When the spec has unresolved blocking questions and a
        planner is available, it uses the planner's ``answer_questions`` to
        resolve them autonomously.
        """
        for _ in range(_MAX_ADVANCE_ITERATIONS):
            state = self.get_state(issue_id)
            if state in {RunState.GATE_EVALUATED, RunState.MERGED, RunState.ACCEPTED}:
                break
            if state == RunState.SPEC_DRAFTING and self.planner_adapter is not None:
                workspace = self.workspace_service.issue_workspace_path(issue_id)
                snapshot = read_spec_snapshot(workspace)
                if snapshot and snapshot.has_unresolved_blocking_questions():
                    issue = self.issue_source.load(issue_id)
                    planner_context = self.context_assembler.assemble(
                        get_node_context_spec("planner"),
                        issue,
                        workspace,
                        memory=self._get_memory(),
                    )
                    answer_fn = self.planner_adapter.answer_questions
                    if self._supports_context_kwarg(answer_fn):
                        snapshot = answer_fn(
                            snapshot=snapshot,
                            issue=issue,
                            context=planner_context,
                        )
                    else:
                        snapshot = answer_fn(
                            snapshot=snapshot,
                            issue=issue,
                        )
                    write_spec_snapshot(workspace, snapshot)
            result = self.advance(issue_id, flow_type=flow_type)
            if result.state == RunState.FAILED:
                return result
        else:
            return self.advance(issue_id, flow_type=flow_type)

        return self._load_final_result(issue_id)

    def _load_final_result(self, issue_id: str) -> RunResult:
        """Load a RunResult from persisted report.json for a completed run."""
        issue, workspace, report_data, run_id, builder, state = self._load_existing_run(issue_id)
        review = RunReportWriter.review_from_report(report_data, workspace)
        gate = GateVerdict(
            mergeable=report_data.get("mergeable", False),
            failed_conditions=report_data.get("failed_conditions", []),
        )
        return RunResult(
            issue=issue,
            workspace=workspace,
            task_spec=workspace / "task.spec.md",
            progress=workspace / "progress.md",
            explain=workspace / "explain.md",
            report=workspace / "report.json",
            builder=builder,
            review=review,
            gate=gate,
            state=state,
        )

    def advance(self, issue_id: str, flow_type: FlowType | None = None) -> RunResult:
        """Execute the next legal transition for *issue_id*.

        Supports:
          DRAFT             → SPEC_DRAFTING (requires planner_adapter)
          SPEC_DRAFTING     → SPEC_APPROVED (if no unresolved blocking questions)
          SPEC_APPROVED     → BUILDING      (delegates to run_issue)
          GATE_EVALUATED / REVIEW_PENDING / FAILED → rerun
        """
        state = self.get_state(issue_id)

        if state == RunState.DRAFT:
            return self._advance_draft(issue_id)

        if state == RunState.SPEC_DRAFTING:
            return self._advance_spec_drafting(issue_id)

        if state == RunState.SPEC_APPROVED:
            return self.run_issue(issue_id, flow_type=flow_type)

        if state in {RunState.GATE_EVALUATED, RunState.REVIEW_PENDING, RunState.FAILED}:
            return self.rerun_issue(issue_id)

        raise ValueError(
            f"Cannot auto-advance from state {state.value!r}. "
            "Use run_issue(), review_issue(), or accept_issue() explicitly."
        )

    def _advance_draft(self, issue_id: str) -> RunResult:
        """DRAFT → SPEC_DRAFTING: invoke planner to generate questions."""
        issue = self.issue_source.load(issue_id)
        workspace = self.workspace_service.prepare_issue_workspace(issue.issue_id)
        run_id = self.telemetry_service.new_run_id(issue.issue_id)

        if self.planner_adapter is None:
            RunReportWriter.persist_state(workspace, issue, run_id, RunState.SPEC_DRAFTING)
            return self._stub_result(
                issue,
                workspace,
                RunState.SPEC_DRAFTING,
                message="Awaiting manual spec drafting (no planner configured).",
            )

        existing_snapshot = read_spec_snapshot(workspace)
        planner_context = self.context_assembler.assemble(
            get_node_context_spec("planner"),
            issue,
            workspace,
            memory=self._get_memory(),
        )
        plan_fn = self.planner_adapter.plan
        if self._supports_context_kwarg(plan_fn):
            planner_result = plan_fn(
                issue=issue,
                workspace=workspace,
                existing_snapshot=existing_snapshot,
                context=planner_context,
            )
        else:
            planner_result = plan_fn(
                issue=issue,
                workspace=workspace,
                existing_snapshot=existing_snapshot,
            )

        snapshot = planner_result.spec_draft or create_initial_snapshot(issue)
        for q in planner_result.questions:
            snapshot.questions.append(q)
        write_spec_snapshot(workspace, snapshot)

        RunReportWriter.persist_state(workspace, issue, run_id, RunState.SPEC_DRAFTING)
        self.telemetry_service.log_event(
            workspace=workspace,
            run_id=run_id,
            issue_id=issue.issue_id,
            component="planner",
            event_type="spec_drafting_started",
            message=f"Planner generated {len(planner_result.questions)} question(s).",
            data={"questions": len(planner_result.questions)},
        )
        return self._stub_result(issue, workspace, RunState.SPEC_DRAFTING)

    def _advance_spec_drafting(self, issue_id: str) -> RunResult:
        """SPEC_DRAFTING → SPEC_APPROVED: approve if no blocking questions remain."""
        issue = self.issue_source.load(issue_id)
        workspace = self.workspace_service.issue_workspace_path(issue.issue_id)
        snapshot = read_spec_snapshot(workspace)

        if snapshot is None:
            snapshot = create_initial_snapshot(issue)

        if snapshot.has_unresolved_blocking_questions():
            raise ValueError(
                "Cannot approve spec: unresolved blocking questions remain. "
                "Use `spec-orch questions list` and `spec-orch questions answer` first."
            )

        snapshot.approved = True
        snapshot.version += 1
        write_spec_snapshot(workspace, snapshot)

        run_id = self.telemetry_service.new_run_id(issue.issue_id)
        RunReportWriter.persist_state(workspace, issue, run_id, RunState.SPEC_APPROVED)
        self.telemetry_service.log_event(
            workspace=workspace,
            run_id=run_id,
            issue_id=issue.issue_id,
            component="spec",
            event_type="spec_approved",
            message="Spec snapshot approved; ready for building.",
        )
        return self._stub_result(issue, workspace, RunState.SPEC_APPROVED)

    def _stub_result(
        self,
        issue: Issue,
        workspace: Path,
        state: RunState,
        *,
        message: str = "",
    ) -> RunResult:
        """Return a RunResult for pre-build states (no builder/gate yet)."""
        dummy_builder = BuilderResult(
            succeeded=False,
            command=[],
            stdout=message,
            stderr="",
            report_path=workspace / "builder_report.json",
            adapter="none",
            agent="none",
            skipped=True,
        )
        return RunResult(
            issue=issue,
            workspace=workspace,
            task_spec=workspace / "task.spec.md",
            progress=workspace / "progress.md",
            explain=workspace / "explain.md",
            report=workspace / "report.json",
            builder=dummy_builder,
            review=ReviewSummary(),
            gate=GateVerdict(
                mergeable=False,
                failed_conditions=["pre_build"],
            ),
            state=state,
        )

    def _finalize_run(
        self,
        *,
        issue: Issue,
        workspace: Path,
        run_id: str,
        builder: BuilderResult,
        verification: VerificationSummary,
        review: ReviewSummary,
        human_acceptance: bool,
        accepted_by: str | None,
        activity_logger: ActivityLogger | None = None,
        state: RunState = RunState.GATE_EVALUATED,
        flow_type: FlowType | None = None,
    ) -> tuple[GateVerdict, Path, Path]:
        snapshot = read_spec_snapshot(workspace)
        spec_exists = snapshot is not None
        spec_approved = snapshot.approved if snapshot else False

        deviations = detect_deviations(workspace=workspace, snapshot=snapshot)
        overwrite_deviations(workspace, deviations)
        within_boundaries = len(deviations) == 0

        gate = self.gate_service.evaluate(
            GateInput(
                spec_exists=spec_exists,
                spec_approved=spec_approved,
                within_boundaries=within_boundaries,
                builder_succeeded=builder.succeeded,
                verification=verification,
                review=review,
                human_acceptance=human_acceptance,
                claimed_flow=flow_type.value if flow_type else None,
                issue_id=issue.issue_id,
            )
        )
        self._event_logger.log_gate_event(
            workspace=workspace,
            issue_id=issue.issue_id,
            run_id=run_id,
            gate=gate,
            activity_logger=activity_logger,
        )
        explain = self.artifact_service.write_explain_report(
            workspace=workspace,
            issue_id=issue.issue_id,
            issue_title=issue.title,
            mergeable=gate.mergeable,
            failed_conditions=gate.failed_conditions,
            builder_status=self._builder_status(builder),
            review_status=review.verdict,
            reviewed_by=review.reviewed_by,
            acceptance_status="accepted" if human_acceptance else "pending",
            accepted_by=accepted_by,
            builder_contract_compliance=builder.metadata.get("turn_contract_compliance"),
            builder_adapter=builder.adapter,
            verification=verification,
            acceptance_criteria=issue.acceptance_criteria,
        )
        report = RunReportWriter.write_report(
            workspace=workspace,
            issue=issue,
            run_id=run_id,
            gate=gate,
            builder=builder,
            review=review,
            verification=verification,
            accepted_by=accepted_by,
            state=state,
        )
        RunReportWriter.write_artifact_manifest(
            workspace=workspace,
            run_id=run_id,
            issue=issue,
            builder=builder,
            review=review,
            explain=explain,
            report=report,
        )
        self.run_artifact_service.write_from_run(
            workspace=workspace,
            run_id=run_id,
            issue_id=issue.issue_id,
            report_path=report,
            explain_path=explain,
        )
        self._maybe_trigger_evolution(workspace)
        self._event_logger.maybe_sample_for_eval(
            run_id=run_id,
            gate=gate,
            builder=builder,
            issue_id=issue.issue_id,
        )
        return gate, explain, report

    def _maybe_trigger_evolution(self, workspace: Path) -> None:
        """Run the evolution cycle if configured and threshold is met."""
        toml_path = self.repo_root / "spec-orch.toml"
        if not toml_path.exists():
            return
        try:
            toml_data = RunReportWriter.load_toml(toml_path)
        except Exception:
            import logging

            logging.getLogger(__name__).warning(
                "Failed to load spec-orch.toml for evolution trigger",
                exc_info=True,
            )
            return
        from spec_orch.services.evolution_trigger import EvolutionConfig, EvolutionTrigger

        config = EvolutionConfig.from_toml(toml_data)
        if not config.enabled:
            return
        trigger = EvolutionTrigger(
            self.repo_root,
            config,
            planner=self.planner_adapter,
            latest_workspace=workspace,
        )
        result = trigger.run_evolution_cycle()
        if result.triggered:
            import logging

            logging.getLogger(__name__).info(
                "Evolution cycle triggered: prompt_evolved=%s, hints=%s, rules=%d",
                result.prompt_evolved,
                result.plan_hints_generated,
                result.harness_rules_proposed,
            )

    def _builder_status(self, builder) -> str:
        if builder.skipped:
            return "skipped"
        if builder.succeeded:
            return "passed"
        return "failed"

    @staticmethod
    def _render_builder_envelope(issue: Issue, workspace: Path) -> str:
        """Render a structured envelope that replaces bare builder_prompt."""
        sections: list[str] = []
        base = issue.builder_prompt or issue.summary or ""
        sections.append(f"## Task\n{base}")

        if issue.acceptance_criteria:
            items = "\n".join(f"- {c}" for c in issue.acceptance_criteria)
            sections.append(f"## Acceptance Criteria\n{items}")

        if issue.context.constraints:
            items = "\n".join(f"- {c}" for c in issue.context.constraints)
            sections.append(f"## Constraints\n{items}")

        if issue.context.files_to_read:
            items = "\n".join(f"- {f}" for f in issue.context.files_to_read)
            sections.append(f"## Files to Read\n{items}")

        if issue.verification_commands:
            cmds = "\n".join(
                f"- {name}: `{' '.join(cmd)}`" for name, cmd in issue.verification_commands.items()
            )
            sections.append(f"## Verification Commands\n{cmds}")

        spec_path = workspace / "task.spec.md"
        if spec_path.exists():
            spec_text = spec_path.read_text()
            if len(spec_text) > 4000:
                spec_text = spec_text[:4000] + "\n... [truncated]"
            if spec_text.strip():
                sections.append(f"## Spec\n{spec_text}")

        return "\n\n".join(sections)

    def _run_builder(
        self,
        *,
        issue: Issue,
        workspace: Path,
        run_id: str,
        activity_logger: ActivityLogger | None = None,
    ) -> BuilderResult:
        if issue.builder_prompt:
            from dataclasses import replace

            enriched_prompt = self._render_builder_envelope(issue, workspace)
            enriched_issue = replace(issue, builder_prompt=enriched_prompt)
        else:
            enriched_issue = issue

        adapter_name = self.builder_adapter.ADAPTER_NAME
        agent_name = self.builder_adapter.AGENT_NAME
        self._event_logger.log_and_emit(
            activity_logger=activity_logger,
            workspace=workspace,
            run_id=run_id,
            issue_id=issue.issue_id,
            component="builder",
            event_type="builder_started",
            message="Started builder adapter.",
            adapter=adapter_name,
            agent=agent_name,
        )
        try:
            builder = self.builder_adapter.run(
                issue=enriched_issue,
                workspace=workspace,
                run_id=run_id,
                event_logger=self._event_logger.make_event_logger(
                    workspace=workspace,
                    run_id=run_id,
                    issue_id=issue.issue_id,
                    activity_logger=activity_logger,
                ),
            )
        except Exception as exc:
            compliance = evaluate_pre_action_narration_compliance(
                workspace / "telemetry" / "incoming_events.jsonl"
            )
            command = getattr(self.builder_adapter, "command", [])
            builder = BuilderResult(
                succeeded=False,
                command=command,
                stdout="",
                stderr=str(exc),
                report_path=workspace / "builder_report.json",
                adapter=adapter_name,
                agent=agent_name,
                metadata={
                    "run_id": run_id,
                    "failure_reason": str(exc),
                    "turn_contract_compliance": compliance,
                },
            )
        builder.metadata.setdefault("turn_contract_compliance", default_turn_contract_compliance())
        builder.metadata["run_id"] = run_id
        if not builder.report_path.is_absolute():
            builder.report_path = builder.report_path.resolve()
        from spec_orch.services.codex_exec_builder_adapter import (
            _write_report as write_builder_report,
        )

        if builder.adapter == adapter_name:
            write_builder_report(builder)
        self._event_logger.log_and_emit(
            activity_logger=activity_logger,
            workspace=workspace,
            run_id=run_id,
            issue_id=issue.issue_id,
            component="builder",
            event_type="builder_completed",
            severity="info" if builder.succeeded else "error",
            message="Builder adapter completed.",
            adapter=builder.adapter,
            agent=builder.agent,
            data={"succeeded": builder.succeeded, "skipped": builder.skipped},
        )
        return builder
