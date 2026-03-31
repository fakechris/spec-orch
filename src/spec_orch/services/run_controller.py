from __future__ import annotations

import inspect
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any

from spec_orch.contract_core.snapshots import (
    auto_approve_spec_snapshot,
    create_initial_snapshot,
    read_spec_snapshot,
    write_spec_snapshot,
)
from spec_orch.decision_core.inventory import decision_point_for_flow_router_source
from spec_orch.domain.compliance import (
    default_turn_contract_compliance,
    evaluate_pre_action_narration_compliance,
)
from spec_orch.domain.models import (
    BuilderResult,
    FlowGraph,
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
from spec_orch.services.telemetry_service import TelemetryService
from spec_orch.services.verification_service import VerificationService
from spec_orch.services.workspace_service import WorkspaceService

logger = logging.getLogger(__name__)

_MAX_ADVANCE_ITERATIONS = 10
_FLOW_ORDER: dict[FlowType, int] = {FlowType.HOTFIX: 0, FlowType.STANDARD: 1, FlowType.FULL: 2}

_EXECUTION_STEP_HANDLERS: dict[str, str] = {
    "execute": "_handle_builder_step",
    "implement": "_handle_builder_step",
    "verify": "_handle_verify_step",
    "gate": "_handle_gate_step",
}

_STEP_TO_PROGRESS_STAGE: dict[str, str] = {
    "execute": "builder",
    "implement": "builder",
    "verify": "verification",
}

_STATE_TO_STEP: dict[RunState, tuple[str, ...]] = {
    RunState.SPEC_DRAFTING: ("freeze_spec",),
    RunState.SPEC_APPROVED: ("mission_approve",),
    RunState.BUILDING: ("execute", "implement"),
    RunState.VERIFYING: ("verify",),
    RunState.GATE_EVALUATED: ("gate",),
    RunState.REVIEW_PENDING: ("pr_review", "pre_merge_review"),
    RunState.MERGED: ("merge",),
}


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
        require_spec_approval: bool = True,
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
        self._runs_since_compaction = 0
        self.require_spec_approval = require_spec_approval

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
            decision_point = decision_point_for_flow_router_source(decision.source)
            logger.info(
                "FlowRouter decision: %s (confidence=%.2f, source=%s) — %s",
                decision.recommended_flow,
                decision.confidence,
                decision.source,
                decision.reasoning,
                extra={
                    "decision_point_key": decision_point.key,
                    "decision_authority": decision_point.authority.value,
                    "decision_owner": decision_point.owner,
                },
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
    def _resolve_active_conditions(issue: Issue) -> set[str]:
        """Extract active conditions from issue labels and priority."""
        conditions: set[str] = set()
        labels_lower = {lbl.lower() for lbl in (issue.labels or [])}
        if labels_lower & {"doc-only", "doc_only", "documentation"}:
            conditions.add("doc_only")
        if labels_lower & {"urgent", "hotfix", "p0", "critical"}:
            conditions.add("urgent")
        return conditions

    @staticmethod
    def _supports_context_kwarg(method: Any) -> bool:
        try:
            return "context" in inspect.signature(method).parameters
        except (TypeError, ValueError):
            return False

    def run_issue(self, issue_id: str, flow_type: FlowType | None = None) -> RunResult:
        """Run an issue through the execution pipeline driven by FlowEngine graph.

        Walks the graph steps in order, skipping pre-execution steps and
        applying ``is_skippable()`` for conditional steps (e.g. doc_only,
        urgent).  Each handled step is dispatched to a registered handler.
        """
        issue = self.issue_source.load(issue_id)
        resolved_flow = flow_type or self._resolve_flow(issue)
        workspace = self.workspace_service.prepare_issue_workspace(issue.issue_id)
        run_id = self.telemetry_service.new_run_id(issue.issue_id)
        graph = self.flow_engine.get_graph(resolved_flow)
        active_conditions = self._resolve_active_conditions(issue)

        prev_snap = RunProgressSnapshot.load(workspace)
        completed_stages: set[str] = prev_snap.completed_stage_names() if prev_snap else set()

        run_snap = RunProgressSnapshot.create(run_id=run_id, issue_id=issue.issue_id)
        if prev_snap:
            run_snap.stages = list(prev_snap.stages)

        ctx: dict[str, Any] = {
            "issue": issue,
            "workspace": workspace,
            "run_id": run_id,
            "run_snap": run_snap,
            "resolved_flow": resolved_flow,
            "builder": None,
            "verification": None,
            "review": None,
            "gate": None,
            "explain": None,
            "report": None,
            "task_spec": None,
            "progress": None,
        }

        with self._event_logger.open_activity_logger(workspace) as activity_logger:
            ctx["activity_logger"] = activity_logger
            self._event_logger.log_and_emit(
                activity_logger=activity_logger,
                workspace=workspace,
                run_id=run_id,
                issue_id=issue.issue_id,
                component="run_controller",
                event_type="run_started",
                message=f"Started issue run (flow={resolved_flow.value}).",
                data={"flow_type": resolved_flow.value},
            )

            task_spec, progress = self.artifact_service.write_initial_artifacts(
                workspace=workspace,
                issue_id=issue.issue_id,
                issue_title=issue.title,
            )
            ctx["task_spec"] = task_spec
            ctx["progress"] = progress

            spec_result = self._handle_spec_step(ctx)
            if spec_result is not None:
                return spec_result

            for step in graph.steps:
                handler_name = _EXECUTION_STEP_HANDLERS.get(step.id)
                if handler_name is None:
                    continue

                progress_stage = _STEP_TO_PROGRESS_STAGE.get(step.id)
                if progress_stage and progress_stage in completed_stages:
                    self._resume_completed_step(ctx, step.id, progress_stage)
                    force_rerun = ctx.get("_force_rerun_steps", set())
                    if step.id not in force_rerun:
                        self._event_logger.log_and_emit(
                            activity_logger=activity_logger,
                            workspace=workspace,
                            run_id=run_id,
                            issue_id=issue.issue_id,
                            component="flow_engine",
                            event_type="step_resumed",
                            message=(
                                f"Resumed step '{step.id}' from previous run "
                                f"(stage '{progress_stage}' already succeeded)."
                            ),
                            data={"step": step.id, "stage": progress_stage},
                        )
                        continue

                if self.flow_engine.is_skippable(resolved_flow, step.id, active_conditions):
                    self._event_logger.log_and_emit(
                        activity_logger=activity_logger,
                        workspace=workspace,
                        run_id=run_id,
                        issue_id=issue.issue_id,
                        component="flow_engine",
                        event_type="step_skipped",
                        message=f"Skipped step '{step.id}' (conditions: {active_conditions}).",
                        data={"step": step.id, "conditions": sorted(active_conditions)},
                    )
                    continue

                handler = getattr(self, handler_name)
                early_return: RunResult | None = handler(ctx)
                if early_return is not None:
                    return early_return

        return RunResult(
            issue=issue,
            workspace=workspace,
            task_spec=ctx["task_spec"],
            progress=ctx["progress"],
            explain=ctx["explain"],
            report=ctx["report"],
            builder=ctx["builder"],
            review=ctx["review"],
            gate=ctx["gate"],
            state=RunState.GATE_EVALUATED,
        )

    def _handle_spec_step(self, ctx: dict[str, Any]) -> RunResult | None:
        """Handle freeze_spec step: check or create spec snapshot."""
        issue = ctx["issue"]
        workspace = ctx["workspace"]
        run_id = ctx["run_id"]
        activity_logger = ctx.get("activity_logger")

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
            return None

        if existing_snapshot is not None and self.require_spec_approval:
            self._event_logger.log_and_emit(
                activity_logger=activity_logger,
                workspace=workspace,
                run_id=run_id,
                issue_id=issue.issue_id,
                component="spec",
                event_type="spec_awaiting_approval",
                message="Spec snapshot exists and is awaiting approval before build.",
                data={"version": existing_snapshot.version, "approved": False},
            )
            RunReportWriter.persist_state(
                workspace,
                issue,
                run_id,
                RunState.SPEC_DRAFTING,
            )
            return self._stub_result(
                issue,
                workspace,
                RunState.SPEC_DRAFTING,
                message="Spec requires approval. Use 'advance' after approving.",
            )

        if existing_snapshot is not None:
            auto_approve_spec_snapshot(existing_snapshot)
            write_spec_snapshot(workspace, existing_snapshot)
            self._event_logger.log_and_emit(
                activity_logger=activity_logger,
                workspace=workspace,
                run_id=run_id,
                issue_id=issue.issue_id,
                component="spec",
                event_type="spec_snapshot_auto_approved",
                message=(f"Existing spec snapshot auto-approved as v{existing_snapshot.version}."),
                data={"version": existing_snapshot.version, "approved": True},
            )
            return None

        if self.require_spec_approval:
            snapshot = create_initial_snapshot(issue, approved=False)
            write_spec_snapshot(workspace, snapshot)
            self._event_logger.log_and_emit(
                activity_logger=activity_logger,
                workspace=workspace,
                run_id=run_id,
                issue_id=issue.issue_id,
                component="spec",
                event_type="spec_awaiting_approval",
                message="Spec snapshot created; awaiting approval before build.",
                data={"version": 1, "approved": False},
            )
            RunReportWriter.persist_state(
                workspace,
                issue,
                run_id,
                RunState.SPEC_DRAFTING,
            )
            return self._stub_result(
                issue,
                workspace,
                RunState.SPEC_DRAFTING,
                message="Spec requires approval. Use 'advance' after approving.",
            )

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
        return None

    def _resume_completed_step(self, ctx: dict[str, Any], step_id: str, stage: str) -> None:
        """Restore ctx data for a previously completed stage from persisted artifacts."""
        workspace = ctx["workspace"]
        try:
            report_data = RunReportWriter.load_persisted_run_payload(workspace)
            if stage == "builder":
                ctx["builder"] = RunReportWriter.builder_from_report(report_data, workspace)
            elif stage == "verification":
                ctx["verification"] = RunReportWriter.verification_from_report(report_data)
        except (KeyError, FileNotFoundError, TypeError, AttributeError):
            logger.warning("Cannot restore %s from report; will re-run", stage)
            force_rerun = ctx.setdefault("_force_rerun_steps", set())
            force_rerun.add(step_id)
            if stage == "builder":
                force_rerun.add("verify")

    def _handle_builder_step(self, ctx: dict[str, Any]) -> RunResult | None:
        """Handle execute/implement step: run the builder."""
        run_snap: RunProgressSnapshot = ctx["run_snap"]
        run_snap.mark_stage_start("builder")
        builder = self._run_builder(
            issue=ctx["issue"],
            workspace=ctx["workspace"],
            run_id=ctx["run_id"],
            activity_logger=ctx.get("activity_logger"),
        )
        run_snap.mark_stage_complete("builder", success=builder.succeeded)
        run_snap.save(ctx["workspace"])
        ctx["builder"] = builder
        return None

    def _handle_verify_step(self, ctx: dict[str, Any]) -> RunResult | None:
        """Handle verify step: run verification commands."""
        run_snap: RunProgressSnapshot = ctx["run_snap"]
        activity_logger = ctx.get("activity_logger")
        run_snap.mark_stage_start("verification")
        self._event_logger.log_and_emit(
            activity_logger=activity_logger,
            workspace=ctx["workspace"],
            run_id=ctx["run_id"],
            issue_id=ctx["issue"].issue_id,
            component="verification",
            event_type="verification_started",
            message="Started verification steps.",
        )
        verification = self.verification_service.run(
            issue=ctx["issue"],
            workspace=ctx["workspace"],
        )
        v_passed = sum(1 for v in verification.step_results.values() if v)
        v_total = len(verification.step_results)
        run_snap.mark_stage_complete(
            "verification",
            success=all(verification.step_results.values()) if verification.step_results else True,
            detail=f"{v_passed}/{v_total} checks passed",
        )
        run_snap.save(ctx["workspace"])
        self._event_logger.log_verification_events(
            workspace=ctx["workspace"],
            issue_id=ctx["issue"].issue_id,
            run_id=ctx["run_id"],
            verification=verification,
            activity_logger=activity_logger,
        )
        ctx["verification"] = verification
        return None

    def _handle_gate_step(self, ctx: dict[str, Any]) -> RunResult | None:
        """Handle gate step: initialize review, then evaluate gate conditions."""
        run_snap: RunProgressSnapshot = ctx["run_snap"]
        activity_logger = ctx.get("activity_logger")

        builder = ctx.get("builder")
        if builder is None:
            builder = BuilderResult(
                succeeded=True,
                command=[],
                stdout="",
                stderr="",
                report_path=ctx["workspace"] / "builder_report.json",
                adapter="none",
                agent="none",
                skipped=True,
            )
            ctx["builder"] = builder

        verification = ctx.get("verification")
        if verification is None:
            verification = VerificationSummary()
            ctx["verification"] = verification

        if ctx.get("review") is None:
            run_snap.mark_stage_start("review")
            review = self.review_adapter.initialize(
                issue_id=ctx["issue"].issue_id,
                workspace=ctx["workspace"],
                builder_turn_contract_compliance=(
                    builder.metadata.get("turn_contract_compliance") if builder else None
                ),
            )
            run_snap.mark_stage_complete(
                "review",
                success=review.verdict != "rejected",
            )
            run_snap.save(ctx["workspace"])
            self._event_logger.log_and_emit(
                activity_logger=activity_logger,
                workspace=ctx["workspace"],
                run_id=ctx["run_id"],
                issue_id=ctx["issue"].issue_id,
                component="review",
                event_type="review_initialized",
                message="Initialized review state.",
                data={"verdict": review.verdict},
            )
            ctx["review"] = review

        run_snap.mark_stage_start("gate")
        gate, explain, report = self._finalize_run(
            issue=ctx["issue"],
            workspace=ctx["workspace"],
            run_id=ctx["run_id"],
            builder=builder,
            verification=verification,
            review=ctx["review"],
            human_acceptance=False,
            accepted_by=None,
            activity_logger=activity_logger,
            state=RunState.GATE_EVALUATED,
            flow_type=ctx["resolved_flow"],
        )
        run_snap.mark_stage_complete("gate", success=gate.mergeable)
        run_snap.save(ctx["workspace"])
        self._handle_gate_flow_signals(
            gate=gate,
            resolved_flow=ctx["resolved_flow"],
            issue_id=ctx["issue"].issue_id,
            run_id=ctx["run_id"],
            activity_logger=activity_logger,
            workspace=ctx["workspace"],
        )
        ctx["gate"] = gate
        ctx["explain"] = explain
        ctx["report"] = report
        return None

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

    def _find_current_step_id(
        self,
        state: RunState,
        graph: FlowGraph,
    ) -> str | None:
        """Map a RunState to its corresponding graph step ID."""
        candidates = _STATE_TO_STEP.get(state, ())
        step_ids = set(graph.step_ids())
        for cid in candidates:
            if cid in step_ids:
                return cid
        return None

    def advance(self, issue_id: str, flow_type: FlowType | None = None) -> RunResult:
        """Execute the next legal transition for *issue_id*.

        Uses FlowEngine graph transitions to determine the next step
        rather than hardcoded RunState branching.
        """
        state = self.get_state(issue_id)
        issue = self.issue_source.load(issue_id)
        resolved_flow = flow_type or self._resolve_flow(issue)
        graph = self.flow_engine.get_graph(resolved_flow)

        if state == RunState.DRAFT:
            return self._advance_draft(issue_id)

        if state == RunState.SPEC_DRAFTING:
            return self._advance_spec_drafting(issue_id)

        if state == RunState.SPEC_APPROVED:
            return self.run_issue(issue_id, flow_type=flow_type)

        current_step_id = self._find_current_step_id(state, graph)
        if current_step_id is not None:
            next_steps = self.flow_engine.get_next_steps(resolved_flow, current_step_id)
            if next_steps:
                next_id = next_steps[0]
                if next_id in _EXECUTION_STEP_HANDLERS or next_id in (
                    "mission_approve",
                    "generate_plan",
                    "promote_issues",
                    "generate_contracts",
                    "create_branch",
                ):
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
        self._consolidate_run_memory(
            run_id=run_id,
            issue_id=issue.issue_id,
            gate=gate,
            workspace=workspace,
            builder=builder,
            verification=verification,
            human_acceptance=human_acceptance,
            accepted_by=accepted_by,
        )
        self._maybe_trigger_evolution(workspace)
        self._event_logger.maybe_sample_for_eval(
            run_id=run_id,
            gate=gate,
            builder=builder,
            issue_id=issue.issue_id,
        )
        return gate, explain, report

    _COMPACT_EVERY_N_RUNS = 10

    def _consolidate_run_memory(
        self,
        *,
        run_id: str,
        issue_id: str,
        gate: GateVerdict,
        workspace: Path | None = None,
        builder: BuilderResult | None = None,
        verification: VerificationSummary | None = None,
        human_acceptance: bool = False,
        accepted_by: str | None = None,
    ) -> None:
        """Store run outcome + telemetry in memory for cross-run learning."""
        try:
            from spec_orch.services.memory.service import get_memory_service

            memory = get_memory_service(repo_root=self.repo_root)

            key_learnings = self._extract_key_learnings(
                builder=builder,
                verification=verification,
                gate=gate,
            )
            memory.consolidate_run(
                run_id=run_id,
                issue_id=issue_id,
                succeeded=gate.mergeable,
                failed_conditions=gate.failed_conditions,
                key_learnings=key_learnings,
                builder_adapter=builder.adapter if builder else None,
                verification_passed=verification.all_passed if verification else None,
            )

            if workspace is not None:
                self._store_builder_telemetry(memory, run_id, issue_id, workspace)
                from spec_orch.runtime_core.readers import read_issue_execution_attempt

                normalized_attempt = read_issue_execution_attempt(workspace)
                if normalized_attempt is not None:
                    memory.record_execution_outcome(attempt=normalized_attempt)

            if human_acceptance and accepted_by:
                memory.record_acceptance(
                    issue_id=issue_id,
                    accepted_by=accepted_by,
                    run_id=run_id,
                )

            self._runs_since_compaction += 1
            if self._runs_since_compaction >= self._COMPACT_EVERY_N_RUNS:
                planner_cfg = self._load_planner_config_for_compact()
                memory.compact(planner_config=planner_cfg)
                self._runs_since_compaction = 0
        except Exception:
            logger.debug("Memory consolidation skipped", exc_info=True)

    @staticmethod
    def _extract_key_learnings(
        *,
        builder: BuilderResult | None,
        verification: VerificationSummary | None,
        gate: GateVerdict,
    ) -> str:
        """Summarize key facts from this run for the run-summary entry."""
        parts: list[str] = []
        if builder:
            parts.append(f"Builder: {builder.adapter or 'unknown'}, succeeded={builder.succeeded}")
            compliance = builder.metadata.get("turn_contract_compliance")
            if compliance:
                parts.append(f"Contract compliance: {compliance}")
        if verification:
            step_results = ", ".join(
                f"{k}={'pass' if v else 'fail'}" for k, v in verification.step_results.items()
            )
            parts.append(f"Verification: all_passed={verification.all_passed}")
            if step_results:
                parts.append(f"Steps: {step_results}")
        if gate.failed_conditions:
            parts.append(f"Failed conditions: {', '.join(gate.failed_conditions)}")
        return "\n".join(parts)

    @staticmethod
    def _store_builder_telemetry(
        memory: Any,
        run_id: str,
        issue_id: str,
        workspace: Path,
    ) -> None:
        """Read builder telemetry JSONL and store tool sequence in memory."""
        import json as _json

        for candidate in [
            workspace / "telemetry" / "incoming_events.jsonl",
            workspace / "builder_events.jsonl",
        ]:
            if candidate.exists():
                telemetry_path = candidate
                break
        else:
            return

        try:
            text = telemetry_path.read_text(encoding="utf-8")
        except OSError:
            return

        seq: list[str] = []
        lines_read = 0
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            lines_read += 1
            if lines_read > 2000:
                break
            try:
                obj = _json.loads(stripped)
            except (ValueError, _json.JSONDecodeError):
                continue
            if not isinstance(obj, dict):
                continue
            tool = obj.get("tool") or obj.get("tool_name") or obj.get("function", "")
            if tool:
                seq.append(str(tool))

        if seq:
            memory.record_builder_telemetry(
                run_id=run_id,
                issue_id=issue_id,
                tool_sequence=seq,
                lines_scanned=lines_read,
                source_path=str(telemetry_path),
            )

    def _load_planner_config_for_compact(self) -> dict[str, Any] | None:
        """Load [planner] config from TOML for memory distillation."""
        import os

        toml_path = self.repo_root / "spec-orch.toml"
        if not toml_path.exists():
            return None
        try:
            raw = RunReportWriter.load_toml(toml_path)
        except Exception:
            return None
        cfg = raw.get("planner")
        if not isinstance(cfg, dict):
            return None
        result: dict[str, Any] = {}
        if cfg.get("model"):
            result["model"] = cfg["model"]
        if cfg.get("api_type"):
            result["api_type"] = cfg["api_type"]
        if cfg.get("api_key_env"):
            result["api_key"] = os.environ.get(cfg["api_key_env"], "")
        if cfg.get("api_base_env"):
            result["api_base"] = os.environ.get(cfg["api_base_env"], "")
        return result

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
    def _render_builder_envelope(
        issue: Issue,
        workspace: Path,
        *,
        repo_root: Path | None = None,
    ) -> str:
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

        btw_candidates = [workspace / "btw_context.md"]
        if repo_root is not None:
            btw_candidates.append(
                Path(repo_root) / ".spec_orch_runs" / issue.issue_id / "btw_context.md"
            )
        for btw_path in btw_candidates:
            if not btw_path.exists():
                continue
            try:
                btw_content = btw_path.read_text(encoding="utf-8").strip()
            except OSError as exc:
                logger.warning("Failed to read /btw context from %s: %s", btw_path, exc)
                continue
            except UnicodeDecodeError as exc:
                logger.warning("Failed to decode /btw context from %s: %s", btw_path, exc)
                continue
            if btw_content:
                sections.append(f"## Additional Context (injected via /btw)\n\n{btw_content}")
                break

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

            enriched_prompt = self._render_builder_envelope(
                issue,
                workspace,
                repo_root=self.repo_root,
            )
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
