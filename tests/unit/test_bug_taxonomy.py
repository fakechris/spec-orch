"""Tests for acceptance bug taxonomy and triage routing (SON-357/358)."""

from __future__ import annotations

from spec_orch.domain.models import AcceptanceFinding, AcceptanceIssueProposal
from spec_orch.services.acceptance.bug_taxonomy import (
    BugType,
    classify_finding,
    classify_proposal,
    should_auto_file,
    triage_summary,
)


def _finding(summary: str, *, critique_axis: str = "", details: str = "") -> AcceptanceFinding:
    return AcceptanceFinding(
        severity="high", summary=summary, details=details, critique_axis=critique_axis
    )


def _proposal(title: str, summary: str = "", *, critique_axis: str = "") -> AcceptanceIssueProposal:
    return AcceptanceIssueProposal(
        title=title,
        summary=summary,
        severity="high",
        critique_axis=critique_axis,
    )


class TestClassifyFinding:
    def test_explicit_critique_axis(self) -> None:
        f = _finding("Some issue", critique_axis="harness_bug")
        assert classify_finding(f) == BugType.HARNESS_BUG

    def test_harness_signal_in_summary(self) -> None:
        f = _finding("Selector not found for login button")
        assert classify_finding(f) == BugType.HARNESS_BUG

    def test_n2n_signal_in_summary(self) -> None:
        f = _finding("500 error when submitting form")
        assert classify_finding(f) == BugType.N2N_BUG

    def test_ux_gap_signal(self) -> None:
        f = _finding("Confusing button label on dashboard")
        assert classify_finding(f) == BugType.UX_GAP

    def test_unknown_fallback(self) -> None:
        f = _finding("Minor visual glitch")
        assert classify_finding(f) == BugType.UNKNOWN

    def test_harness_priority_over_n2n(self) -> None:
        f = _finding("Timeout waiting for element after 500 error")
        assert classify_finding(f) == BugType.HARNESS_BUG

    def test_details_field_checked(self) -> None:
        f = _finding("Issue", details="playwright threw an error")
        assert classify_finding(f) == BugType.HARNESS_BUG


class TestClassifyProposal:
    def test_explicit_axis(self) -> None:
        p = _proposal("Fix it", critique_axis="n2n_bug")
        assert classify_proposal(p) == BugType.N2N_BUG

    def test_from_title(self) -> None:
        p = _proposal("Regression in payment flow")
        assert classify_proposal(p) == BugType.N2N_BUG


class TestShouldAutoFile:
    def test_harness_bug_not_filed(self) -> None:
        p = _proposal("Selector not found", critique_axis="harness_bug")
        should, reason = should_auto_file(p)
        assert not should
        assert "harness_bug" in reason

    def test_ux_gap_held_for_review(self) -> None:
        p = _proposal("Confusing affordance", critique_axis="ux_gap")
        should, reason = should_auto_file(p)
        assert not should
        assert "operator review" in reason

    def test_n2n_bug_eligible(self) -> None:
        p = _proposal("Data not saved", critique_axis="n2n_bug")
        should, reason = should_auto_file(p)
        assert should

    def test_unknown_eligible(self) -> None:
        p = _proposal("Something else")
        should, _ = should_auto_file(p)
        assert should


class TestTriageSummary:
    def test_mixed_findings(self) -> None:
        findings = [
            _finding("Timeout waiting for element"),
            _finding("500 error on save"),
            _finding("Confusing label"),
        ]
        proposals = [
            _proposal("Fix selector", critique_axis="harness_bug"),
            _proposal("Fix save bug", critique_axis="n2n_bug"),
        ]
        summary = triage_summary(findings, proposals)
        assert summary["finding_counts"]["harness_bug"] == 1
        assert summary["finding_counts"]["n2n_bug"] == 1
        assert summary["finding_counts"]["ux_gap"] == 1
        assert summary["harness_bugs_block_filing"] is True
        assert summary["auto_fileable_proposals"] == 1  # only n2n_bug

    def test_no_harness_bugs(self) -> None:
        findings = [_finding("Real issue", critique_axis="n2n_bug")]
        summary = triage_summary(findings, [])
        assert summary["harness_bugs_block_filing"] is False
