from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(slots=True)
class CompactionTriggerDecision:
    trigger: bool
    reason: str
    threshold: int
    observed_count: int
    posture: str = "standard"


@dataclass(slots=True)
class CompactionRestoreBundle:
    restored_state: dict[str, Any] = field(default_factory=dict)
    attachment_refs: dict[str, Any] = field(default_factory=dict)
    discovered_tools: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "restored_state": self.restored_state,
            "attachment_refs": self.attachment_refs,
            "discovered_tools": self.discovered_tools,
        }


@dataclass(slots=True)
class CompactionBoundary:
    boundary_id: str
    trigger_reason: str
    restore_bundle: dict[str, Any]
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "boundary_id": self.boundary_id,
            "trigger_reason": self.trigger_reason,
            "restore_bundle": self.restore_bundle,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> CompactionBoundary:
        return cls(
            boundary_id=str(payload.get("boundary_id", "")),
            trigger_reason=str(payload.get("trigger_reason", "")),
            restore_bundle=dict(payload.get("restore_bundle") or {}),
            created_at=str(payload.get("created_at", "")),
        )


@dataclass(slots=True)
class CompactionTelemetryEvent:
    phase: str
    reason: str
    details: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "reason": self.reason,
            "details": self.details,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> CompactionTelemetryEvent:
        return cls(
            phase=str(payload.get("phase", "")),
            reason=str(payload.get("reason", "")),
            details=dict(payload.get("details") or {}),
            created_at=str(payload.get("created_at", "")),
        )
