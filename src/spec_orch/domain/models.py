from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class RunState(StrEnum):
    """Explicit lifecycle states for an issue run."""

    DRAFT = "draft"
    SPEC_DRAFTING = "spec_drafting"
    SPEC_APPROVED = "spec_approved"
    BUILDING = "building"
    VERIFYING = "verifying"
    REVIEW_PENDING = "review_pending"
    GATE_EVALUATED = "gate_evaluated"
    ACCEPTED = "accepted"
    MERGED = "merged"
    FAILED = "failed"


TERMINAL_STATES = frozenset({RunState.ACCEPTED, RunState.MERGED, RunState.FAILED})

_VALID_TRANSITIONS: dict[RunState, frozenset[RunState]] = {
    RunState.DRAFT: frozenset({RunState.SPEC_DRAFTING, RunState.SPEC_APPROVED, RunState.BUILDING}),
    RunState.SPEC_DRAFTING: frozenset({RunState.SPEC_APPROVED, RunState.FAILED}),
    RunState.SPEC_APPROVED: frozenset({RunState.BUILDING, RunState.FAILED}),
    RunState.BUILDING: frozenset({RunState.VERIFYING, RunState.FAILED}),
    RunState.VERIFYING: frozenset({RunState.REVIEW_PENDING, RunState.FAILED}),
    RunState.REVIEW_PENDING: frozenset({RunState.GATE_EVALUATED, RunState.VERIFYING}),
    RunState.GATE_EVALUATED: frozenset({
        RunState.ACCEPTED, RunState.REVIEW_PENDING, RunState.VERIFYING,
    }),
    RunState.ACCEPTED: frozenset({RunState.MERGED}),
    RunState.MERGED: frozenset(),
    RunState.FAILED: frozenset({RunState.BUILDING, RunState.VERIFYING}),
}


def validate_transition(current: RunState, target: RunState) -> None:
    """Raise ValueError if *current* → *target* is not a legal transition."""
    allowed = _VALID_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise ValueError(
            f"Invalid state transition: {current.value} → {target.value}. "
            f"Allowed: {', '.join(s.value for s in sorted(allowed, key=lambda s: s.value))}"
        )


@dataclass(slots=True)
class IssueContext:
    files_to_read: list[str] = field(default_factory=list)
    architecture_notes: str = ""
    constraints: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Issue:
    issue_id: str
    title: str
    summary: str
    builder_prompt: str | None = None
    verification_commands: dict[str, list[str]] = field(default_factory=dict)
    context: IssueContext = field(default_factory=IssueContext)
    acceptance_criteria: list[str] = field(default_factory=list)


@dataclass(slots=True)
class VerificationDetail:
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str


@dataclass(slots=True)
class VerificationSummary:
    lint_passed: bool = False
    typecheck_passed: bool = False
    test_passed: bool = False
    build_passed: bool = False
    details: dict[str, VerificationDetail] = field(default_factory=dict)

    @property
    def all_passed(self) -> bool:
        return (
            self.lint_passed
            and self.typecheck_passed
            and self.test_passed
            and self.build_passed
        )


@dataclass(slots=True)
class BuilderResult:
    succeeded: bool
    command: list[str]
    stdout: str
    stderr: str
    report_path: Path
    adapter: str
    agent: str
    skipped: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ReviewSummary:
    verdict: str = "pending"
    reviewed_by: str | None = None
    report_path: Path | None = None


@dataclass(slots=True)
class GateInput:
    spec_exists: bool = False
    spec_approved: bool = False
    within_boundaries: bool = False
    builder_succeeded: bool = True
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
class Question:
    """A question raised during planning or execution."""

    id: str
    asked_by: str
    target: str
    category: str
    blocking: bool
    text: str
    answer: str | None = None
    answered_by: str | None = None


@dataclass(slots=True)
class Decision:
    """A formal answer to a Question."""

    question_id: str
    answer: str
    decided_by: str
    timestamp: str


@dataclass
class SpecSnapshot:
    """Frozen, approved specification consumed by the builder.

    The builder reads only this artifact — it must not modify it or access
    the raw fixture/plan directly.
    """

    version: int
    approved: bool
    approved_by: str | None
    issue: Issue
    questions: list[Question] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)

    def has_unresolved_blocking_questions(self) -> bool:
        blocking_ids = {q.id for q in self.questions if q.blocking}
        answered_ids = {d.question_id for d in self.decisions}
        return bool(blocking_ids - answered_ids)


@dataclass(slots=True)
class RunResult:
    issue: Issue
    workspace: Path
    task_spec: Path
    progress: Path
    explain: Path
    report: Path
    builder: BuilderResult
    review: ReviewSummary
    gate: GateVerdict
    state: RunState = RunState.GATE_EVALUATED
