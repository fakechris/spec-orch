"""Issue-level domain models: Issue, RunState, verification, builder, review."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
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
    RunState.GATE_EVALUATED: frozenset(
        {
            RunState.ACCEPTED,
            RunState.REVIEW_PENDING,
            RunState.VERIFYING,
        }
    ),
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
    target_files: list[str] = field(default_factory=list)
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
    mission_id: str | None = None
    spec_section: str | None = None
    run_class: str | None = None
    labels: list[str] = field(default_factory=list)


@dataclass(slots=True)
class VerificationDetail:
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str


@dataclass
class VerificationSummary:
    lint_passed: bool = False
    typecheck_passed: bool = False
    test_passed: bool = False
    build_passed: bool = False
    details: dict[str, VerificationDetail] = field(default_factory=dict)
    step_results: dict[str, bool] = field(default_factory=dict)
    step_outcomes: dict[str, str] = field(default_factory=dict)

    _LEGACY_FIELDS = ("lint", "typecheck", "test", "build")

    def set_step_passed(self, step: str, passed: bool) -> None:
        """Record the result for a verification step (works for any name)."""
        self.set_step_outcome(step, "pass" if passed else "fail")

    def set_step_outcome(self, step: str, outcome: str) -> None:
        """Record the outcome for a verification step.

        Valid outcomes are ``pass``, ``fail``, and ``skipped``.
        """
        normalized = outcome.strip().lower()
        if normalized not in {"pass", "fail", "skipped"}:
            normalized = "fail"
        self.step_outcomes[step] = normalized
        self.step_results[step] = normalized == "pass"
        if step in self._LEGACY_FIELDS:
            setattr(self, f"{step}_passed", normalized == "pass")

    def get_step_passed(self, step: str) -> bool:
        """Get the result for a verification step by name."""
        if step in self.step_results:
            return self.step_results[step]
        if step in self._LEGACY_FIELDS:
            return getattr(self, f"{step}_passed", False)
        return False

    def get_step_outcome(self, step: str) -> str:
        if step in self.step_outcomes:
            return self.step_outcomes[step]
        if step in self.step_results:
            return "pass" if self.step_results[step] else "fail"
        if step in self._LEGACY_FIELDS:
            return "pass" if getattr(self, f"{step}_passed", False) else "fail"
        return "fail"

    @property
    def has_skipped(self) -> bool:
        steps = self.details.keys() or self.step_outcomes.keys()
        return any(self.get_step_outcome(step) == "skipped" for step in steps)

    @property
    def all_passed(self) -> bool:
        """Return True only when at least one step ran and every step passed."""
        steps = list(self.details.keys()) or list(self.step_outcomes.keys())
        if steps:
            return all(self.get_step_outcome(step) == "pass" for step in steps)
        return all(getattr(self, f"{step}_passed", False) for step in self._LEGACY_FIELDS)

    @property
    def all_passed_or_skipped(self) -> bool:
        """Return True when every step either passed or was explicitly skipped.

        Use this for flows (e.g. hotfix) that tolerate missing verification
        steps.  Unlike ``all_passed``, a ``skipped`` outcome is not treated
        as a failure here.
        """
        steps = list(self.details.keys()) or list(self.step_outcomes.keys())
        if steps:
            return all(self.get_step_outcome(step) in ("pass", "skipped") for step in steps)
        return all(getattr(self, f"{step}_passed", False) for step in self._LEGACY_FIELDS)

    @property
    def skipped_steps(self) -> list[str]:
        """Return the names of verification steps that were skipped."""
        steps = list(self.details.keys()) or list(self.step_outcomes.keys())
        return [s for s in steps if self.get_step_outcome(s) == "skipped"]


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
class Finding:
    """A structured review observation — unified across all review sources."""

    id: str
    source: str
    severity: str  # "blocking" | "advisory"
    confidence: float
    scope: str  # "in_spec" | "out_of_spec"
    fingerprint: str
    description: str
    file_path: str | None = None
    line: int | None = None
    suggested_action: str | None = None
    resolved: bool = False


@dataclass(slots=True)
class ReviewMeta:
    """Convergence metadata for review loops."""

    review_epoch: int = 0
    autofix_budget: int = 3
    findings: list[Finding] = field(default_factory=list)

    @property
    def blocking_unresolved(self) -> list[Finding]:
        return [
            f
            for f in self.findings
            if f.severity == "blocking" and not f.resolved and f.scope == "in_spec"
        ]

    @property
    def budget_exhausted(self) -> bool:
        return self.review_epoch >= self.autofix_budget

    def deduplicated_findings(self) -> list[Finding]:
        """Return findings de-duplicated by fingerprint (keep first)."""
        seen: set[str] = set()
        result: list[Finding] = []
        for f in self.findings:
            if f.fingerprint not in seen:
                seen.add(f.fingerprint)
                result.append(f)
        return result


@dataclass(slots=True)
class BuilderEvent:
    """Vendor-neutral event produced by a builder adapter."""

    timestamp: str
    kind: str
    text: str = ""
    exit_code: int | None = None
    file_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ArtifactManifest:
    """Records all artifacts produced by a single run."""

    run_id: str
    issue_id: str
    artifacts: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    STANDARD_TYPES = (
        "spec_snapshot",
        "builder_report",
        "builder_events",
        "verification",
        "gate_report",
        "review_report",
        "deviations",
        "explain",
        "report",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "issue_id": self.issue_id,
            "artifacts": self.artifacts,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }


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
    gate: Any  # GateVerdict — avoiding circular import with domain.gate
    state: RunState = RunState.GATE_EVALUATED
