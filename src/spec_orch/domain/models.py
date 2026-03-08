from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class Issue:
    issue_id: str
    title: str
    summary: str


@dataclass(slots=True)
class VerificationSummary:
    lint_passed: bool = False
    typecheck_passed: bool = False
    test_passed: bool = False
    build_passed: bool = False

    @property
    def all_passed(self) -> bool:
        return (
            self.lint_passed
            and self.typecheck_passed
            and self.test_passed
            and self.build_passed
        )


@dataclass(slots=True)
class ReviewSummary:
    verdict: str = "changes_requested"


@dataclass(slots=True)
class GateInput:
    spec_exists: bool = False
    spec_approved: bool = False
    within_boundaries: bool = False
    verification: VerificationSummary = field(default_factory=VerificationSummary)
    review: ReviewSummary = field(default_factory=ReviewSummary)
    human_acceptance: bool = False
    preview_required: bool = False
    preview_passed: bool = False


@dataclass(slots=True)
class GateVerdict:
    mergeable: bool
    failed_conditions: list[str]


@dataclass(slots=True)
class RunResult:
    issue: Issue
    workspace: Path
    task_spec: Path
    progress: Path
    explain: Path
    report: Path
    gate: GateVerdict
