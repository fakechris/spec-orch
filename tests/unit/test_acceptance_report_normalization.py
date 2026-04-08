"""Tests for acceptance report normalization (SON-355/356).

Validates that _reconcile_report_consistency() keeps top-level status/summary
in agreement with nested findings and issue_proposals.
"""

from __future__ import annotations

from spec_orch.domain.models import (
    AcceptanceFinding,
    AcceptanceIssueProposal,
    AcceptanceReviewResult,
)
from spec_orch.services.acceptance.litellm_acceptance_evaluator import (
    LiteLLMAcceptanceEvaluator,
)


def _make_result(
    *,
    status: str = "pass",
    summary: str = "All good.",
    confidence: float = 0.9,
    findings: list[AcceptanceFinding] | None = None,
    issue_proposals: list[AcceptanceIssueProposal] | None = None,
) -> AcceptanceReviewResult:
    return AcceptanceReviewResult(
        status=status,
        summary=summary,
        confidence=confidence,
        evaluator="test",
        findings=findings or [],
        issue_proposals=issue_proposals or [],
    )


class TestReconcileReportConsistency:
    """Test _reconcile_report_consistency ensures status/summary agree with findings."""

    def test_pass_status_with_no_findings_stays_pass(self) -> None:
        result = _make_result(status="pass", findings=[], issue_proposals=[])
        reconciled = LiteLLMAcceptanceEvaluator._reconcile_report_consistency(result)
        assert reconciled.status == "pass"
        assert reconciled.summary == "All good."

    def test_empty_findings_with_fail_status_corrected_to_warn(self) -> None:
        result = _make_result(status="fail", findings=[], issue_proposals=[])
        reconciled = LiteLLMAcceptanceEvaluator._reconcile_report_consistency(result)
        assert reconciled.status == "warn"

    def test_empty_findings_fail_status_gets_fallback_summary(self) -> None:
        result = _make_result(status="fail", summary="", findings=[], issue_proposals=[])
        reconciled = LiteLLMAcceptanceEvaluator._reconcile_report_consistency(result)
        assert reconciled.status == "warn"
        assert reconciled.summary == "No actionable findings."

    def test_high_severity_finding_upgrades_pass_to_warn(self) -> None:
        finding = AcceptanceFinding(
            severity="high",
            summary="Transcript evidence entry is hard to discover",
        )
        result = _make_result(status="pass", findings=[finding])
        reconciled = LiteLLMAcceptanceEvaluator._reconcile_report_consistency(result)
        assert reconciled.status == "warn"

    def test_critical_severity_finding_upgrades_pass_to_warn(self) -> None:
        finding = AcceptanceFinding(
            severity="critical",
            summary="Critical rendering failure",
        )
        result = _make_result(status="pass", findings=[finding])
        reconciled = LiteLLMAcceptanceEvaluator._reconcile_report_consistency(result)
        assert reconciled.status == "warn"

    def test_issue_proposals_upgrade_pass_to_warn(self) -> None:
        proposal = AcceptanceIssueProposal(
            title="Clarify transcript packet selection entry point",
            summary="Needs clearer affordance.",
            severity="medium",
        )
        result = _make_result(status="pass", issue_proposals=[proposal])
        reconciled = LiteLLMAcceptanceEvaluator._reconcile_report_consistency(result)
        assert reconciled.status == "warn"

    def test_warn_status_with_high_findings_stays_warn(self) -> None:
        finding = AcceptanceFinding(severity="high", summary="Something bad")
        result = _make_result(status="warn", findings=[finding])
        reconciled = LiteLLMAcceptanceEvaluator._reconcile_report_consistency(result)
        assert reconciled.status == "warn"

    def test_fail_status_with_findings_not_downgraded(self) -> None:
        finding = AcceptanceFinding(severity="high", summary="Something bad")
        result = _make_result(status="fail", findings=[finding])
        reconciled = LiteLLMAcceptanceEvaluator._reconcile_report_consistency(result)
        assert reconciled.status == "fail"

    def test_consistent_report_not_modified(self) -> None:
        """A warn report with high findings should pass through unchanged."""
        finding = AcceptanceFinding(severity="high", summary="Issue found")
        proposal = AcceptanceIssueProposal(title="Fix it", summary="Details.", severity="high")
        result = _make_result(
            status="warn",
            summary="Issues found.",
            confidence=0.75,
            findings=[finding],
            issue_proposals=[proposal],
        )
        reconciled = LiteLLMAcceptanceEvaluator._reconcile_report_consistency(result)
        assert reconciled.status == "warn"
        assert reconciled.summary == "Issues found."
        assert reconciled.confidence == 0.75

    def test_low_severity_findings_without_proposals_stays_pass(self) -> None:
        finding = AcceptanceFinding(severity="low", summary="Minor nit")
        result = _make_result(status="pass", findings=[finding], issue_proposals=[])
        reconciled = LiteLLMAcceptanceEvaluator._reconcile_report_consistency(result)
        assert reconciled.status == "pass"

    def test_medium_severity_findings_without_proposals_stays_pass(self) -> None:
        finding = AcceptanceFinding(severity="medium", summary="Moderate concern")
        result = _make_result(status="pass", findings=[finding], issue_proposals=[])
        reconciled = LiteLLMAcceptanceEvaluator._reconcile_report_consistency(result)
        assert reconciled.status == "pass"
