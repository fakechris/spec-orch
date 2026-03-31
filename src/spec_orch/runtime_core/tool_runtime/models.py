from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol


class ToolPermissionClass(StrEnum):
    READ_ONLY = "read_only"
    WORKSPACE_WRITE = "workspace_write"
    SESSION_ADMIN = "session_admin"
    NETWORK = "network"


class ToolConcurrencyClass(StrEnum):
    SERIAL = "serial"
    SAFE_PARALLEL = "safe_parallel"


class ToolAdapter(Protocol):
    def __call__(self, arguments: dict[str, Any]) -> Any: ...


@dataclass(slots=True)
class ToolDefinition:
    name: str
    adapter: ToolAdapter
    aliases: tuple[str, ...] = ()
    required_fields: tuple[str, ...] = ()
    permission_class: ToolPermissionClass = ToolPermissionClass.READ_ONLY
    concurrency_class: ToolConcurrencyClass = ToolConcurrencyClass.SERIAL
    telemetry_label: str = ""


@dataclass(slots=True)
class ToolExecutionRequest:
    tool_name: str
    arguments: dict[str, Any]
    allowed_permissions: set[ToolPermissionClass] | None = None
    telemetry_root: Any = None


@dataclass(slots=True)
class ToolPermissionDecision:
    allowed: bool
    reason: str = ""


@dataclass(slots=True)
class ToolExecutionResult:
    tool_name: str
    success: bool
    output: Any = None
    error: str = ""
    duration_ms: int = 0
    permission: ToolPermissionDecision = field(
        default_factory=lambda: ToolPermissionDecision(allowed=True)
    )


@dataclass(slots=True)
class ToolLifecycleEvent:
    tool_name: str
    phase: str
    success: bool | None = None
    error: str = ""
    duration_ms: int = 0
    telemetry_label: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "phase": self.phase,
            "success": self.success,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "telemetry_label": self.telemetry_label,
            "arguments": self.arguments,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ToolLifecycleEvent:
        return cls(
            tool_name=str(payload.get("tool_name", "")),
            phase=str(payload.get("phase", "")),
            success=payload.get("success"),
            error=str(payload.get("error", "")),
            duration_ms=int(payload.get("duration_ms", 0) or 0),
            telemetry_label=str(payload.get("telemetry_label", "")),
            arguments=dict(payload.get("arguments") or {}),
            metadata=dict(payload.get("metadata") or {}),
        )


ToolBatchPlan = list[list[ToolExecutionRequest]]


__all__ = [
    "ToolAdapter",
    "ToolBatchPlan",
    "ToolConcurrencyClass",
    "ToolDefinition",
    "ToolExecutionRequest",
    "ToolExecutionResult",
    "ToolLifecycleEvent",
    "ToolPermissionClass",
    "ToolPermissionDecision",
]
