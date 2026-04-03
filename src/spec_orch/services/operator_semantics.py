from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from spec_orch.acceptance_core.calibration import AcceptanceSurfacePack
from spec_orch.acceptance_core.models import AcceptanceJudgment, AcceptanceJudgmentClass
from spec_orch.domain.execution_semantics import (
    ExecutionAttempt,
    ExecutionAttemptState,
    ExecutionStatus,
)
from spec_orch.domain.intake_models import CanonicalIssue
from spec_orch.domain.models import AcceptanceReviewResult
from spec_orch.domain.operator_semantics import (
    ArtifactEnvelope,
    CandidateFinding,
    CompareOverlay,
    EvidenceBundle,
    ExecutionSession,
    Judgment,
    JudgmentTimelineEntry,
    LearningLineage,
    Observation,
    SubjectRef,
    SurfacePack,
    Workspace,
)
from spec_orch.runtime_chain.models import ChainPhase, RuntimeChainStatus


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def handoff_blockers_for_canonical_issue(canonical: CanonicalIssue) -> list[str]:
    blockers: list[str] = []
    if not canonical.problem.strip():
        blockers.append("problem")
    if not canonical.goal.strip():
        blockers.append("goal")
    if not canonical.acceptance.success_conditions:
        blockers.append("acceptance")
    if not canonical.acceptance.verification_expectations:
        blockers.append("verification_expectations")
    if any(item.strip().lower().startswith("[blocking]") for item in canonical.open_questions):
        blockers.append("blocking_open_questions")
    return blockers


def handoff_state_for_canonical_issue(canonical: CanonicalIssue) -> str:
    blockers = handoff_blockers_for_canonical_issue(canonical)
    if not blockers:
        return "ready_for_workspace"
    if canonical.problem.strip() and canonical.goal.strip():
        return "canonicalized"
    return "draft_only"


def workspace_from_canonical_issue(
    canonical: CanonicalIssue,
    *,
    subject_kind: str = "issue",
) -> Workspace:
    timestamp = _now_iso()
    state_summary = handoff_state_for_canonical_issue(canonical)
    workspace_id = canonical.issue_id
    workspace_kind = "mission" if subject_kind == "mission" else "issue"
    execution_session_id = f"{workspace_id}:execution"
    judgment_id = f"{workspace_id}:judgment"
    learning_lineage_id = f"{workspace_id}:learning"
    next_action = "create_workspace" if state_summary == "ready_for_workspace" else "clarify_intake"
    title = canonical.title or canonical.problem or canonical.issue_id
    subject = SubjectRef(
        subject_id=canonical.issue_id,
        subject_kind=subject_kind,
        subject_title=title,
        source_ref=(
            str(canonical.source_refs[0].get("ref", ""))
            if canonical.source_refs and isinstance(canonical.source_refs[0], dict)
            else ""
        ),
    )
    active_execution = ExecutionSession(
        execution_session_id=execution_session_id,
        run_id="",
        agent_id="",
        runtime_id="",
        phase="intake",
        health="pending",
        status_reason="waiting_for_execution",
        queue_state="pending",
        last_event_at="",
        available_actions=[next_action],
    )
    active_judgment = Judgment(
        judgment_id=judgment_id,
        workspace_id=workspace_id,
        base_run_mode="recon",
        graph_profile="intake_handoff",
        risk_posture="pending",
        judgment_class=AcceptanceJudgmentClass.OBSERVATION.value,
        review_state="pending",
        confidence=0.0,
        impact_if_true="",
        repro_status="not_run",
        recommended_next_step=(
            "Start execution to collect evidence."
            if state_summary == "ready_for_workspace"
            else "Complete intake and unblock workspace creation."
        ),
        summary="Judgment pending until execution evidence exists.",
    )
    learning_lineage = LearningLineage(
        learning_lineage_id=learning_lineage_id,
        workspace_id=workspace_id,
        status="pending",
    )
    return Workspace(
        workspace_id=workspace_id,
        workspace_kind=workspace_kind,
        workspace_title=title,
        subject_id=canonical.issue_id,
        subject_kind=subject_kind,
        source_system=canonical.origin or "unknown",
        state_summary=state_summary,
        created_at=timestamp,
        updated_at=timestamp,
        active_execution_session_id=execution_session_id,
        active_judgment_id=judgment_id,
        learning_timeline_id=learning_lineage_id,
        subject=subject,
        active_execution=active_execution,
        active_judgment=active_judgment,
        learning_lineage=learning_lineage,
    )


def execution_session_from_attempt(
    attempt: ExecutionAttempt,
    *,
    workspace_id: str,
    agent_id: str = "",
    runtime_id: str = "",
) -> ExecutionSession:
    phase = {
        ExecutionAttemptState.CREATED: "created",
        ExecutionAttemptState.RUNNING: "running",
        ExecutionAttemptState.COMPLETED: "completed",
        ExecutionAttemptState.CANCELLED: "cancelled",
    }[attempt.attempt_state]
    queue_state = {
        ExecutionAttemptState.CREATED: "pending",
        ExecutionAttemptState.RUNNING: "running",
        ExecutionAttemptState.COMPLETED: "completed",
        ExecutionAttemptState.CANCELLED: "cancelled",
    }[attempt.attempt_state]
    if attempt.attempt_state is ExecutionAttemptState.RUNNING:
        health = "active"
    else:
        health = {
            ExecutionStatus.SUCCEEDED: "healthy",
            ExecutionStatus.FAILED: "failed",
            ExecutionStatus.PARTIAL: "degraded",
            ExecutionStatus.BLOCKED: "blocked",
        }[attempt.outcome.status]
    available_actions: list[str]
    if health in {"failed", "blocked", "degraded"}:
        available_actions = ["retry", "takeover"]
    elif attempt.attempt_state is ExecutionAttemptState.RUNNING:
        available_actions = ["cancel", "takeover"]
    elif attempt.attempt_state is ExecutionAttemptState.CREATED:
        available_actions = ["cancel"]
    else:
        available_actions = []
    return ExecutionSession(
        execution_session_id=f"{workspace_id}:{attempt.attempt_id}",
        run_id=attempt.continuity_id or attempt.attempt_id,
        agent_id=agent_id,
        runtime_id=runtime_id,
        phase=phase,
        health=health,
        status_reason=attempt.outcome.status.value,
        queue_state=queue_state,
        last_event_at=attempt.completed_at or attempt.started_at or "",
        available_actions=available_actions,
    )


def execution_session_from_runtime_chain_status(
    status: RuntimeChainStatus,
    *,
    workspace_id: str,
    agent_id: str = "",
    runtime_id: str = "",
) -> ExecutionSession:
    phase = status.phase.value
    if status.phase in {ChainPhase.STARTED, ChainPhase.HEARTBEAT}:
        health = "active"
        queue_state = "running"
        available_actions = ["cancel", "takeover"]
    elif status.phase is ChainPhase.COMPLETED:
        health = "healthy"
        queue_state = "finished"
        available_actions = []
    elif status.phase is ChainPhase.DEGRADED:
        health = "degraded"
        queue_state = "running"
        available_actions = ["retry", "takeover"]
    else:
        health = "failed"
        queue_state = "failed"
        available_actions = ["retry", "takeover"]
    return ExecutionSession(
        execution_session_id=status.active_span_id or f"{workspace_id}:{status.chain_id}",
        run_id=status.chain_id,
        agent_id=agent_id or str(status.session_refs.get("agent_id") or ""),
        runtime_id=runtime_id or str(status.session_refs.get("runtime_id") or ""),
        phase=phase,
        health=health,
        status_reason=status.status_reason,
        queue_state=queue_state,
        last_event_at=status.updated_at,
        available_actions=available_actions,
    )


def evidence_bundle_from_attempt(
    attempt: ExecutionAttempt,
    *,
    workspace_id: str,
    bundle_kind: str = "execution_artifacts",
) -> EvidenceBundle:
    artifact_refs = [
        ArtifactEnvelope(
            artifact_key=artifact.key,
            producer_kind=artifact.producer_kind,
            carrier_kind=artifact.carrier_kind.value,
            subject_kind=artifact.subject_kind.value,
            scope=artifact.scope.value,
            path=artifact.path,
        )
        for artifact in attempt.outcome.artifacts.values()
        if artifact is not None
    ]
    return EvidenceBundle(
        evidence_bundle_id=f"{workspace_id}:{attempt.attempt_id}:evidence",
        workspace_id=workspace_id,
        origin_run_id=attempt.continuity_id or attempt.attempt_id,
        bundle_kind=bundle_kind,
        artifact_refs=artifact_refs,
        route_refs=[],
        step_refs=[],
        evidence_summary=(
            f"{len(artifact_refs)} artifacts captured "
            f"for {attempt.unit_kind.value} {attempt.unit_id}."
        ),
        collected_at=attempt.completed_at or attempt.started_at or _now_iso(),
    )


def judgment_from_acceptance_judgment(
    acceptance_judgment: AcceptanceJudgment,
    *,
    workspace_id: str,
) -> Judgment:
    candidate = None
    observation = None
    impact_if_true = ""
    repro_status = ""
    recommended_next_step = ""
    graph_profile = ""
    if acceptance_judgment.candidate is not None:
        source = acceptance_judgment.candidate
        candidate = CandidateFinding(
            finding_id=source.finding_id,
            claim=source.claim,
            surface=source.surface,
            route=source.route,
            evidence_refs=list(source.evidence_refs),
            confidence=source.confidence,
            impact_if_true=source.impact_if_true,
            repro_status=source.repro_status,
            hold_reason=source.hold_reason,
            promotion_test=source.promotion_test,
            recommended_next_step=source.recommended_next_step,
            dedupe_key=source.dedupe_key,
            critique_axis=source.critique_axis,
            operator_task=source.operator_task,
            why_it_matters=source.why_it_matters,
            baseline_ref=source.baseline_ref,
            origin_step=source.origin_step,
            graph_profile=source.graph_profile,
            compare_overlay=source.compare_overlay,
            source_observation_id=source.source_observation_id,
            reviewer_identity=source.reviewer_identity,
            review_note=source.review_note,
            dismissal_reason=source.dismissal_reason,
            superseded_by=source.superseded_by,
        )
        impact_if_true = source.impact_if_true
        repro_status = source.repro_status
        recommended_next_step = source.recommended_next_step
        graph_profile = source.graph_profile
    if acceptance_judgment.observation is not None:
        source = acceptance_judgment.observation
        observation = Observation(
            summary=source.summary,
            route=source.route,
            details=source.details,
            evidence_refs=list(source.evidence_refs),
            critique_axis=source.critique_axis,
            operator_task=source.operator_task,
            why_it_matters=source.why_it_matters,
        )
        if not impact_if_true:
            impact_if_true = source.why_it_matters
        if not recommended_next_step:
            recommended_next_step = source.operator_task
    risk_posture = {
        AcceptanceJudgmentClass.CONFIRMED_ISSUE: "high",
        AcceptanceJudgmentClass.CANDIDATE_FINDING: "medium",
        AcceptanceJudgmentClass.OBSERVATION: "low",
    }[acceptance_judgment.judgment_class]
    return Judgment(
        judgment_id=acceptance_judgment.judgment_id,
        workspace_id=workspace_id,
        base_run_mode=acceptance_judgment.run_mode.value,
        graph_profile=graph_profile,
        risk_posture=risk_posture,
        judgment_class=acceptance_judgment.judgment_class.value,
        review_state=acceptance_judgment.workflow_state.value,
        confidence=acceptance_judgment.confidence,
        impact_if_true=impact_if_true,
        repro_status=repro_status,
        recommended_next_step=recommended_next_step,
        summary=acceptance_judgment.summary,
        candidate_finding=candidate,
        observation=observation,
    )


def _judgment_from_payload(payload: dict[str, Any], *, workspace_id: str) -> Judgment:
    candidate_payload = payload.get("candidate_finding")
    observation_payload = payload.get("observation")
    candidate = None
    if isinstance(candidate_payload, dict):
        candidate = CandidateFinding(
            finding_id=str(candidate_payload.get("finding_id", "")),
            claim=str(candidate_payload.get("claim", "")),
            surface=str(candidate_payload.get("surface", "")),
            route=str(candidate_payload.get("route", "")),
            evidence_refs=[str(item) for item in candidate_payload.get("evidence_refs", [])],
            confidence=float(candidate_payload.get("confidence", 0.0) or 0.0),
            impact_if_true=str(candidate_payload.get("impact_if_true", "")),
            repro_status=str(candidate_payload.get("repro_status", "")),
            hold_reason=str(candidate_payload.get("hold_reason", "")),
            promotion_test=str(candidate_payload.get("promotion_test", "")),
            recommended_next_step=str(candidate_payload.get("recommended_next_step", "")),
            dedupe_key=str(candidate_payload.get("dedupe_key", "")),
            critique_axis=str(candidate_payload.get("critique_axis", "")),
            operator_task=str(candidate_payload.get("operator_task", "")),
            why_it_matters=str(candidate_payload.get("why_it_matters", "")),
            baseline_ref=str(candidate_payload.get("baseline_ref", "")),
            origin_step=str(candidate_payload.get("origin_step", "")),
            graph_profile=str(candidate_payload.get("graph_profile", "")),
            compare_overlay=bool(candidate_payload.get("compare_overlay", False)),
            source_observation_id=str(candidate_payload.get("source_observation_id", "")),
            reviewer_identity=str(candidate_payload.get("reviewer_identity", "")),
            review_note=str(candidate_payload.get("review_note", "")),
            dismissal_reason=str(candidate_payload.get("dismissal_reason", "")),
            superseded_by=str(candidate_payload.get("superseded_by", "")),
        )
    observation = None
    if isinstance(observation_payload, dict):
        observation = Observation(
            summary=str(observation_payload.get("summary", "")),
            route=str(observation_payload.get("route", "")),
            details=str(observation_payload.get("details", "")),
            evidence_refs=[str(item) for item in observation_payload.get("evidence_refs", [])],
            critique_axis=str(observation_payload.get("critique_axis", "")),
            operator_task=str(observation_payload.get("operator_task", "")),
            why_it_matters=str(observation_payload.get("why_it_matters", "")),
        )
    return Judgment(
        judgment_id=str(payload.get("judgment_id", f"{workspace_id}:judgment")),
        workspace_id=workspace_id,
        base_run_mode=str(payload.get("base_run_mode", "recon")),
        graph_profile=str(payload.get("graph_profile", "")),
        risk_posture=str(payload.get("risk_posture", "pending")),
        judgment_class=str(payload.get("judgment_class", "observation")),
        review_state=str(payload.get("review_state", "pending")),
        confidence=float(payload.get("confidence", 0.0) or 0.0),
        impact_if_true=str(payload.get("impact_if_true", "")),
        repro_status=str(payload.get("repro_status", "")),
        recommended_next_step=str(payload.get("recommended_next_step", "")),
        summary=str(payload.get("summary", "")),
        candidate_finding=candidate,
        observation=observation,
    )


def workspace_from_mission_runtime(
    *,
    mission_id: str,
    mission_title: str,
    runtime_status: RuntimeChainStatus | None = None,
    latest_judgment: Judgment | dict[str, Any] | None = None,
    source_system: str = "spec_orch",
) -> Workspace:
    timestamp = _now_iso()
    if runtime_status is not None:
        active_execution = execution_session_from_runtime_chain_status(
            runtime_status,
            workspace_id=mission_id,
        )
        updated_at = runtime_status.updated_at or timestamp
        state_summary = runtime_status.phase.value
    else:
        active_execution = ExecutionSession(
            execution_session_id=f"{mission_id}:execution",
            run_id="",
            agent_id="",
            runtime_id="",
            phase="pending",
            health="pending",
            status_reason="waiting_for_runtime",
            queue_state="pending",
            last_event_at="",
            available_actions=[],
        )
        updated_at = timestamp
        state_summary = "pending"

    if isinstance(latest_judgment, dict):
        active_judgment = _judgment_from_payload(latest_judgment, workspace_id=mission_id)
    elif latest_judgment is not None:
        active_judgment = Judgment(
            judgment_id=latest_judgment.judgment_id,
            workspace_id=mission_id,
            base_run_mode=latest_judgment.base_run_mode,
            graph_profile=latest_judgment.graph_profile,
            risk_posture=latest_judgment.risk_posture,
            judgment_class=latest_judgment.judgment_class,
            review_state=latest_judgment.review_state,
            confidence=latest_judgment.confidence,
            impact_if_true=latest_judgment.impact_if_true,
            repro_status=latest_judgment.repro_status,
            recommended_next_step=latest_judgment.recommended_next_step,
            summary=latest_judgment.summary,
            candidate_finding=latest_judgment.candidate_finding,
            observation=latest_judgment.observation,
        )
    else:
        active_judgment = Judgment(
            judgment_id=f"{mission_id}:judgment",
            workspace_id=mission_id,
            base_run_mode="recon",
            graph_profile="",
            risk_posture="pending",
            judgment_class=AcceptanceJudgmentClass.OBSERVATION.value,
            review_state="pending",
            confidence=0.0,
            impact_if_true="",
            repro_status="not_run",
            recommended_next_step="Run acceptance to collect evidence.",
            summary="Judgment pending until acceptance evidence exists.",
        )

    learning_lineage = LearningLineage(
        learning_lineage_id=f"{mission_id}:learning",
        workspace_id=mission_id,
        status="pending",
    )
    return Workspace(
        workspace_id=mission_id,
        workspace_kind="mission",
        workspace_title=mission_title,
        subject_id=mission_id,
        subject_kind="mission",
        source_system=source_system,
        state_summary=state_summary,
        created_at=timestamp,
        updated_at=updated_at,
        active_execution_session_id=active_execution.execution_session_id,
        active_judgment_id=active_judgment.judgment_id,
        learning_timeline_id=learning_lineage.learning_lineage_id,
        subject=SubjectRef(
            subject_id=mission_id,
            subject_kind="mission",
            subject_title=mission_title,
            source_ref=mission_id,
        ),
        active_execution=active_execution,
        active_judgment=active_judgment,
        learning_lineage=learning_lineage,
    )


def evidence_bundle_from_acceptance_review(
    review: AcceptanceReviewResult,
    *,
    workspace_id: str,
    round_id: int,
    artifact_path: str,
) -> EvidenceBundle:
    artifacts = review.artifacts if isinstance(review.artifacts, dict) else {}
    artifact_refs: list[ArtifactEnvelope] = []

    def _carrier_kind(path: str) -> str:
        lowered = path.lower()
        if lowered.endswith(".json"):
            return "json"
        if lowered.endswith(".jsonl"):
            return "jsonl"
        if lowered.endswith(".md"):
            return "markdown"
        if lowered.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg")):
            return "image"
        if lowered.endswith("/"):
            return "directory"
        return "artifact"

    seen_paths: set[str] = set()
    acceptance_review_path = str(artifacts.get("acceptance_review") or artifact_path).strip()
    if acceptance_review_path:
        seen_paths.add(acceptance_review_path)
        artifact_refs.append(
            ArtifactEnvelope(
                artifact_key="acceptance_review",
                producer_kind="acceptance_evaluator",
                carrier_kind=_carrier_kind(acceptance_review_path),
                subject_kind="mission",
                scope="leaf",
                path=acceptance_review_path,
            )
        )
    for key, value in artifacts.items():
        if not isinstance(value, str) or not value.strip() or value.strip() in seen_paths:
            continue
        seen_paths.add(value.strip())
        artifact_refs.append(
            ArtifactEnvelope(
                artifact_key=str(key),
                producer_kind="acceptance_graph" if "graph" in str(key) else "acceptance_evaluator",
                carrier_kind=_carrier_kind(value.strip()),
                subject_kind="mission",
                scope="leaf",
                path=value.strip(),
            )
        )
    route_refs: list[str] = []
    if review.campaign is not None:
        route_refs.extend(str(item) for item in review.campaign.primary_routes if str(item).strip())
        route_refs.extend(str(item) for item in review.campaign.related_routes if str(item).strip())
    step_refs = [
        str(item)
        for item in artifacts.get("step_artifacts", [])
        if isinstance(item, str) and item.strip()
    ]
    route_refs = list(dict.fromkeys(route_refs))
    return EvidenceBundle(
        evidence_bundle_id=f"{workspace_id}:round-{round_id:02d}:evidence",
        workspace_id=workspace_id,
        origin_run_id=f"{workspace_id}:round-{round_id:02d}",
        bundle_kind="acceptance_review",
        artifact_refs=artifact_refs,
        route_refs=route_refs,
        step_refs=step_refs,
        evidence_summary=(
            f"{review.coverage_status or 'unscoped'} coverage across "
            f"{len(route_refs)} routes and {len(step_refs)} step artifacts."
        ),
        collected_at="",
    )


def compare_overlay_from_acceptance_review(
    review: AcceptanceReviewResult,
    *,
    workspace_id: str,
    judgments: list[Judgment],
) -> CompareOverlay:
    artifacts = review.artifacts if isinstance(review.artifacts, dict) else {}
    candidate_baselines = [
        judgment.candidate_finding.baseline_ref
        for judgment in judgments
        if judgment.candidate_finding is not None and judgment.candidate_finding.baseline_ref
    ]
    baseline_ref = str(
        artifacts.get("baseline_ref")
        or (candidate_baselines[0] if candidate_baselines else "")
    ).strip()
    compare_active = bool(artifacts.get("compare_overlay")) or any(
        judgment.candidate_finding is not None and judgment.candidate_finding.compare_overlay
        for judgment in judgments
    )
    step_artifacts = [
        str(item)
        for item in artifacts.get("step_artifacts", [])
        if isinstance(item, str) and item.strip()
    ]
    compare_state = "active" if compare_active else "inactive"
    drift_summary = (
        f"Baseline compare active against {baseline_ref}."
        if compare_active and baseline_ref
        else "Compare overlay inactive."
    )
    judgment_drift_summary = (
        "Candidate findings were formed under compare overlay."
        if compare_active
        else "No compare drift applied."
    )
    return CompareOverlay(
        compare_overlay_id=f"{workspace_id}:compare",
        workspace_id=workspace_id,
        baseline_ref=baseline_ref,
        compare_state=compare_state,
        drift_summary=drift_summary,
        artifact_drift_refs=step_artifacts if compare_active else [],
        judgment_drift_summary=judgment_drift_summary,
    )


def surface_pack_from_acceptance_surface_pack(
    pack: AcceptanceSurfacePack,
    *,
    workspace_id: str,
    graph_profiles: list[str],
    baseline_refs: list[str],
) -> SurfacePack:
    return SurfacePack(
        surface_pack_id=f"{workspace_id}:{pack.pack_key}",
        workspace_id=workspace_id,
        surface_name="dashboard",
        active_axes=list(pack.critique_axes),
        known_routes=list(pack.seed_routes),
        graph_profiles=list(dict.fromkeys(item for item in graph_profiles if item)),
        baseline_refs=list(dict.fromkeys(item for item in baseline_refs if item)),
        pack_key=pack.pack_key,
        safe_action_budget=pack.safe_action_budget,
    )


def judgment_timeline_entries_for_review(
    *,
    workspace_id: str,
    round_id: int,
    review: AcceptanceReviewResult,
    judgments: list[Judgment],
    evidence_bundle: EvidenceBundle,
    compare_overlay: CompareOverlay,
) -> list[JudgmentTimelineEntry]:
    artifacts = review.artifacts if isinstance(review.artifacts, dict) else {}
    graph_profile = str(artifacts.get("graph_profile", "")).strip()
    first_judgment_id = (
        judgments[0].judgment_id
        if judgments
        else f"{workspace_id}:round-{round_id:02d}:judgment"
    )
    timeline: list[JudgmentTimelineEntry] = [
        JudgmentTimelineEntry(
            timeline_entry_id=f"{workspace_id}:round-{round_id:02d}:routing",
            workspace_id=workspace_id,
            judgment_id=first_judgment_id,
            event_type="routing_selected",
            event_summary=review.acceptance_mode or "recon",
            created_at="",
            artifact_refs=[],
        )
    ]
    if graph_profile:
        timeline.append(
            JudgmentTimelineEntry(
                timeline_entry_id=f"{workspace_id}:round-{round_id:02d}:graph",
                workspace_id=workspace_id,
                judgment_id=first_judgment_id,
                event_type="graph_profile_activated",
                event_summary=graph_profile,
                created_at="",
                artifact_refs=[
                    item.path
                    for item in evidence_bundle.artifact_refs
                    if item.artifact_key == "graph_run"
                ],
            )
        )
    timeline.append(
        JudgmentTimelineEntry(
            timeline_entry_id=f"{workspace_id}:round-{round_id:02d}:evidence",
            workspace_id=workspace_id,
            judgment_id=first_judgment_id,
            event_type="evidence_bundle_collected",
            event_summary=evidence_bundle.evidence_summary,
            created_at="",
            artifact_refs=[item.path for item in evidence_bundle.artifact_refs],
        )
    )
    timeline.append(
        JudgmentTimelineEntry(
            timeline_entry_id=f"{workspace_id}:round-{round_id:02d}:compare",
            workspace_id=workspace_id,
            judgment_id=first_judgment_id,
            event_type=(
                "compare_overlay_active"
                if compare_overlay.compare_state == "active"
                else "compare_overlay_inactive"
            ),
            event_summary=compare_overlay.compare_state,
            created_at="",
            artifact_refs=list(compare_overlay.artifact_drift_refs),
        )
    )
    if judgments:
        first = judgments[0]
        timeline.append(
            JudgmentTimelineEntry(
                timeline_entry_id=f"{workspace_id}:round-{round_id:02d}:judgment",
                workspace_id=workspace_id,
                judgment_id=first.judgment_id,
                event_type="judgment_assigned",
                event_summary=first.judgment_class,
                created_at="",
                artifact_refs=(
                    list(first.candidate_finding.evidence_refs)
                    if first.candidate_finding
                    else []
                ),
            )
        )
        timeline.append(
            JudgmentTimelineEntry(
                timeline_entry_id=f"{workspace_id}:round-{round_id:02d}:review-state",
                workspace_id=workspace_id,
                judgment_id=first.judgment_id,
                event_type="review_state_changed",
                event_summary=f"{first.review_state} {first.judgment_class}",
                created_at="",
                artifact_refs=[],
            )
        )
    return timeline


__all__ = [
    "evidence_bundle_from_attempt",
    "execution_session_from_attempt",
    "execution_session_from_runtime_chain_status",
    "evidence_bundle_from_acceptance_review",
    "compare_overlay_from_acceptance_review",
    "surface_pack_from_acceptance_surface_pack",
    "judgment_timeline_entries_for_review",
    "handoff_blockers_for_canonical_issue",
    "handoff_state_for_canonical_issue",
    "judgment_from_acceptance_judgment",
    "workspace_from_canonical_issue",
    "workspace_from_mission_runtime",
]
