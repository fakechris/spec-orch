from __future__ import annotations

from spec_orch.acceptance_core.models import (
    AcceptanceJudgment,
    AcceptanceJudgmentClass,
    AcceptanceRunMode,
    AcceptanceWorkflowState,
    CandidateFinding,
)
from spec_orch.domain.execution_semantics import (
    ArtifactCarrierKind,
    ArtifactRef,
    ArtifactScope,
    ContinuityKind,
    ExecutionAttempt,
    ExecutionAttemptState,
    ExecutionOutcome,
    ExecutionOwnerKind,
    ExecutionStatus,
    ExecutionUnitKind,
    SubjectKind,
)
from spec_orch.domain.intake_models import CanonicalAcceptance, CanonicalIssue
from spec_orch.runtime_chain.models import ChainPhase, RuntimeChainStatus, RuntimeSubjectKind


def test_workspace_from_canonical_issue_builds_shared_operator_contract() -> None:
    from spec_orch.services.operator_semantics import workspace_from_canonical_issue

    workspace = workspace_from_canonical_issue(
        CanonicalIssue(
            issue_id="SON-370",
            title="Shared operator semantics",
            problem="Execution, judgment, and learning need one operator vocabulary.",
            goal="Expose one stable workspace contract across the workbench.",
            constraints=["Do not collapse runtime ownership into SON-370."],
            acceptance=CanonicalAcceptance(
                success_conditions=["Operators can inspect a canonical workspace object."],
                verification_expectations=[
                    "Dashboard handoff shows execution and judgment placeholders."
                ],
            ),
            evidence_expectations=["workspace preview"],
            open_questions=[],
            current_plan_hint="Ship a shared seam before runtime cutover.",
            origin="dashboard",
            source_refs=[{"kind": "dashboard_draft", "ref": "SON-370"}],
        ),
        subject_kind="mission",
    )

    payload = workspace.to_dict()

    assert payload["workspace_id"] == "SON-370"
    assert payload["workspace_kind"] == "mission"
    assert payload["source_system"] == "dashboard"
    assert payload["subject"]["subject_kind"] == "mission"
    assert payload["active_execution"]["phase"] == "intake"
    assert payload["active_execution"]["health"] == "pending"
    assert payload["active_judgment"]["review_state"] == "pending"
    assert payload["learning_lineage"]["learning_lineage_id"] == "SON-370:learning"


def test_execution_session_from_attempt_normalizes_execution_status() -> None:
    from spec_orch.services.operator_semantics import execution_session_from_attempt

    attempt = ExecutionAttempt(
        attempt_id="attempt-1",
        unit_kind=ExecutionUnitKind.ISSUE,
        unit_id="SON-370",
        owner_kind=ExecutionOwnerKind.RUN_CONTROLLER,
        continuity_kind=ContinuityKind.FILE_BACKED_RUN,
        continuity_id="run-1",
        workspace_root="/tmp/workspace",
        attempt_state=ExecutionAttemptState.COMPLETED,
        started_at="2026-04-02T10:00:00+00:00",
        completed_at="2026-04-02T10:05:00+00:00",
        outcome=ExecutionOutcome(
            unit_kind=ExecutionUnitKind.ISSUE,
            owner_kind=ExecutionOwnerKind.RUN_CONTROLLER,
            status=ExecutionStatus.BLOCKED,
            build={"adapter": "codex"},
            artifacts={},
        ),
    )

    session = execution_session_from_attempt(
        attempt,
        workspace_id="SON-370",
        agent_id="planner",
        runtime_id="runtime-local",
    )

    assert session.phase == "completed"
    assert session.health == "blocked"
    assert session.queue_state == "completed"
    assert session.available_actions == ["retry", "takeover"]
    assert session.last_event_at == "2026-04-02T10:05:00+00:00"


def test_evidence_bundle_from_attempt_carries_artifact_envelopes() -> None:
    from spec_orch.services.operator_semantics import evidence_bundle_from_attempt

    attempt = ExecutionAttempt(
        attempt_id="attempt-2",
        unit_kind=ExecutionUnitKind.ISSUE,
        unit_id="SON-370",
        owner_kind=ExecutionOwnerKind.RUN_CONTROLLER,
        continuity_kind=ContinuityKind.FILE_BACKED_RUN,
        continuity_id="run-2",
        workspace_root="/tmp/workspace",
        attempt_state=ExecutionAttemptState.COMPLETED,
        outcome=ExecutionOutcome(
            unit_kind=ExecutionUnitKind.ISSUE,
            owner_kind=ExecutionOwnerKind.RUN_CONTROLLER,
            status=ExecutionStatus.SUCCEEDED,
            build={"adapter": "codex"},
            artifacts={
                "acceptance_review": ArtifactRef(
                    key="acceptance_review",
                    scope=ArtifactScope.LEAF,
                    producer_kind="acceptance_evaluator",
                    subject_kind=SubjectKind.ISSUE,
                    carrier_kind=ArtifactCarrierKind.JSON,
                    path="docs/specs/SON-370/acceptance_review.json",
                )
            },
        ),
    )

    bundle = evidence_bundle_from_attempt(attempt, workspace_id="SON-370")
    payload = bundle.to_dict()

    assert payload["origin_run_id"] == "run-2"
    assert payload["bundle_kind"] == "execution_artifacts"
    assert payload["artifact_refs"][0]["artifact_key"] == "acceptance_review"
    assert payload["artifact_refs"][0]["producer_kind"] == "acceptance_evaluator"


def test_judgment_from_acceptance_judgment_preserves_candidate_semantics() -> None:
    from spec_orch.services.operator_semantics import judgment_from_acceptance_judgment

    judgment = judgment_from_acceptance_judgment(
        AcceptanceJudgment(
            judgment_id="judgment-1",
            judgment_class=AcceptanceJudgmentClass.CANDIDATE_FINDING,
            run_mode=AcceptanceRunMode.EXPLORE,
            workflow_state=AcceptanceWorkflowState.QUEUED,
            summary="Candidate finding on transcript continuity.",
            confidence=0.82,
            candidate=CandidateFinding(
                finding_id="candidate-1",
                claim="Transcript continuity is not self-evident.",
                surface="transcript",
                route="/?mission=demo&tab=transcript",
                evidence_refs=["acceptance_review.json"],
                impact_if_true="Operators may miss the regression.",
                repro_status="credible",
                hold_reason="Need rerun with compare enabled.",
                promotion_test="Replay transcript with compare overlay.",
                recommended_next_step="Run compare replay.",
                graph_profile="dashboard_compare_v1",
            ),
        ),
        workspace_id="workspace-1",
    )

    payload = judgment.to_dict()

    assert payload["workspace_id"] == "workspace-1"
    assert payload["base_run_mode"] == "explore"
    assert payload["judgment_class"] == "candidate_finding"
    assert payload["review_state"] == "queued"
    assert payload["impact_if_true"] == "Operators may miss the regression."
    assert payload["recommended_next_step"] == "Run compare replay."
    assert payload["candidate_finding"]["claim"] == "Transcript continuity is not self-evident."


def test_workspace_from_mission_runtime_uses_runtime_chain_and_latest_judgment() -> None:
    from spec_orch.services.operator_semantics import (
        execution_session_from_runtime_chain_status,
        judgment_from_acceptance_judgment,
        workspace_from_mission_runtime,
    )

    chain_status = RuntimeChainStatus(
        chain_id="chain-mission-1",
        active_span_id="chain-mission-1:acceptance",
        subject_kind=RuntimeSubjectKind.ACCEPTANCE,
        subject_id="mission-1",
        phase=ChainPhase.HEARTBEAT,
        status_reason="acceptance_waiting_on_model",
        updated_at="2026-04-02T15:00:00+00:00",
    )
    execution_session_from_runtime_chain_status(
        chain_status,
        workspace_id="mission-1",
    )
    active_judgment = judgment_from_acceptance_judgment(
        AcceptanceJudgment(
            judgment_id="judgment-mission-1",
            judgment_class=AcceptanceJudgmentClass.CANDIDATE_FINDING,
            run_mode=AcceptanceRunMode.EXPLORE,
            workflow_state=AcceptanceWorkflowState.QUEUED,
            summary="Acceptance is waiting on stronger transcript evidence.",
            confidence=0.73,
            candidate=CandidateFinding(
                finding_id="candidate-mission-1",
                claim="Transcript evidence is incomplete.",
                surface="transcript",
                route="/?mission=mission-1&tab=transcript",
                evidence_refs=["acceptance_review.json"],
                impact_if_true="Operators cannot verify continuity.",
                repro_status="credible",
                hold_reason="Need replay evidence.",
                promotion_test="Rerun transcript review with compare.",
                recommended_next_step="Collect replay evidence.",
                graph_profile="dashboard_compare_v1",
            ),
        ),
        workspace_id="mission-1",
    )

    workspace = workspace_from_mission_runtime(
        mission_id="mission-1",
        mission_title="Mission One",
        runtime_status=chain_status,
        latest_judgment=active_judgment,
    )

    payload = workspace.to_dict()
    assert payload["workspace_id"] == "mission-1"
    assert payload["workspace_title"] == "Mission One"
    assert payload["active_execution"]["phase"] == "heartbeat"
    assert payload["active_execution"]["health"] == "active"
    assert payload["active_execution"]["status_reason"] == "acceptance_waiting_on_model"
    assert payload["active_judgment"]["judgment_id"] == "judgment-mission-1"
    assert payload["active_judgment"]["recommended_next_step"] == "Collect replay evidence."


def test_execution_substrate_models_serialize_operator_facing_fields() -> None:
    from spec_orch.domain.operator_semantics import (
        ActiveWork,
        Agent,
        OperatorIntervention,
        QueueEntry,
        Runtime,
    )

    agent = Agent(
        agent_id="acceptance_evaluator",
        name="Acceptance Evaluator",
        role="acceptance",
        status="active",
        runtime_id="runtime:local",
        active_workspace_id="mission-1",
        last_active_at="2026-04-02T16:00:00+00:00",
        recent_subject_refs=["mission:mission-1"],
    )
    runtime = Runtime(
        runtime_id="runtime:local",
        runtime_kind="local",
        mode="interactive",
        health="healthy",
        heartbeat_at="2026-04-02T16:00:00+00:00",
        usage_summary={"active_sessions": 1},
        activity_summary={"active_workspace_ids": ["mission-1"]},
        degradation_flags=[],
    )
    active_work = ActiveWork(
        active_work_id="mission-1:acceptance",
        workspace_id="mission-1",
        subject_id="mission-1",
        subject_kind="mission",
        agent_id="acceptance_evaluator",
        runtime_id="runtime:local",
        phase="heartbeat",
        health="active",
        status_reason="acceptance_waiting_on_model",
        started_at="2026-04-02T15:59:00+00:00",
        updated_at="2026-04-02T16:00:00+00:00",
        available_actions=["cancel", "takeover"],
    )
    queue_entry = QueueEntry(
        queue_entry_id="queue:mission-1",
        workspace_id="mission-1",
        subject_id="mission-1",
        queue_name="runtime",
        position=1,
        queue_state="queued",
        claimed_by_agent_id="",
        claimed_at="",
    )
    intervention = OperatorIntervention(
        intervention_id="intervention-1",
        workspace_id="mission-1",
        action="retry",
        requested_by="operator",
        requested_at="2026-04-02T16:01:00+00:00",
        outcome="pending",
        outcome_reason="",
        audit_refs=[],
    )

    assert agent.to_dict()["agent_id"] == "acceptance_evaluator"
    assert runtime.to_dict()["runtime_kind"] == "local"
    assert active_work.to_dict()["phase"] == "heartbeat"
    assert queue_entry.to_dict()["queue_state"] == "queued"
    assert intervention.to_dict()["action"] == "retry"


def test_judgment_side_models_serialize_compare_and_timeline_fields() -> None:
    from spec_orch.domain.operator_semantics import (
        CompareOverlay,
        JudgmentTimelineEntry,
        SurfacePack,
    )

    compare = CompareOverlay(
        compare_overlay_id="mission-1:compare",
        workspace_id="mission-1",
        baseline_ref="fixture:dashboard-transcript-regression",
        compare_state="active",
        drift_summary="Baseline compare active.",
        artifact_drift_refs=["steps/02-compare_replay.json"],
        judgment_drift_summary="Candidate findings were formed under compare overlay.",
    )
    timeline = JudgmentTimelineEntry(
        timeline_entry_id="mission-1:round-01:judgment",
        workspace_id="mission-1",
        judgment_id="judgment-1",
        event_type="judgment_assigned",
        event_summary="candidate_finding",
        created_at="2026-04-02T18:00:00+00:00",
        artifact_refs=["acceptance_review.json"],
    )
    surface_pack = SurfacePack(
        surface_pack_id="mission-1:dashboard_surface_pack_v1",
        workspace_id="mission-1",
        surface_name="dashboard",
        active_axes=["task_continuity"],
        known_routes=["/"],
        graph_profiles=["tuned_dashboard_compare_graph"],
        baseline_refs=["fixture:dashboard-transcript-regression"],
        pack_key="dashboard_surface_pack_v1",
        safe_action_budget="bounded",
    )

    assert compare.to_dict()["compare_state"] == "active"
    assert timeline.to_dict()["event_type"] == "judgment_assigned"
    assert surface_pack.to_dict()["pack_key"] == "dashboard_surface_pack_v1"
