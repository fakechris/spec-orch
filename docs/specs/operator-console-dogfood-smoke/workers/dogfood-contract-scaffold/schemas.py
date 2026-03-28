# pylance: disable=reportUntypedBaseMetadata
"""
Data models and type definitions for SpecOrch Mission Dashboard.

Defines schemas for:
- Mission (with detail, transcript, approval_state, visual_qa_data, costs)
- MissionRound
- HumanInterventionRequest
- Dashboard API contract
- Daemon mission pickup interface
- ask_human intervention contract
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Protocol, runtime_checkable


# =============================================================================
# Enums
# =============================================================================


class MissionStatus(StrEnum):
    """Lifecycle states for a Mission (contract layer above issues)."""

    DRAFTING = "drafting"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ARCHIVED = "archived"


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


class ApprovalStatus(StrEnum):
    """Status for an approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    REVISION_REQUESTED = "revision_requested"
    FOLLOWUP_REQUESTED = "followup_requested"
    EXPIRED = "expired"


class InterventionType(StrEnum):
    """Types of human intervention requests."""

    ASK_HUMAN = "ask_human"
    APPROVE = "approve"
    REJECT = "reject"
    GUIDANCE = "guidance"
    FOLLOWUP = "followup"


# =============================================================================
# Mission Schemas
# =============================================================================


@dataclass
class MissionCosts:
    """Cost and budget tracking for a mission."""

    total_cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    budget_status: str = "unconfigured"  # unconfigured | healthy | warning | critical
    warning_threshold_usd: float | None = None
    critical_threshold_usd: float | None = None
    remaining_budget_usd: float | None = None
    incidents: list["CostIncident"] = field(default_factory=list)
    worker_costs: list["WorkerCost"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_cost_usd": self.total_cost_usd,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "budget_status": self.budget_status,
            "warning_threshold_usd": self.warning_threshold_usd,
            "critical_threshold_usd": self.critical_threshold_usd,
            "remaining_budget_usd": self.remaining_budget_usd,
            "incidents": [i.to_dict() for i in self.incidents],
            "worker_costs": [w.to_dict() for w in self.worker_costs],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MissionCosts":
        return cls(
            total_cost_usd=data.get("total_cost_usd", 0.0),
            input_tokens=data.get("input_tokens", 0),
            output_tokens=data.get("output_tokens", 0),
            budget_status=data.get("budget_status", "unconfigured"),
            warning_threshold_usd=data.get("warning_threshold_usd"),
            critical_threshold_usd=data.get("critical_threshold_usd"),
            remaining_budget_usd=data.get("remaining_budget_usd"),
            incidents=[CostIncident.from_dict(i) for i in data.get("incidents", [])],
            worker_costs=[WorkerCost.from_dict(w) for w in data.get("worker_costs", [])],
        )


@dataclass
class CostIncident:
    """An incident/warning related to mission costs."""

    severity: str = "warning"  # warning | critical
    message: str = ""
    actual_cost_usd: float = 0.0
    threshold_usd: float = 0.0
    recommended_action: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "message": self.message,
            "actual_cost_usd": self.actual_cost_usd,
            "threshold_usd": self.threshold_usd,
            "recommended_action": self.recommended_action,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CostIncident":
        return cls(
            severity=data.get("severity", "warning"),
            message=data.get("message", ""),
            actual_cost_usd=data.get("actual_cost_usd", 0.0),
            threshold_usd=data.get("threshold_usd", 0.0),
            recommended_action=data.get("recommended_action", ""),
        )


@dataclass
class WorkerCost:
    """Cost breakdown for a single worker/packet execution."""

    packet_id: str = ""
    adapter: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    turn_status: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "packet_id": self.packet_id,
            "adapter": self.adapter,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": self.cost_usd,
            "turn_status": self.turn_status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkerCost":
        return cls(
            packet_id=data.get("packet_id", ""),
            adapter=data.get("adapter", ""),
            input_tokens=data.get("input_tokens", 0),
            output_tokens=data.get("output_tokens", 0),
            cost_usd=data.get("cost_usd", 0.0),
            turn_status=data.get("turn_status", ""),
        )


@dataclass
class VisualQAFinding:
    """A finding from visual QA evaluation."""

    severity: str = "info"  # blocking | warning | info
    description: str = ""
    file_path: str | None = None
    line: int | None = None
    suggested_action: str | None = None


@dataclass
class VisualQAResult:
    """Visual QA evaluation result for a round."""

    round_id: int = 0
    evaluator: str = ""
    summary: str = ""
    confidence: float = 0.0
    status: str = "pass"  # pass | warning | blocking
    findings: list[VisualQAFinding] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)
    gallery_items: list["GalleryItem"] = field(default_factory=list)
    comparison_available: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "round_id": self.round_id,
            "evaluator": self.evaluator,
            "summary": self.summary,
            "confidence": self.confidence,
            "status": self.status,
            "findings": [
                {
                    "severity": f.severity,
                    "description": f.description,
                    "file_path": f.file_path,
                    "line": f.line,
                    "suggested_action": f.suggested_action,
                }
                for f in self.findings
            ],
            "artifacts": self.artifacts,
            "gallery_items": [g.to_dict() for g in self.gallery_items],
            "comparison_available": self.comparison_available,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VisualQAResult":
        findings = [
            VisualQAFinding(
                severity=f.get("severity", "info"),
                description=f.get("description", ""),
                file_path=f.get("file_path"),
                line=f.get("line"),
                suggested_action=f.get("suggested_action"),
            )
            for f in data.get("findings", [])
        ]
        gallery = [GalleryItem.from_dict(g) for g in data.get("gallery_items", [])]
        return cls(
            round_id=data.get("round_id", 0),
            evaluator=data.get("evaluator", ""),
            summary=data.get("summary", ""),
            confidence=data.get("confidence", 0.0),
            status=data.get("status", "pass"),
            findings=findings,
            artifacts=data.get("artifacts", {}),
            gallery_items=gallery,
            comparison_available=data.get("comparison_available", False),
        )


@dataclass
class GalleryItem:
    """An image artifact from visual QA."""

    label: str = ""
    path: str = ""
    kind: str = "image"  # image | diff

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "path": self.path,
            "kind": self.kind,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GalleryItem":
        return cls(
            label=data.get("label", ""),
            path=data.get("path", ""),
            kind=data.get("kind", "image"),
        )


@dataclass
class VisualQAData:
    """Visual QA data for a mission."""

    mission_id: str = ""
    total_rounds: int = 0
    blocking_findings: int = 0
    warning_findings: int = 0
    latest_confidence: float = 0.0
    blocking_rounds: list[int] = field(default_factory=list)
    gallery_items: int = 0
    diff_items: int = 0
    comparison_rounds: int = 0
    round_results: list[VisualQAResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "total_rounds": self.total_rounds,
            "blocking_findings": self.blocking_findings,
            "warning_findings": self.warning_findings,
            "latest_confidence": self.latest_confidence,
            "blocking_rounds": self.blocking_rounds,
            "gallery_items": self.gallery_items,
            "diff_items": self.diff_items,
            "comparison_rounds": self.comparison_rounds,
            "round_results": [r.to_dict() for r in self.round_results],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VisualQAData":
        return cls(
            mission_id=data.get("mission_id", ""),
            total_rounds=data.get("total_rounds", 0),
            blocking_findings=data.get("blocking_findings", 0),
            warning_findings=data.get("warning_findings", 0),
            latest_confidence=data.get("latest_confidence", 0.0),
            blocking_rounds=data.get("blocking_rounds", []),
            gallery_items=data.get("gallery_items", 0),
            diff_items=data.get("diff_items", 0),
            comparison_rounds=data.get("comparison_rounds", 0),
            round_results=[VisualQAResult.from_dict(r) for r in data.get("round_results", [])],
        )


@dataclass
class ApprovalAction:
    """An available approval action."""

    key: str = ""
    label: str = ""
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApprovalAction":
        return cls(
            key=data.get("key", ""),
            label=data.get("label", ""),
            message=data.get("message", ""),
        )


@dataclass
class ApprovalRequest:
    """An active approval request from the supervisor."""

    round_id: int = 0
    timestamp: str = ""
    summary: str = ""
    blocking_question: str | None = None
    decision_action: str = ""
    actions: list[ApprovalAction] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "round_id": self.round_id,
            "timestamp": self.timestamp,
            "summary": self.summary,
            "blocking_question": self.blocking_question,
            "decision_action": self.decision_action,
            "actions": [a.to_dict() for a in self.actions],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApprovalRequest":
        return cls(
            round_id=data.get("round_id", 0),
            timestamp=data.get("timestamp", ""),
            summary=data.get("summary", ""),
            blocking_question=data.get("blocking_question"),
            decision_action=data.get("decision_action", ""),
            actions=[ApprovalAction.from_dict(a) for a in data.get("actions", [])],
        )


@dataclass
class ApprovalHistoryEntry:
    """A recorded approval action."""

    timestamp: str = ""
    action_key: str = ""
    label: str = ""
    message: str = ""
    channel: str = ""
    status: str = ""  # applied | not_applied | failed
    effect: str = ""  # approval_granted | revision_requested | followup_requested | guidance_sent

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "action_key": self.action_key,
            "label": self.label,
            "message": self.message,
            "channel": self.channel,
            "status": self.status,
            "effect": self.effect,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApprovalHistoryEntry":
        return cls(
            timestamp=data.get("timestamp", ""),
            action_key=data.get("action_key", ""),
            label=data.get("label", ""),
            message=data.get("message", ""),
            channel=data.get("channel", ""),
            status=data.get("status", ""),
            effect=data.get("effect", ""),
        )


@dataclass
class ApprovalState:
    """Approval state for a mission."""

    status: str = "awaiting_human"  # awaiting_human | approved | revision_requested | followup_requested | failed
    summary: str = ""
    latest_action: ApprovalHistoryEntry | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "summary": self.summary,
            "latest_action": self.latest_action.to_dict() if self.latest_action else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApprovalState":
        latest = data.get("latest_action")
        return cls(
            status=data.get("status", "awaiting_human"),
            summary=data.get("summary", ""),
            latest_action=ApprovalHistoryEntry.from_dict(latest) if latest else None,
        )


@dataclass
class TranscriptEntry:
    """A single entry in a mission transcript."""

    kind: str = ""  # activity | event | incoming | message
    timestamp: str = ""
    message: str = ""
    event_type: str = ""
    source_path: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "timestamp": self.timestamp,
            "message": self.message,
            "event_type": self.event_type,
            "source_path": self.source_path,
            "raw": self.raw,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TranscriptEntry":
        return cls(
            kind=data.get("kind", ""),
            timestamp=data.get("timestamp", ""),
            message=data.get("message", ""),
            event_type=data.get("event_type", ""),
            source_path=data.get("source_path"),
            raw=data.get("raw", {}),
        )


@dataclass
class TranscriptBlock:
    """A grouped block in a transcript."""

    block_type: str = ""  # activity | event | message | tool | command_burst | milestone | supervisor | visual_finding
    emphasis: str = "neutral"  # neutral | log | narrative | tool | burst | decision | alert | milestone | critical | event
    timestamp: str = ""
    title: str = ""
    body: str = ""
    source_path: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    jump_targets: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "block_type": self.block_type,
            "emphasis": self.emphasis,
            "timestamp": self.timestamp,
            "title": self.title,
            "body": self.body,
            "source_path": self.source_path,
            "details": self.details,
            "jump_targets": self.jump_targets,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TranscriptBlock":
        return cls(
            block_type=data.get("block_type", ""),
            emphasis=data.get("emphasis", "neutral"),
            timestamp=data.get("timestamp", ""),
            title=data.get("title", ""),
            body=data.get("body", ""),
            source_path=data.get("source_path"),
            details=data.get("details", {}),
            jump_targets=data.get("jump_targets", []),
        )


@dataclass
class TranscriptData:
    """Transcript data for a mission/packet."""

    mission_id: str = ""
    packet_id: str = ""
    entries: list[TranscriptEntry] = field(default_factory=list)
    blocks: list[TranscriptBlock] = field(default_factory=list)
    milestones: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    telemetry: dict[str, str | None] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "packet_id": self.packet_id,
            "entries": [e.to_dict() for e in self.entries],
            "blocks": [b.to_dict() for b in self.blocks],
            "milestones": self.milestones,
            "summary": self.summary,
            "telemetry": self.telemetry,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TranscriptData":
        return cls(
            mission_id=data.get("mission_id", ""),
            packet_id=data.get("packet_id", ""),
            entries=[TranscriptEntry.from_dict(e) for e in data.get("entries", [])],
            blocks=[TranscriptBlock.from_dict(b) for b in data.get("blocks", [])],
            milestones=data.get("milestones", []),
            summary=data.get("summary", {}),
            telemetry=data.get("telemetry", {}),
        )


@dataclass
class MissionDetail:
    """Detailed mission information for the dashboard."""

    mission_id: str = ""
    title: str = ""
    status: str = ""
    created_at: str = ""
    approved_at: str | None = None
    completed_at: str | None = None
    acceptance_criteria: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    spec_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "title": self.title,
            "status": self.status,
            "created_at": self.created_at,
            "approved_at": self.approved_at,
            "completed_at": self.completed_at,
            "acceptance_criteria": self.acceptance_criteria,
            "constraints": self.constraints,
            "spec_path": self.spec_path,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MissionDetail":
        return cls(
            mission_id=data.get("mission_id", ""),
            title=data.get("title", ""),
            status=data.get("status", ""),
            created_at=data.get("created_at", ""),
            approved_at=data.get("approved_at"),
            completed_at=data.get("completed_at"),
            acceptance_criteria=data.get("acceptance_criteria", []),
            constraints=data.get("constraints", []),
            spec_path=data.get("spec_path", ""),
        )


# =============================================================================
# MissionRound
# =============================================================================


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

    action: RoundAction = RoundAction.CONTINUE
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
            "action": self.action.value if isinstance(self.action, RoundAction) else self.action,
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
    def from_dict(cls, data: dict[str, Any]) -> "RoundDecision":
        action_val = data.get("action", "continue")
        if isinstance(action_val, str):
            try:
                action = RoundAction(action_val)
            except ValueError:
                action = RoundAction.CONTINUE
        else:
            action = action_val

        session_ops_data = data.get("session_ops", {})
        plan_patch_data = data.get("plan_patch")

        plan_patch: PlanPatch | None = None
        if isinstance(plan_patch_data, dict):
            plan_patch = PlanPatch(
                modified_packets=plan_patch_data.get("modified_packets", {}),
                added_packets=plan_patch_data.get("added_packets", []),
                removed_packet_ids=plan_patch_data.get("removed_packet_ids", []),
                reason=plan_patch_data.get("reason", ""),
            )

        return cls(
            action=action,
            reason_code=data.get("reason_code", ""),
            summary=data.get("summary", ""),
            confidence=data.get("confidence", 0.0),
            affected_workers=data.get("affected_workers", []),
            artifacts=data.get("artifacts", {}),
            session_ops=SessionOps(
                reuse=session_ops_data.get("reuse", []),
                spawn=session_ops_data.get("spawn", []),
                cancel=session_ops_data.get("cancel", []),
            ),
            plan_patch=plan_patch,
            blocking_questions=data.get("blocking_questions", []),
        )


@dataclass
class MissionRound:
    """One complete execute-review-decide cycle in a mission."""

    round_id: int = 0
    wave_id: int = 0
    status: RoundStatus = RoundStatus.EXECUTING
    started_at: str = ""
    completed_at: str | None = None
    worker_results: list[dict[str, Any]] = field(default_factory=list)
    decision: RoundDecision | None = None
    paths: dict[str, str | None] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "round_id": self.round_id,
            "wave_id": self.wave_id,
            "status": self.status.value if isinstance(self.status, RoundStatus) else self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "worker_results": self.worker_results,
            "paths": self.paths,
        }
        if self.decision is not None:
            payload["decision"] = self.decision.to_dict()
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MissionRound":
        status_val = data.get("status", "executing")
        if isinstance(status_val, str):
            try:
                status = RoundStatus(status_val)
            except ValueError:
                status = RoundStatus.EXECUTING
        else:
            status = status_val

        decision_data = data.get("decision")
        decision = RoundDecision.from_dict(decision_data) if decision_data else None

        return cls(
            round_id=data.get("round_id", 0),
            wave_id=data.get("wave_id", 0),
            status=status,
            started_at=data.get("started_at", ""),
            completed_at=data.get("completed_at"),
            worker_results=data.get("worker_results", []),
            decision=decision,
            paths=data.get("paths", {}),
        )


# =============================================================================
# HumanInterventionRequest
# =============================================================================


@dataclass
class HumanInterventionRequest:
    """Request for human intervention during mission execution."""

    intervention_id: str = ""
    mission_id: str = ""
    round_id: int = 0
    intervention_type: InterventionType = InterventionType.ASK_HUMAN
    timestamp: str = ""
    summary: str = ""
    blocking_question: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    available_actions: list[ApprovalAction] = field(default_factory=list)
    status: ApprovalStatus = ApprovalStatus.PENDING

    def to_dict(self) -> dict[str, Any]:
        return {
            "intervention_id": self.intervention_id,
            "mission_id": self.mission_id,
            "round_id": self.round_id,
            "intervention_type": self.intervention_type.value
            if isinstance(self.intervention_type, InterventionType)
            else self.intervention_type,
            "timestamp": self.timestamp,
            "summary": self.summary,
            "blocking_question": self.blocking_question,
            "context": self.context,
            "available_actions": [a.to_dict() for a in self.available_actions],
            "status": self.status.value if isinstance(self.status, ApprovalStatus) else self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HumanInterventionRequest":
        int_type_val = data.get("intervention_type", "ask_human")
        if isinstance(int_type_val, str):
            try:
                int_type = InterventionType(int_type_val)
            except ValueError:
                int_type = InterventionType.ASK_HUMAN
        else:
            int_type = int_type_val

        status_val = data.get("status", "pending")
        if isinstance(status_val, str):
            try:
                status = ApprovalStatus(status_val)
            except ValueError:
                status = ApprovalStatus.PENDING
        else:
            status = status_val

        return cls(
            intervention_id=data.get("intervention_id", ""),
            mission_id=data.get("mission_id", ""),
            round_id=data.get("round_id", 0),
            intervention_type=int_type,
            timestamp=data.get("timestamp", ""),
            summary=data.get("summary", ""),
            blocking_question=data.get("blocking_question"),
            context=data.get("context", {}),
            available_actions=[
                ApprovalAction.from_dict(a) for a in data.get("available_actions", [])
            ],
            status=status,
        )


# =============================================================================
# Dashboard API Contract
# =============================================================================


@dataclass
class MissionDetailResponse:
    """Response schema for GET /api/missions/{mission_id}/detail"""

    mission: MissionDetail
    lifecycle: dict[str, Any]
    current_round: int = 0
    rounds: list[MissionRound] = field(default_factory=list)
    packets: list[dict[str, Any]] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    approval_request: ApprovalRequest | None = None
    approval_history: list[ApprovalHistoryEntry] = field(default_factory=list)
    approval_state: ApprovalState | None = None
    visual_qa: VisualQAData | None = None
    costs: MissionCosts | None = None
    artifacts: dict[str, str | None] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission": self.mission.to_dict(),
            "lifecycle": self.lifecycle,
            "current_round": self.current_round,
            "rounds": [r.to_dict() for r in self.rounds],
            "packets": self.packets,
            "actions": self.actions,
            "approval_request": self.approval_request.to_dict() if self.approval_request else None,
            "approval_history": [h.to_dict() for h in self.approval_history],
            "approval_state": self.approval_state.to_dict() if self.approval_state else None,
            "visual_qa": self.visual_qa.to_dict() if self.visual_qa else None,
            "costs": self.costs.to_dict() if self.costs else None,
            "artifacts": self.artifacts,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MissionDetailResponse":
        return cls(
            mission=MissionDetail.from_dict(data.get("mission", {})),
            lifecycle=data.get("lifecycle", {}),
            current_round=data.get("current_round", 0),
            rounds=[MissionRound.from_dict(r) for r in data.get("rounds", [])],
            packets=data.get("packets", []),
            actions=data.get("actions", []),
            approval_request=ApprovalRequest.from_dict(data["approval_request"])
            if data.get("approval_request")
            else None,
            approval_history=[
                ApprovalHistoryEntry.from_dict(h) for h in data.get("approval_history", [])
            ],
            approval_state=ApprovalState.from_dict(data["approval_state"])
            if data.get("approval_state")
            else None,
            visual_qa=VisualQAData.from_dict(data["visual_qa"]) if data.get("visual_qa") else None,
            costs=MissionCosts.from_dict(data["costs"]) if data.get("costs") else None,
            artifacts=data.get("artifacts", {}),
        )


@dataclass
class TranscriptResponse:
    """Response schema for GET /api/missions/{mission_id}/packets/{packet_id}/transcript"""

    mission_id: str = ""
    packet_id: str = ""
    entries: list[TranscriptEntry] = field(default_factory=list)
    blocks: list[TranscriptBlock] = field(default_factory=list)
    milestones: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    telemetry: dict[str, str | None] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "packet_id": self.packet_id,
            "entries": [e.to_dict() for e in self.entries],
            "blocks": [b.to_dict() for b in self.blocks],
            "milestones": self.milestones,
            "summary": self.summary,
            "telemetry": self.telemetry,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TranscriptResponse":
        return cls(
            mission_id=data.get("mission_id", ""),
            packet_id=data.get("packet_id", ""),
            entries=[TranscriptEntry.from_dict(e) for e in data.get("entries", [])],
            blocks=[TranscriptBlock.from_dict(b) for b in data.get("blocks", [])],
            milestones=data.get("milestones", []),
            summary=data.get("summary", {}),
            telemetry=data.get("telemetry", {}),
        )


@dataclass
class ApprovalResponse:
    """Response schema for GET /api/missions/{mission_id}/approval"""

    approval_request: ApprovalRequest | None = None
    approval_history: list[ApprovalHistoryEntry] = field(default_factory=list)
    approval_state: ApprovalState | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "approval_request": self.approval_request.to_dict() if self.approval_request else None,
            "approval_history": [h.to_dict() for h in self.approval_history],
            "approval_state": self.approval_state.to_dict() if self.approval_state else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApprovalResponse":
        return cls(
            approval_request=ApprovalRequest.from_dict(data["approval_request"])
            if data.get("approval_request")
            else None,
            approval_history=[
                ApprovalHistoryEntry.from_dict(h) for h in data.get("approval_history", [])
            ],
            approval_state=ApprovalState.from_dict(data["approval_state"])
            if data.get("approval_state")
            else None,
        )


@dataclass
class VisualQAResponse:
    """Response schema for GET /api/missions/{mission_id}/visual-qa"""

    mission_id: str = ""
    summary: dict[str, Any] = field(default_factory=dict)
    review_route: str = ""
    rounds: list[VisualQAResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "summary": self.summary,
            "review_route": self.review_route,
            "rounds": [r.to_dict() for r in self.rounds],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VisualQAResponse":
        return cls(
            mission_id=data.get("mission_id", ""),
            summary=data.get("summary", {}),
            review_route=data.get("review_route", ""),
            rounds=[VisualQAResult.from_dict(r) for r in data.get("rounds", [])],
        )


@dataclass
class CostsResponse:
    """Response schema for GET /api/missions/{mission_id}/costs"""

    mission_id: str = ""
    summary: dict[str, Any] = field(default_factory=dict)
    review_route: str = ""
    focus_packet_id: str | None = None
    highest_cost_worker: dict[str, Any] | None = None
    incidents: list[CostIncident] = field(default_factory=list)
    workers: list[WorkerCost] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "summary": self.summary,
            "review_route": self.review_route,
            "focus_packet_id": self.focus_packet_id,
            "highest_cost_worker": self.highest_cost_worker,
            "incidents": [i.to_dict() for i in self.incidents],
            "workers": [w.to_dict() for w in self.workers],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CostsResponse":
        return cls(
            mission_id=data.get("mission_id", ""),
            summary=data.get("summary", {}),
            review_route=data.get("review_route", ""),
            focus_packet_id=data.get("focus_packet_id"),
            highest_cost_worker=data.get("highest_cost_worker"),
            incidents=[CostIncident.from_dict(i) for i in data.get("incidents", [])],
            workers=[WorkerCost.from_dict(w) for w in data.get("workers", [])],
        )


# =============================================================================
# Daemon Mission Pickup Interface
# =============================================================================


@dataclass
class DaemonPickupClaim:
    """Claim issued by daemon when picking up a mission issue."""

    issue_id: str = ""
    claimed_at: str = ""
    lockfile_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "claimed_at": self.claimed_at,
            "lockfile_path": self.lockfile_path,
        }


@dataclass
class DaemonPickupResult:
    """Result of daemon attempting to pick up an issue."""

    success: bool = False
    issue_id: str = ""
    mission_id: str | None = None
    is_hotfix: bool = False
    error: str | None = None
    claim: DaemonPickupClaim | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "issue_id": self.issue_id,
            "mission_id": self.mission_id,
            "is_hotfix": self.is_hotfix,
            "error": self.error,
            "claim": self.claim.to_dict() if self.claim else None,
        }


class DaemonMissionPicker(Protocol):
    """Protocol for daemon mission pickup."""

    def pick_up(self, issue_id: str) -> DaemonPickupResult:
        """Attempt to pick up an issue for processing."""
        ...

    def release(self, issue_id: str) -> None:
        """Release a previously claimed issue."""
        ...

    def is_locked(self, issue_id: str) -> bool:
        """Check if an issue is currently locked by another picker."""
        ...

    def get_lockfile_path(self, issue_id: str) -> str:
        """Get the lockfile path for an issue."""
        ...


# =============================================================================
# ask_human Intervention Contract
# =============================================================================


@dataclass
class AskHumanIntervention:
    """The ask_human intervention contract - emitted when supervisor requests human input."""

    intervention_id: str = ""
    mission_id: str = ""
    round_id: int = 0
    timestamp: str = ""
    summary: str = ""
    blocking_questions: list[str] = field(default_factory=list)
    context_artifacts: dict[str, str] = field(default_factory=dict)  # artifact_name -> path
    decision: RoundDecision | None = None
    review_memo_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "intervention_id": self.intervention_id,
            "mission_id": self.mission_id,
            "round_id": self.round_id,
            "timestamp": self.timestamp,
            "summary": self.summary,
            "blocking_questions": self.blocking_questions,
            "context_artifacts": self.context_artifacts,
            "decision": self.decision.to_dict() if self.decision else None,
            "review_memo_path": self.review_memo_path,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AskHumanIntervention":
        decision_data = data.get("decision")
        decision = RoundDecision.from_dict(decision_data) if decision_data else None

        return cls(
            intervention_id=data.get("intervention_id", ""),
            mission_id=data.get("mission_id", ""),
            round_id=data.get("round_id", 0),
            timestamp=data.get("timestamp", ""),
            summary=data.get("summary", ""),
            blocking_questions=data.get("blocking_questions", []),
            context_artifacts=data.get("context_artifacts", {}),
            decision=decision,
            review_memo_path=data.get("review_memo_path"),
        )


@dataclass
class InterventionResponse:
    """Operator response to an intervention request."""

    intervention_id: str = ""
    action_key: str = ""  # approve | request_revision | ask_followup
    message: str = ""
    channel: str = "web-dashboard"
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "intervention_id": self.intervention_id,
            "action_key": self.action_key,
            "message": self.message,
            "channel": self.channel,
            "timestamp": self.timestamp,
        }


# =============================================================================
# Protocol Definitions (for type hints)
# =============================================================================


@runtime_checkable
class MissionPicker(Protocol):
    """Protocol for mission pickup operations."""

    def pick_up(self, issue_id: str) -> DaemonPickupResult:
        """Attempt to pick up an issue for processing."""
        ...

    def release(self, issue_id: str) -> None:
        """Release a previously claimed issue."""
        ...
