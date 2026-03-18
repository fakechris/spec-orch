from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any


class FlowType(StrEnum):
    """Supported workflow tiers aligned with change-management-policy."""

    FULL = "full"
    STANDARD = "standard"
    HOTFIX = "hotfix"


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


class MissionStatus(StrEnum):
    """Lifecycle states for a Mission (contract layer above issues)."""

    DRAFTING = "drafting"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ARCHIVED = "archived"


@dataclass
class Mission:
    """A cross-issue contract that defines what to build and why.

    The canonical spec lives in ``docs/specs/<mission_id>/spec.md`` inside the
    repo, not in Linear or any external system.
    """

    mission_id: str
    title: str
    status: MissionStatus = MissionStatus.DRAFTING
    spec_path: str = ""
    acceptance_criteria: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    interface_contracts: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    approved_at: str | None = None
    completed_at: str | None = None


class PlanStatus(StrEnum):
    """Lifecycle states for an ExecutionPlan."""

    DRAFT = "draft"
    APPROVED = "approved"
    EXECUTING = "executing"
    COMPLETED = "completed"


@dataclass
class WorkPacket:
    """An atomic unit of work derived from a Mission — becomes a Linear issue."""

    packet_id: str
    title: str
    spec_section: str = ""
    run_class: str = "feature"
    files_in_scope: list[str] = field(default_factory=list)
    files_out_of_scope: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    verification_commands: dict[str, list[str]] = field(default_factory=dict)
    builder_prompt: str = ""
    linear_issue_id: str | None = None


@dataclass
class Wave:
    """A group of parallelizable WorkPackets within an ExecutionPlan."""

    wave_number: int
    description: str = ""
    work_packets: list[WorkPacket] = field(default_factory=list)


@dataclass
class ExecutionPlan:
    """A DAG of Waves derived from a Mission by the Scoper."""

    plan_id: str
    mission_id: str
    waves: list[Wave] = field(default_factory=list)
    status: PlanStatus = PlanStatus.DRAFT


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


@dataclass(slots=True)
class VerificationSummary:
    lint_passed: bool = False
    typecheck_passed: bool = False
    test_passed: bool = False
    build_passed: bool = False
    details: dict[str, VerificationDetail] = field(default_factory=dict)

    @property
    def all_passed(self) -> bool:
        """Only count steps that were actually configured (have a detail entry
        with a non-empty command).  Unconfigured steps are treated as N/A
        rather than as failures."""
        for step in ("lint", "typecheck", "test", "build"):
            detail = self.details.get(step)
            if detail is not None and detail.command and not getattr(self, f"{step}_passed"):
                return False
        return True


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
    review_meta: ReviewMeta = field(default_factory=ReviewMeta)
    compliance_passed: bool = True
    claimed_flow: str | None = None
    demotion_proposed_by_conductor: bool = False
    diff_stats: dict[str, int] = field(default_factory=dict)
    issue_id: str = ""


@dataclass(slots=True)
class BuilderEvent:
    """Vendor-neutral event produced by a builder adapter.

    Each adapter maps its raw events (Codex JSONL, Cursor WebSocket, etc.)
    to this common model.  The ComplianceEngine and EventFormatter operate
    exclusively on BuilderEvent, never on raw vendor payloads.
    """

    timestamp: str
    # "message" | "command_start" | "command_end" | "file_change"
    # | "plan" | "reasoning" | "turn_end" | "error"
    kind: str
    text: str = ""
    exit_code: int | None = None
    file_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class GateVerdict:
    mergeable: bool
    failed_conditions: list[str]
    mergeable_internal: bool = True
    mergeable_external: bool = True
    promotion_required: bool = False
    promotion_target: str | None = None
    demotion_suggested: bool = False
    demotion_target: str | None = None
    backtrack_reason: str | None = None


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
class PlannerResult:
    """Output of a PlannerAdapter.plan() call."""

    questions: list[Question]
    spec_draft: SpecSnapshot | None = None
    raw_response: str = ""


class ThreadStatus(StrEnum):
    """Lifecycle states for a conversation thread."""

    ACTIVE = "active"
    FROZEN = "frozen"
    ARCHIVED = "archived"


@dataclass
class ConversationMessage:
    """A single message in a discussion thread — channel-agnostic."""

    message_id: str
    thread_id: str
    sender: str
    content: str
    timestamp: str
    channel: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversationThread:
    """Persistent state for a multi-turn brainstorming discussion."""

    thread_id: str
    channel: str
    mission_id: str | None = None
    messages: list[ConversationMessage] = field(default_factory=list)
    status: ThreadStatus = ThreadStatus.ACTIVE
    spec_snapshot: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class DeviationSeverity(StrEnum):
    MINOR = "minor"
    MAJOR = "major"
    BLOCKING = "blocking"


class DeviationResolution(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    SPEC_AMENDED = "spec_amended"
    REVERTED = "reverted"


@dataclass(slots=True)
class SpecDeviation:
    """Records how execution diverged from the approved spec."""

    deviation_id: str
    issue_id: str
    mission_id: str = ""
    description: str = ""
    severity: str = DeviationSeverity.MINOR
    resolution: str = DeviationResolution.PENDING
    detected_by: str = "gate"
    file_path: str | None = None


@dataclass
class ParallelConfig:
    """Controls concurrency for parallel wave execution."""

    max_concurrency: int = 3
    max_concurrency_cap: int = 0

    def effective_limit(self) -> int:
        cap = self.max_concurrency_cap or os.cpu_count() or 4
        return min(self.max_concurrency, cap)


@dataclass
class PacketResult:
    """Outcome of executing a single WorkPacket."""

    packet_id: str
    wave_id: int
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float


@dataclass
class WaveResult:
    """Aggregate outcome of all packets in a single Wave."""

    wave_id: int
    packet_results: list[PacketResult]
    all_succeeded: bool

    @property
    def failed_packets(self) -> list[PacketResult]:
        return [r for r in self.packet_results if r.exit_code != 0]


@dataclass
class ExecutionPlanResult:
    """Aggregate outcome of running an entire ExecutionPlan."""

    wave_results: list[WaveResult]
    total_duration: float

    def is_success(self) -> bool:
        return all(w.all_succeeded for w in self.wave_results)


@dataclass
class ArtifactManifest:
    """Records all artifacts produced by a single run.

    Written to ``{workspace}/artifact_manifest.json`` at the end of each run
    so that downstream consumers (ContextAssembler, Evolvers, Review) can
    locate artifacts by type without hard-coding paths.
    """

    run_id: str
    issue_id: str
    artifacts: dict[str, str] = field(default_factory=dict)
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
    gate: GateVerdict
    state: RunState = RunState.GATE_EVALUATED


# ---------------------------------------------------------------------------
# Flow Engine domain models (Change 01: scaffold-flow-engine)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FlowStep:
    """A single step within a workflow graph."""

    id: str
    run_state: RunState | None = None
    skippable_if: tuple[str, ...] = ()


@dataclass(frozen=True)
class FlowGraph:
    """Directed graph of steps for a specific FlowType."""

    flow_type: FlowType
    steps: tuple[FlowStep, ...]
    transitions: dict[str, tuple[str, ...]] = field(default_factory=dict)
    backtrack: dict[str, dict[str, str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_steps_map", {s.id: s for s in self.steps})

    def step_ids(self) -> list[str]:
        return [s.id for s in self.steps]

    def get_step(self, step_id: str) -> FlowStep | None:
        mapping: dict[str, FlowStep] = self._steps_map  # type: ignore[attr-defined]
        return mapping.get(step_id)


@dataclass(frozen=True)
class FlowTransitionEvent:
    """Records a flow promotion / demotion / backtrack event."""

    from_flow: str
    to_flow: str
    trigger: str
    timestamp: str
    issue_id: str = ""
    run_id: str = ""
