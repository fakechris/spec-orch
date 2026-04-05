from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any


def _coerce_confidence_score(value: Any, *, default: float = 0.0) -> float:
    def _sanitize(number: float) -> float:
        return number if math.isfinite(number) and 0.0 <= number <= 1.0 else default

    if isinstance(value, bool):
        return _sanitize(float(value))
    if isinstance(value, (int, float)):
        return _sanitize(float(value))
    if isinstance(value, str):
        normalized = value.strip().lower()
        if not normalized:
            return default
        mapped = {"high": 0.9, "medium": 0.7, "low": 0.3}.get(normalized)
        if mapped is not None:
            return _sanitize(mapped)
        try:
            return _sanitize(float(normalized))
        except ValueError:
            return default
    return default


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
    FAILED = "failed"
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


class RoundStatus(StrEnum):
    """Lifecycle states for one execute-review-decide round."""

    EXECUTING = "executing"
    COLLECTING = "collecting"
    REVIEWING = "reviewing"
    DECIDED = "decided"
    COMPLETED = "completed"
    FAILED = "failed"


class RoundAction(StrEnum):
    """Supervisor actions emitted after reviewing one round."""

    CONTINUE = "continue"
    RETRY = "retry"
    REPLAN_REMAINING = "replan_remaining"
    ASK_HUMAN = "ask_human"
    STOP = "stop"


@dataclass
class SessionOps:
    """Lifecycle operations to apply to worker sessions after a round."""

    reuse: list[str] = field(default_factory=list)
    spawn: list[str] = field(default_factory=list)
    cancel: list[str] = field(default_factory=list)


@dataclass
class PlanPatch:
    """Structured modifications to the remaining execution plan."""

    modified_packets: dict[str, dict[str, Any]] = field(default_factory=dict)
    added_packets: list[dict[str, Any]] = field(default_factory=list)
    removed_packet_ids: list[str] = field(default_factory=list)
    reason: str = ""


@dataclass
class RoundDecision:
    """Thin, structured supervisor output for orchestration control."""

    action: RoundAction
    reason_code: str = ""
    summary: str = ""
    confidence: float = 0.0
    affected_workers: list[str] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)
    session_ops: SessionOps = field(default_factory=SessionOps)
    plan_patch: PlanPatch | None = None
    blocking_questions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "action": self.action.value,
            "reason_code": self.reason_code,
            "summary": self.summary,
            "confidence": self.confidence,
            "affected_workers": self.affected_workers,
            "artifacts": self.artifacts,
            "session_ops": {
                "reuse": self.session_ops.reuse,
                "spawn": self.session_ops.spawn,
                "cancel": self.session_ops.cancel,
            },
            "blocking_questions": self.blocking_questions,
        }
        if self.plan_patch is not None:
            payload["plan_patch"] = {
                "modified_packets": self.plan_patch.modified_packets,
                "added_packets": self.plan_patch.added_packets,
                "removed_packet_ids": self.plan_patch.removed_packet_ids,
                "reason": self.plan_patch.reason,
            }
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RoundDecision:
        if "action" not in data:
            raise ValueError(f"Missing required field 'action' in RoundDecision data: {data!r}")
        session_ops = data.get("session_ops", {})
        plan_patch_raw = data.get("plan_patch")
        plan_patch: PlanPatch | None = None
        if isinstance(plan_patch_raw, dict):
            plan_patch = PlanPatch(
                modified_packets=plan_patch_raw.get("modified_packets", {}),
                added_packets=plan_patch_raw.get("added_packets", []),
                removed_packet_ids=plan_patch_raw.get("removed_packet_ids", []),
                reason=plan_patch_raw.get("reason", ""),
            )
        return cls(
            action=RoundAction(data["action"]),
            reason_code=data.get("reason_code", ""),
            summary=data.get("summary", ""),
            confidence=data.get("confidence", 0.0),
            affected_workers=data.get("affected_workers", []),
            artifacts=data.get("artifacts", {}),
            session_ops=SessionOps(
                reuse=session_ops.get("reuse", []),
                spawn=session_ops.get("spawn", []),
                cancel=session_ops.get("cancel", []),
            ),
            plan_patch=plan_patch,
            blocking_questions=data.get("blocking_questions", []),
        )


@dataclass
class RoundArtifacts:
    """Artifacts collected from one wave execution before supervisor review."""

    round_id: int
    mission_id: str
    builder_reports: list[dict[str, Any]] = field(default_factory=list)
    verification_outputs: list[dict[str, Any]] = field(default_factory=list)
    gate_verdicts: list[dict[str, Any]] = field(default_factory=list)
    manifest_paths: list[str] = field(default_factory=list)
    diff_summary: str = ""
    worker_session_ids: list[str] = field(default_factory=list)
    visual_evaluation: VisualEvaluationResult | None = None


@dataclass
class VisualEvaluationResult:
    """Optional visual/interactive evaluation produced between execution and review."""

    evaluator: str
    summary: str = ""
    confidence: float = 0.0
    findings: list[dict[str, Any]] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "evaluator": self.evaluator,
            "summary": self.summary,
            "confidence": self.confidence,
            "findings": self.findings,
            "artifacts": self.artifacts,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VisualEvaluationResult:
        return cls(
            evaluator=data.get("evaluator", ""),
            summary=data.get("summary", ""),
            confidence=data.get("confidence", 0.0),
            findings=data.get("findings", []),
            artifacts=data.get("artifacts", {}),
        )


@dataclass
class AcceptanceFinding:
    severity: str
    summary: str
    details: str = ""
    expected: str = ""
    actual: str = ""
    route: str = ""
    artifact_paths: dict[str, str] = field(default_factory=dict)
    critique_axis: str = ""
    operator_task: str = ""
    why_it_matters: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "summary": self.summary,
            "details": self.details,
            "expected": self.expected,
            "actual": self.actual,
            "route": self.route,
            "artifact_paths": self.artifact_paths,
            "critique_axis": self.critique_axis,
            "operator_task": self.operator_task,
            "why_it_matters": self.why_it_matters,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AcceptanceFinding:
        return cls(
            severity=data.get("severity", ""),
            summary=data.get("summary", ""),
            details=data.get("details", ""),
            expected=data.get("expected", ""),
            actual=data.get("actual", ""),
            route=data.get("route", ""),
            artifact_paths=data.get("artifact_paths", {}),
            critique_axis=data.get("critique_axis", ""),
            operator_task=data.get("operator_task", ""),
            why_it_matters=data.get("why_it_matters", ""),
        )


class AcceptanceMode(StrEnum):
    FEATURE_SCOPED = "feature_scoped"
    IMPACT_SWEEP = "impact_sweep"
    WORKFLOW = "workflow"
    EXPLORATORY = "exploratory"


@dataclass
class AcceptanceInteractionStep:
    action: str
    target: str
    description: str = ""
    value: str = ""
    timeout_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "target": self.target,
            "description": self.description,
            "value": self.value,
            "timeout_ms": self.timeout_ms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AcceptanceInteractionStep:
        raw_timeout = data.get("timeout_ms", 0)
        try:
            timeout_ms = int(raw_timeout)
        except (TypeError, ValueError):
            timeout_ms = 0
        return cls(
            action=data.get("action", ""),
            target=data.get("target", ""),
            description=data.get("description", ""),
            value=str(data.get("value", "") or ""),
            timeout_ms=max(timeout_ms, 0),
        )


@dataclass
class AcceptanceCampaign:
    mode: AcceptanceMode
    goal: str
    primary_routes: list[str] = field(default_factory=list)
    related_routes: list[str] = field(default_factory=list)
    interaction_plans: dict[str, list[AcceptanceInteractionStep]] = field(default_factory=dict)
    coverage_expectations: list[str] = field(default_factory=list)
    required_interactions: list[str] = field(default_factory=list)
    min_primary_routes: int = 0
    related_route_budget: int = 0
    interaction_budget: str = ""
    filing_policy: str = ""
    exploration_budget: str = ""
    seed_routes: list[str] = field(default_factory=list)
    allowed_expansions: list[str] = field(default_factory=list)
    critique_focus: list[str] = field(default_factory=list)
    stop_conditions: list[str] = field(default_factory=list)
    evidence_budget: str = ""
    functional_plan: list[str] = field(default_factory=list)
    adversarial_plan: list[str] = field(default_factory=list)
    coverage_gaps: list[str] = field(default_factory=list)
    merged_plan: list[str] = field(default_factory=list)

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        if value is None:
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "goal": self.goal,
            "primary_routes": self.primary_routes,
            "related_routes": self.related_routes,
            "interaction_plans": {
                route: [step.to_dict() for step in steps]
                for route, steps in self.interaction_plans.items()
            },
            "coverage_expectations": self.coverage_expectations,
            "required_interactions": self.required_interactions,
            "min_primary_routes": self.min_primary_routes,
            "related_route_budget": self.related_route_budget,
            "interaction_budget": self.interaction_budget,
            "filing_policy": self.filing_policy,
            "exploration_budget": self.exploration_budget,
            "seed_routes": self.seed_routes,
            "allowed_expansions": self.allowed_expansions,
            "critique_focus": self.critique_focus,
            "stop_conditions": self.stop_conditions,
            "evidence_budget": self.evidence_budget,
            "functional_plan": self.functional_plan,
            "adversarial_plan": self.adversarial_plan,
            "coverage_gaps": self.coverage_gaps,
            "merged_plan": self.merged_plan,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AcceptanceCampaign:
        def _coerce_str_list(value: Any) -> list[str]:
            if isinstance(value, str):
                stripped = value.strip()
                return [stripped] if stripped else []
            if not isinstance(value, list):
                return []
            return [str(item) for item in value if isinstance(item, str) and item.strip()]

        return cls(
            mode=AcceptanceMode(data.get("mode", AcceptanceMode.EXPLORATORY.value)),
            goal=data.get("goal", ""),
            primary_routes=data.get("primary_routes", []),
            related_routes=data.get("related_routes", []),
            interaction_plans={
                route: [
                    AcceptanceInteractionStep.from_dict(step)
                    for step in steps
                    if isinstance(step, dict)
                ]
                for route, steps in data.get("interaction_plans", {}).items()
                if isinstance(route, str) and isinstance(steps, list)
            },
            coverage_expectations=data.get("coverage_expectations", []),
            required_interactions=data.get("required_interactions", []),
            min_primary_routes=cls._safe_int(data.get("min_primary_routes", 0)),
            related_route_budget=cls._safe_int(data.get("related_route_budget", 0)),
            interaction_budget=data.get("interaction_budget", ""),
            filing_policy=data.get("filing_policy", ""),
            exploration_budget=data.get("exploration_budget", ""),
            seed_routes=_coerce_str_list(data.get("seed_routes", [])),
            allowed_expansions=_coerce_str_list(data.get("allowed_expansions", [])),
            critique_focus=_coerce_str_list(data.get("critique_focus", [])),
            stop_conditions=_coerce_str_list(data.get("stop_conditions", [])),
            evidence_budget=data.get("evidence_budget", ""),
            functional_plan=_coerce_str_list(data.get("functional_plan", [])),
            adversarial_plan=_coerce_str_list(data.get("adversarial_plan", [])),
            coverage_gaps=_coerce_str_list(data.get("coverage_gaps", [])),
            merged_plan=_coerce_str_list(data.get("merged_plan", [])),
        )


@dataclass
class AcceptanceIssueProposal:
    title: str
    summary: str
    severity: str
    confidence: float = 0.0
    repro_steps: list[str] = field(default_factory=list)
    expected: str = ""
    actual: str = ""
    route: str = ""
    artifact_paths: dict[str, str] = field(default_factory=dict)
    critique_axis: str = ""
    operator_task: str = ""
    why_it_matters: str = ""
    hold_reason: str = ""
    linear_issue_id: str = ""
    filing_status: str = ""
    filing_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "summary": self.summary,
            "severity": self.severity,
            "confidence": self.confidence,
            "repro_steps": self.repro_steps,
            "expected": self.expected,
            "actual": self.actual,
            "route": self.route,
            "artifact_paths": self.artifact_paths,
            "critique_axis": self.critique_axis,
            "operator_task": self.operator_task,
            "why_it_matters": self.why_it_matters,
            "hold_reason": self.hold_reason,
            "linear_issue_id": self.linear_issue_id,
            "filing_status": self.filing_status,
            "filing_error": self.filing_error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AcceptanceIssueProposal:
        return cls(
            title=data.get("title", ""),
            summary=data.get("summary", ""),
            severity=data.get("severity", ""),
            confidence=_coerce_confidence_score(data.get("confidence", 0.0)),
            repro_steps=data.get("repro_steps", []),
            expected=data.get("expected", ""),
            actual=data.get("actual", ""),
            route=data.get("route", ""),
            artifact_paths=data.get("artifact_paths", {}),
            critique_axis=data.get("critique_axis", ""),
            operator_task=data.get("operator_task", ""),
            why_it_matters=data.get("why_it_matters", ""),
            hold_reason=data.get("hold_reason", ""),
            linear_issue_id=data.get("linear_issue_id", ""),
            filing_status=data.get("filing_status", ""),
            filing_error=data.get("filing_error", ""),
        )


@dataclass
class AcceptanceReviewResult:
    status: str
    summary: str
    confidence: float
    evaluator: str
    findings: list[AcceptanceFinding] = field(default_factory=list)
    issue_proposals: list[AcceptanceIssueProposal] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)
    tested_routes: list[str] = field(default_factory=list)
    acceptance_mode: str = ""
    coverage_status: str = ""
    untested_expected_routes: list[str] = field(default_factory=list)
    recommended_next_step: str = ""
    campaign: AcceptanceCampaign | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "status": self.status,
            "summary": self.summary,
            "confidence": self.confidence,
            "evaluator": self.evaluator,
            "findings": [finding.to_dict() for finding in self.findings],
            "issue_proposals": [proposal.to_dict() for proposal in self.issue_proposals],
            "artifacts": self.artifacts,
            "tested_routes": self.tested_routes,
            "acceptance_mode": self.acceptance_mode,
            "coverage_status": self.coverage_status,
            "untested_expected_routes": self.untested_expected_routes,
            "recommended_next_step": self.recommended_next_step,
        }
        if self.campaign is not None:
            payload["campaign"] = self.campaign.to_dict()
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AcceptanceReviewResult:
        return cls(
            status=data.get("status", ""),
            summary=data.get("summary", ""),
            confidence=_coerce_confidence_score(data.get("confidence", 0.0)),
            evaluator=data.get("evaluator", ""),
            findings=[
                AcceptanceFinding.from_dict(item)
                for item in data.get("findings", [])
                if isinstance(item, dict)
            ],
            issue_proposals=[
                AcceptanceIssueProposal.from_dict(item)
                for item in data.get("issue_proposals", [])
                if isinstance(item, dict)
            ],
            artifacts=data.get("artifacts", {}),
            tested_routes=data.get("tested_routes", []),
            acceptance_mode=data.get("acceptance_mode", ""),
            coverage_status=data.get("coverage_status", ""),
            untested_expected_routes=data.get("untested_expected_routes", []),
            recommended_next_step=data.get("recommended_next_step", ""),
            campaign=(
                AcceptanceCampaign.from_dict(data["campaign"])
                if isinstance(data.get("campaign"), dict)
                else None
            ),
        )


@dataclass
class RoundSummary:
    """Persistent summary of one full execute-review-decide cycle."""

    round_id: int
    wave_id: int
    status: RoundStatus
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: str | None = None
    worker_results: list[dict[str, Any]] = field(default_factory=list)
    decision: RoundDecision | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "round_id": self.round_id,
            "wave_id": self.wave_id,
            "status": self.status.value,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "worker_results": self.worker_results,
        }
        if self.decision is not None:
            payload["decision"] = self.decision.to_dict()
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RoundSummary:
        decision = data.get("decision")
        return cls(
            round_id=data["round_id"],
            wave_id=data["wave_id"],
            status=RoundStatus(data["status"]),
            started_at=data.get("started_at", ""),
            completed_at=data.get("completed_at"),
            worker_results=data.get("worker_results", []),
            decision=RoundDecision.from_dict(decision) if decision else None,
        )


@dataclass
class MissionExecutionResult:
    """Unified mission execution result shared by lifecycle and daemon owners."""

    mission_id: str
    completed: bool
    paused: bool = False
    max_rounds_hit: bool = False
    summary_markdown: str = ""
    rounds: list[RoundSummary] = field(default_factory=list)
    last_round_artifacts: RoundArtifacts | None = None
    blocking_questions: list[str] = field(default_factory=list)


@dataclass
class ArtifactManifest:
    """Records all artifacts produced by a single run.

    Canonical location is ``{workspace}/run_artifact/manifest.json`` with a
    legacy compatibility copy at ``{workspace}/artifact_manifest.json`` so
    downstream consumers can locate artifacts by type without hard-coding paths.
    """

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


# ── Evolution lifecycle ──


class EvolutionChangeType(StrEnum):
    """Types of change an evolver can propose."""

    PROMPT_VARIANT = "prompt_variant"
    SCOPER_HINT = "scoper_hint"
    POLICY = "policy"
    HARNESS_RULE = "harness_rule"
    CONFIG_SUGGESTION = "config_suggestion"


class EvolutionValidationMethod(StrEnum):
    """How a proposal was validated."""

    AB_COMPARE = "a_b_compare"
    BACKTEST = "backtest"
    RULE_VALIDATOR = "rule_validator"
    EVAL_RUNNER = "eval_runner"
    AUTO = "auto"


@dataclass
class EvolutionProposal:
    """One proposed evolution change, produced by an evolver."""

    proposal_id: str
    evolver_name: str
    change_type: EvolutionChangeType
    content: dict[str, Any] = field(default_factory=dict)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.5
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self, *, include_content: bool = True) -> dict[str, Any]:
        d: dict[str, Any] = {
            "proposal_id": self.proposal_id,
            "evolver_name": self.evolver_name,
            "change_type": self.change_type.value,
            "evidence_count": len(self.evidence),
            "confidence": self.confidence,
            "created_at": self.created_at,
        }
        if include_content:
            d["content"] = self.content
        return d


@dataclass
class EvolutionOutcome:
    """Result of validating a proposal."""

    proposal_id: str
    accepted: bool
    validation_method: EvolutionValidationMethod = EvolutionValidationMethod.AUTO
    metrics: dict[str, float] = field(default_factory=dict)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "accepted": self.accepted,
            "validation_method": self.validation_method.value,
            "metrics": self.metrics,
            "reason": self.reason,
        }
