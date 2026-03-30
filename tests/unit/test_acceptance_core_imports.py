from __future__ import annotations


def test_acceptance_core_exports_canonical_primitives() -> None:
    from spec_orch.acceptance_core import (
        AcceptanceDisposition,
        AcceptanceDispositionDecision,
        AcceptanceJudgment,
        AcceptanceJudgmentClass,
        AcceptanceObservation,
        AcceptanceRequest,
        AcceptanceRoutingDecision,
        AcceptanceRunMode,
        AcceptanceSurfacePackRef,
        AcceptanceWorkflowState,
        CandidateFinding,
    )

    assert AcceptanceRunMode.VERIFY.value == "verify"
    assert AcceptanceJudgmentClass.CANDIDATE_FINDING.value == "candidate_finding"
    assert AcceptanceWorkflowState.QUEUED.value == "queued"
    assert CandidateFinding.__name__ == "CandidateFinding"
    assert AcceptanceObservation.__name__ == "AcceptanceObservation"
    assert AcceptanceJudgment.__name__ == "AcceptanceJudgment"
    assert AcceptanceRequest.__name__ == "AcceptanceRequest"
    assert AcceptanceRoutingDecision.__name__ == "AcceptanceRoutingDecision"
    assert AcceptanceSurfacePackRef.__name__ == "AcceptanceSurfacePackRef"
    assert AcceptanceDisposition.__name__ == "AcceptanceDisposition"
    assert AcceptanceDispositionDecision.__name__ == "AcceptanceDispositionDecision"
