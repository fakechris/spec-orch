from __future__ import annotations


def test_candidate_finding_disposition_promotes_into_decision_review() -> None:
    from spec_orch.acceptance_core.disposition import (
        AcceptanceDisposition,
        build_acceptance_decision_review,
        disposition_decision,
    )
    from spec_orch.acceptance_core.models import (
        AcceptanceJudgment,
        AcceptanceJudgmentClass,
        AcceptanceRunMode,
        AcceptanceWorkflowState,
        CandidateFinding,
    )

    judgment = AcceptanceJudgment(
        judgment_id="judgment-1",
        judgment_class=AcceptanceJudgmentClass.CANDIDATE_FINDING,
        run_mode=AcceptanceRunMode.EXPLORE,
        workflow_state=AcceptanceWorkflowState.QUEUED,
        summary="Transcript entry point is not self-evident.",
        candidate=CandidateFinding(
            claim="Transcript entry point is not self-evident.",
            surface="mission_transcript",
            route="/?mission=demo&mode=missions&tab=transcript",
            evidence_refs=["rounds/round-01/acceptance_review.json"],
            confidence=0.62,
            impact_if_true="Operators may miss the first useful proof surface.",
            repro_status="credible",
            hold_reason="Needs operator confirmation before filing.",
            promotion_test="Confirmed by operator in a second review pass.",
            recommended_next_step="Queue for operator review.",
            dedupe_key="transcript-entrypoint",
        ),
    )

    disposition = disposition_decision(
        judgment,
        disposition=AcceptanceDisposition.PROMOTE,
        summary="Operator confirmed this should become tracked work.",
    )
    review = build_acceptance_decision_review(
        disposition,
        record_id="acceptance:judgment-1",
        reviewer_kind="acceptance",
    )

    assert disposition.workflow_state is AcceptanceWorkflowState.PROMOTED
    assert review.verdict == "acceptance_candidate_promoted"
    assert review.record_id == "acceptance:judgment-1"


def test_observation_archives_without_second_queue_ontology() -> None:
    from spec_orch.acceptance_core.disposition import AcceptanceDisposition, disposition_decision
    from spec_orch.acceptance_core.models import (
        AcceptanceJudgment,
        AcceptanceJudgmentClass,
        AcceptanceObservation,
        AcceptanceRunMode,
        AcceptanceWorkflowState,
    )

    judgment = AcceptanceJudgment(
        judgment_id="obs-1",
        judgment_class=AcceptanceJudgmentClass.OBSERVATION,
        run_mode=AcceptanceRunMode.RECON,
        workflow_state=AcceptanceWorkflowState.REVIEWED,
        summary="The route tree is more complex than expected.",
        observation=AcceptanceObservation(
            summary="The route tree is more complex than expected.",
            route="/settings",
        ),
    )

    disposition = disposition_decision(
        judgment,
        disposition=AcceptanceDisposition.ARCHIVE,
        summary="Keep as historical signal only.",
    )

    assert disposition.workflow_state is AcceptanceWorkflowState.ARCHIVED
    assert disposition.intervention_required is False


def test_disposition_can_apply_governance_metadata_to_candidate() -> None:
    from spec_orch.acceptance_core.disposition import (
        AcceptanceDisposition,
        apply_disposition_to_judgment,
        disposition_decision,
    )
    from spec_orch.acceptance_core.models import (
        AcceptanceJudgment,
        AcceptanceJudgmentClass,
        AcceptanceRunMode,
        AcceptanceWorkflowState,
        CandidateFinding,
    )

    judgment = AcceptanceJudgment(
        judgment_id="candidate-2",
        judgment_class=AcceptanceJudgmentClass.CANDIDATE_FINDING,
        run_mode=AcceptanceRunMode.EXPLORE,
        workflow_state=AcceptanceWorkflowState.REVIEWED,
        summary="Transcript entry point is not self-evident.",
        candidate=CandidateFinding(
            finding_id="candidate-2",
            claim="Transcript entry point is not self-evident.",
            route="/?mission=demo&mode=missions&tab=transcript",
            confidence=0.68,
            impact_if_true="Operators may miss the main proof surface.",
            repro_status="credible",
            hold_reason="Needs follow-up review.",
            promotion_test="Compare against known-good transcript baseline.",
            recommended_next_step="Operator review before filing.",
            dedupe_key="transcript-entrypoint",
        ),
    )

    decision = disposition_decision(
        judgment,
        disposition=AcceptanceDisposition.DISMISS,
        summary="Confirmed as noise after operator review.",
        reviewer_identity="operator:chris",
        review_note="Observed only once and contradicted by replay.",
        superseded_by="candidate-3",
    )
    updated = apply_disposition_to_judgment(judgment, decision)

    assert updated.workflow_state is AcceptanceWorkflowState.DISMISSED
    assert updated.candidate is not None
    assert updated.candidate.reviewer_identity == "operator:chris"
    assert updated.candidate.dismissal_reason == "Confirmed as noise after operator review."
    assert updated.candidate.superseded_by == "candidate-3"
