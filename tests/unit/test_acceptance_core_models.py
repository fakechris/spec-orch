from __future__ import annotations

from spec_orch.domain.models import (
    AcceptanceFinding,
    AcceptanceIssueProposal,
    AcceptanceReviewResult,
)


def test_acceptance_core_ontology_values_match_judgment_model_doc() -> None:
    from spec_orch.acceptance_core.models import (
        AcceptanceJudgmentClass,
        AcceptanceRunMode,
        AcceptanceWorkflowState,
    )

    assert [item.value for item in AcceptanceRunMode] == ["verify", "replay", "explore", "recon"]
    assert [item.value for item in AcceptanceJudgmentClass] == [
        "confirmed_issue",
        "candidate_finding",
        "observation",
    ]
    assert [item.value for item in AcceptanceWorkflowState] == [
        "queued",
        "reviewed",
        "promoted",
        "dismissed",
        "archived",
    ]


def test_issue_proposal_with_hold_reason_normalizes_into_candidate_finding() -> None:
    from spec_orch.acceptance_core.models import (
        AcceptanceJudgmentClass,
        AcceptanceRunMode,
        build_acceptance_judgments,
    )

    result = AcceptanceReviewResult(
        status="warn",
        summary="Exploratory review found a likely UX concern.",
        confidence=0.71,
        evaluator="acceptance_llm",
        acceptance_mode="exploratory",
        issue_proposals=[
            AcceptanceIssueProposal(
                title="Clarify transcript entry point",
                summary="The transcript path is credible but needs operator review before filing.",
                severity="medium",
                route="/?mission=demo&mode=missions&tab=transcript",
                hold_reason="Needs operator confirmation before queueing UX work.",
                critique_axis="evidence_discoverability",
                operator_task="open packet-level transcript evidence",
                why_it_matters="Operators can stall before finding the right proof.",
                confidence=0.64,
            )
        ],
    )

    judgments = build_acceptance_judgments(result)

    assert len(judgments) == 1
    assert judgments[0].run_mode is AcceptanceRunMode.EXPLORE
    assert judgments[0].judgment_class is AcceptanceJudgmentClass.CANDIDATE_FINDING
    assert judgments[0].workflow_state.value == "queued"
    assert judgments[0].candidate is not None
    assert (
        judgments[0].candidate.hold_reason == "Needs operator confirmation before queueing UX work."
    )
    assert judgments[0].candidate.origin_step == "issue_proposal"
    assert judgments[0].candidate.run_mode == "explore"
    assert judgments[0].candidate.compare_overlay is False


def test_finding_without_issue_proposal_normalizes_into_observation() -> None:
    from spec_orch.acceptance_core.models import (
        AcceptanceJudgmentClass,
        AcceptanceRunMode,
        build_acceptance_judgments,
    )

    result = AcceptanceReviewResult(
        status="warn",
        summary="Review found descriptive signal only.",
        confidence=0.52,
        evaluator="acceptance_llm",
        acceptance_mode="impact_sweep",
        findings=[
            AcceptanceFinding(
                severity="medium",
                summary="The route tree is more complex than expected.",
                details="Need a dedicated rubric before queueing this as a trackable concern.",
                route="/settings",
            )
        ],
    )

    judgments = build_acceptance_judgments(result)

    assert len(judgments) == 1
    assert judgments[0].run_mode is AcceptanceRunMode.VERIFY
    assert judgments[0].judgment_class is AcceptanceJudgmentClass.OBSERVATION
    assert judgments[0].observation is not None
    assert judgments[0].observation.route == "/settings"


def test_candidate_finding_serializes_provenance_fields_from_review_sop() -> None:
    from spec_orch.acceptance_core.models import CandidateFinding

    candidate = CandidateFinding(
        finding_id="candidate-1",
        claim="Transcript empty state hides the retry cause.",
        surface="transcript",
        route="/?mission=demo&mode=missions&tab=transcript",
        evidence_refs=["browser_evidence.json", "step:transcript-empty-state"],
        confidence=0.72,
        impact_if_true="high",
        repro_status="suggestive_only",
        hold_reason="Operator-visible friction is credible but not yet reproducible.",
        promotion_test="rerun transcript path with retry artifact visible",
        recommended_next_step="Run targeted compare replay before filing",
        dedupe_key="dashboard:transcript_empty_state_retry_cause",
        baseline_ref="fixture:dashboard-transcript-empty-state",
        origin_step="transcript_empty_state_review",
        graph_profile="tuned_dashboard_compare_graph",
        run_mode="explore",
        compare_overlay=True,
    )

    payload = candidate.to_dict()

    assert payload["finding_id"] == "candidate-1"
    assert payload["baseline_ref"] == "fixture:dashboard-transcript-empty-state"
    assert payload["origin_step"] == "transcript_empty_state_review"
    assert payload["graph_profile"] == "tuned_dashboard_compare_graph"
    assert payload["run_mode"] == "explore"
    assert payload["compare_overlay"] is True
