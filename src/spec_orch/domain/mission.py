"""Mission-level domain models: Mission, ExecutionPlan, rounds, parallel execution."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class MissionStatus(StrEnum):
    """Lifecycle states for a Mission (contract layer above issues)."""

    DRAFTING = "drafting"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    FAILED = "failed"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class MissionPhase(StrEnum):
    """Internal orchestration phases for mission lifecycle.

    More granular than :class:`MissionStatus` — multiple phases project to a
    single status via :func:`project_mission_status`.
    """

    APPROVED = "approved"
    PLANNING = "planning"
    PLANNED = "planned"
    PROMOTING = "promoting"
    EXECUTING = "executing"
    ALL_DONE = "all_done"
    RETROSPECTING = "retrospecting"
    EVOLVING = "evolving"
    COMPLETED = "completed"
    FAILED = "failed"


_PHASE_TO_STATUS: dict[str, MissionStatus] = {
    MissionPhase.APPROVED.value: MissionStatus.APPROVED,
    MissionPhase.PLANNING.value: MissionStatus.APPROVED,
    MissionPhase.PLANNED.value: MissionStatus.APPROVED,
    MissionPhase.PROMOTING.value: MissionStatus.APPROVED,
    MissionPhase.EXECUTING.value: MissionStatus.IN_PROGRESS,
    MissionPhase.ALL_DONE.value: MissionStatus.IN_PROGRESS,
    MissionPhase.RETROSPECTING.value: MissionStatus.IN_PROGRESS,
    MissionPhase.EVOLVING.value: MissionStatus.IN_PROGRESS,
    MissionPhase.COMPLETED.value: MissionStatus.COMPLETED,
    MissionPhase.FAILED.value: MissionStatus.FAILED,
}


def project_mission_status(phase: MissionPhase | str | None) -> MissionStatus:
    """Map an internal MissionPhase to the coarser external MissionStatus."""
    if phase is None:
        return MissionStatus.DRAFTING
    normalized = str(phase).strip().lower()
    return _PHASE_TO_STATUS.get(normalized, MissionStatus.DRAFTING)


class PlanStatus(StrEnum):
    """Lifecycle states for an ExecutionPlan."""

    DRAFT = "draft"
    APPROVED = "approved"
    EXECUTING = "executing"
    COMPLETED = "completed"


@dataclass
class Mission:
    """A cross-issue contract that defines what to build and why."""

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
        try:
            action = RoundAction(data["action"])
        except ValueError:
            raise ValueError(
                f"Unknown RoundAction {data['action']!r}; "
                f"expected one of {[a.value for a in RoundAction]}"
            ) from None
        return cls(
            action=action,
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
