"""Acceptance bug taxonomy and triage routing (SON-357/358).

Classifies acceptance findings into three categories:

- **harness_bug**: Test infrastructure failures (selectors, timeouts, env).
  Fix immediately — these pollute signal.
- **n2n_bug**: Real product bugs caught by acceptance (broken flows, errors).
  File as issues and route to engineering.
- **ux_gap**: UX/design concerns (confusing labels, poor affordance).
  Hold for operator review — not auto-filed.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from spec_orch.domain.models import AcceptanceFinding, AcceptanceIssueProposal


class BugType(StrEnum):
    """Canonical bug type classification for acceptance findings."""

    HARNESS_BUG = "harness_bug"
    N2N_BUG = "n2n_bug"
    UX_GAP = "ux_gap"
    UNKNOWN = "unknown"


# Signals that indicate the finding is about test infrastructure, not the product.
_HARNESS_SIGNALS = frozenset(
    {
        "selector not found",
        "timeout waiting",
        "element not visible",
        "navigation timeout",
        "playwright",
        "browser error",
        "page.goto",
        "page.click",
        "harness",
        "test infrastructure",
        "fixture",
    }
)

# Signals that indicate a real product bug (broken flow, error state).
_N2N_SIGNALS = frozenset(
    {
        "500 error",
        "error page",
        "broken flow",
        "data not saved",
        "crash",
        "exception",
        "regression",
        "missing data",
        "wrong result",
        "incorrect",
        "failed to load",
    }
)


def classify_finding(finding: AcceptanceFinding) -> BugType:
    """Classify an acceptance finding into a bug type.

    Uses the finding's critique_axis if already set to a known type,
    otherwise infers from text signals in summary/details.
    """
    # If critique_axis is already a known BugType, use it
    axis = finding.critique_axis.lower().strip()
    if axis in {bt.value for bt in BugType}:
        return BugType(axis)

    text = f"{finding.summary} {finding.details}".lower()

    # Harness signals take priority — these mask real results
    if any(signal in text for signal in _HARNESS_SIGNALS):
        return BugType.HARNESS_BUG

    # N2N signals indicate real product bugs
    if any(signal in text for signal in _N2N_SIGNALS):
        return BugType.N2N_BUG

    # UX-related keywords
    if any(kw in text for kw in ("ux", "usability", "confusing", "affordance", "discoverability")):
        return BugType.UX_GAP

    return BugType.UNKNOWN


def classify_proposal(proposal: AcceptanceIssueProposal) -> BugType:
    """Classify an issue proposal into a bug type."""
    axis = proposal.critique_axis.lower().strip()
    if axis in {bt.value for bt in BugType}:
        return BugType(axis)

    text = f"{proposal.title} {proposal.summary}".lower()

    if any(signal in text for signal in _HARNESS_SIGNALS):
        return BugType.HARNESS_BUG
    if any(signal in text for signal in _N2N_SIGNALS):
        return BugType.N2N_BUG
    if any(kw in text for kw in ("ux", "usability", "confusing", "affordance", "discoverability")):
        return BugType.UX_GAP

    return BugType.UNKNOWN


def should_auto_file(proposal: AcceptanceIssueProposal) -> tuple[bool, str]:
    """Determine if a proposal should be auto-filed based on its bug type.

    Returns (should_file, reason).

    - harness_bug: Do NOT file — fix the harness first
    - n2n_bug: File if meets severity/confidence thresholds
    - ux_gap: Hold for operator review
    - unknown: File conservatively
    """
    bug_type = classify_proposal(proposal)

    if bug_type == BugType.HARNESS_BUG:
        return False, "harness_bug: fix test infrastructure before filing"

    if bug_type == BugType.UX_GAP:
        return False, "ux_gap: held for operator review"

    # n2n_bug and unknown — eligible for filing
    return True, f"{bug_type.value}: eligible for auto-filing"


def triage_summary(
    findings: list[AcceptanceFinding],
    proposals: list[AcceptanceIssueProposal],
) -> dict[str, Any]:
    """Produce a triage summary grouping findings by bug type."""
    finding_types = [classify_finding(f) for f in findings]
    proposal_types = [classify_proposal(p) for p in proposals]

    return {
        "finding_counts": {
            bt.value: sum(1 for t in finding_types if t == bt)
            for bt in BugType
            if any(t == bt for t in finding_types)
        },
        "proposal_counts": {
            bt.value: sum(1 for t in proposal_types if t == bt)
            for bt in BugType
            if any(t == bt for t in proposal_types)
        },
        "harness_bugs_block_filing": any(t == BugType.HARNESS_BUG for t in finding_types),
        "auto_fileable_proposals": sum(1 for p in proposals if should_auto_file(p)[0]),
    }
