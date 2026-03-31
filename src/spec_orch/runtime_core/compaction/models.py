from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def _mapping_or_empty(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


@dataclass(slots=True)
class CompactionTriggerDecision:
    trigger: bool
    reason: str
    threshold: int
    observed_count: int
    posture: str = "standard"
    source_size: int = 0
    effective_budget: int = 0


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

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> CompactionRestoreBundle:
        discovered_tools = payload.get("discovered_tools") or []
        return cls(
            restored_state=_mapping_or_empty(payload.get("restored_state")),
            attachment_refs=_mapping_or_empty(payload.get("attachment_refs")),
            discovered_tools=[
                str(item) for item in discovered_tools if isinstance(item, str) and item.strip()
            ],
        )


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
            restore_bundle=_mapping_or_empty(payload.get("restore_bundle")),
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
            details=_mapping_or_empty(payload.get("details")),
            created_at=str(payload.get("created_at", "")),
        )


@dataclass(slots=True)
class CompactionInputSlice:
    effective_context_window: int
    reserved_output_budget: int
    transcript_size: int
    recent_growth: int = 0
    posture: str = "standard"


@dataclass(slots=True)
class CompactionResult:
    triggered: bool
    boundary: dict[str, Any] = field(default_factory=dict)
    stats: dict[str, Any] = field(default_factory=dict)
    restore_bundle: dict[str, Any] = field(default_factory=dict)
    retries_used: int = 0
    fallback_used: str = ""
    guard_state: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "triggered": self.triggered,
            "boundary": self.boundary,
            "stats": self.stats,
            "restore_bundle": self.restore_bundle,
            "retries_used": self.retries_used,
            "fallback_used": self.fallback_used,
            "guard_state": self.guard_state,
        }
