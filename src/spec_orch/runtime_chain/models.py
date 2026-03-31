from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class RuntimeSubjectKind(StrEnum):
    ISSUE = "issue"
    MISSION = "mission"
    ROUND = "round"
    PACKET = "packet"
    SUPERVISOR = "supervisor"
    ACCEPTANCE = "acceptance"
    REPLAY = "replay"


class ChainPhase(StrEnum):
    STARTED = "started"
    HEARTBEAT = "heartbeat"
    COMPLETED = "completed"
    FAILED = "failed"
    DEGRADED = "degraded"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class RuntimeChainEvent:
    chain_id: str
    span_id: str
    parent_span_id: str | None
    subject_kind: RuntimeSubjectKind
    subject_id: str
    phase: ChainPhase
    status_reason: str = ""
    session_refs: dict[str, Any] = field(default_factory=dict)
    artifact_refs: dict[str, Any] = field(default_factory=dict)
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "chain_id": self.chain_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "subject_kind": self.subject_kind.value,
            "subject_id": self.subject_id,
            "phase": self.phase.value,
            "status_reason": self.status_reason,
            "session_refs": self.session_refs,
            "artifact_refs": self.artifact_refs,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> RuntimeChainEvent:
        return cls(
            chain_id=str(payload.get("chain_id", "")),
            span_id=str(payload.get("span_id", "")),
            parent_span_id=(
                str(payload["parent_span_id"])
                if payload.get("parent_span_id") is not None
                else None
            ),
            subject_kind=RuntimeSubjectKind(str(payload.get("subject_kind", "issue"))),
            subject_id=str(payload.get("subject_id", "")),
            phase=ChainPhase(str(payload.get("phase", "started"))),
            status_reason=str(payload.get("status_reason", "")),
            session_refs=dict(payload.get("session_refs") or {}),
            artifact_refs=dict(payload.get("artifact_refs") or {}),
            updated_at=str(payload.get("updated_at", "")),
        )


@dataclass(slots=True)
class RuntimeChainStatus:
    chain_id: str
    active_span_id: str
    subject_kind: RuntimeSubjectKind
    subject_id: str
    phase: ChainPhase
    status_reason: str = ""
    session_refs: dict[str, Any] = field(default_factory=dict)
    artifact_refs: dict[str, Any] = field(default_factory=dict)
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "chain_id": self.chain_id,
            "active_span_id": self.active_span_id,
            "subject_kind": self.subject_kind.value,
            "subject_id": self.subject_id,
            "phase": self.phase.value,
            "status_reason": self.status_reason,
            "session_refs": self.session_refs,
            "artifact_refs": self.artifact_refs,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> RuntimeChainStatus:
        return cls(
            chain_id=str(payload.get("chain_id", "")),
            active_span_id=str(payload.get("active_span_id", "")),
            subject_kind=RuntimeSubjectKind(str(payload.get("subject_kind", "issue"))),
            subject_id=str(payload.get("subject_id", "")),
            phase=ChainPhase(str(payload.get("phase", "started"))),
            status_reason=str(payload.get("status_reason", "")),
            session_refs=dict(payload.get("session_refs") or {}),
            artifact_refs=dict(payload.get("artifact_refs") or {}),
            updated_at=str(payload.get("updated_at", "")),
        )


__all__ = [
    "ChainPhase",
    "RuntimeChainEvent",
    "RuntimeChainStatus",
    "RuntimeSubjectKind",
]
