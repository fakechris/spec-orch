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


class ToolArgumentValidator(Protocol):
    def __call__(self, arguments: dict[str, Any]) -> dict[str, Any]: ...


class ToolActivationPredicate(Protocol):
    def __call__(self, context: dict[str, Any]) -> bool: ...


@dataclass(slots=True)
class ToolDefinition:
    name: str
    adapter: ToolAdapter
    aliases: tuple[str, ...] = ()
    required_fields: tuple[str, ...] = ()
    validator: ToolArgumentValidator | None = None
    permission_class: ToolPermissionClass = ToolPermissionClass.READ_ONLY
    concurrency_class: ToolConcurrencyClass = ToolConcurrencyClass.SERIAL
    telemetry_label: str = ""
    activation_tags: tuple[str, ...] = ()
    activate_when: ToolActivationPredicate | None = None


@dataclass(slots=True)
class ToolExecutionRequest:
    tool_name: str
    arguments: dict[str, Any]
    request_id: str = ""
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
    request_id: str = ""
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


@dataclass(slots=True)
class ToolProgressEvent:
    tool_name: str
    request_id: str
    message: str
    step: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "request_id": self.request_id,
            "message": self.message,
            "step": self.step,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ToolProgressEvent:
        return cls(
            tool_name=str(payload.get("tool_name", "")),
            request_id=str(payload.get("request_id", "")),
            message=str(payload.get("message", "")),
            step=str(payload.get("step", "")),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass(slots=True)
class ToolPairingRecord:
    request_id: str
    tool_name: str
    status: str
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "tool_name": self.tool_name,
            "status": self.status,
            "error": self.error,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ToolPairingRecord:
        return cls(
            request_id=str(payload.get("request_id", "")),
            tool_name=str(payload.get("tool_name", "")),
            status=str(payload.get("status", "")),
            error=str(payload.get("error", "")),
            metadata=dict(payload.get("metadata") or {}),
        )


ToolBatchPlan = list[list[ToolExecutionRequest]]


__all__ = [
    "ToolAdapter",
    "ToolArgumentValidator",
    "ToolActivationPredicate",
    "ToolBatchPlan",
    "ToolConcurrencyClass",
    "ToolDefinition",
    "ToolExecutionRequest",
    "ToolExecutionResult",
    "ToolLifecycleEvent",
    "ToolPairingRecord",
    "ToolPermissionClass",
    "ToolPermissionDecision",
    "ToolProgressEvent",
]
