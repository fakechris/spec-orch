from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _int_value(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _string_dict(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items()}


def _object_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


@dataclass(slots=True)
class RuntimeBudgetVisibility:
    budget_key: str
    planned_steps: int
    completed_steps: int
    remaining_steps: int
    loop_budget: int = 0
    remaining_loop_budget: int = 0

    def to_dict(self) -> dict[str, int | str]:
        return {
            "budget_key": self.budget_key,
            "planned_steps": self.planned_steps,
            "completed_steps": self.completed_steps,
            "remaining_steps": self.remaining_steps,
            "loop_budget": self.loop_budget,
            "remaining_loop_budget": self.remaining_loop_budget,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> RuntimeBudgetVisibility:
        return cls(
            budget_key=str(payload.get("budget_key", "")),
            planned_steps=_int_value(payload.get("planned_steps", 0)),
            completed_steps=_int_value(payload.get("completed_steps", 0)),
            remaining_steps=_int_value(payload.get("remaining_steps", 0)),
            loop_budget=_int_value(payload.get("loop_budget", 0)),
            remaining_loop_budget=_int_value(payload.get("remaining_loop_budget", 0)),
        )


@dataclass(slots=True)
class RuntimeStallSignal:
    stalled: bool = False
    idle_seconds: int = 0
    reason: str = ""

    def to_dict(self) -> dict[str, bool | int | str]:
        return {
            "stalled": self.stalled,
            "idle_seconds": self.idle_seconds,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> RuntimeStallSignal:
        return cls(
            stalled=bool(payload.get("stalled", False)),
            idle_seconds=_int_value(payload.get("idle_seconds", 0)),
            reason=str(payload.get("reason", "")),
        )


@dataclass(slots=True)
class RuntimeProgressEvent:
    subject_key: str
    phase: str
    step_key: str
    message: str
    budget: RuntimeBudgetVisibility
    stall_signal: RuntimeStallSignal = field(default_factory=RuntimeStallSignal)
    artifact_refs: dict[str, str] = field(default_factory=dict)
    updated_at: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "subject_key": self.subject_key,
            "phase": self.phase,
            "step_key": self.step_key,
            "message": self.message,
            "budget": self.budget.to_dict(),
            "stall_signal": self.stall_signal.to_dict(),
            "artifact_refs": self.artifact_refs,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> RuntimeProgressEvent:
        return cls(
            subject_key=str(payload.get("subject_key", "")),
            phase=str(payload.get("phase", "")),
            step_key=str(payload.get("step_key", "")),
            message=str(payload.get("message", "")),
            budget=RuntimeBudgetVisibility.from_dict(_object_dict(payload.get("budget"))),
            stall_signal=RuntimeStallSignal.from_dict(_object_dict(payload.get("stall_signal"))),
            artifact_refs=_string_dict(payload.get("artifact_refs")),
            updated_at=str(payload.get("updated_at", "")),
        )


@dataclass(slots=True)
class RuntimeLiveSummary:
    subject_key: str
    phase: str
    status_reason: str
    current_step_key: str
    budget: RuntimeBudgetVisibility
    stall_signal: RuntimeStallSignal = field(default_factory=RuntimeStallSignal)
    artifact_refs: dict[str, str] = field(default_factory=dict)
    updated_at: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "subject_key": self.subject_key,
            "phase": self.phase,
            "status_reason": self.status_reason,
            "current_step_key": self.current_step_key,
            "budget": self.budget.to_dict(),
            "stall_signal": self.stall_signal.to_dict(),
            "artifact_refs": self.artifact_refs,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> RuntimeLiveSummary:
        return cls(
            subject_key=str(payload.get("subject_key", "")),
            phase=str(payload.get("phase", "")),
            status_reason=str(payload.get("status_reason", "")),
            current_step_key=str(payload.get("current_step_key", "")),
            budget=RuntimeBudgetVisibility.from_dict(_object_dict(payload.get("budget"))),
            stall_signal=RuntimeStallSignal.from_dict(_object_dict(payload.get("stall_signal"))),
            artifact_refs=_string_dict(payload.get("artifact_refs")),
            updated_at=str(payload.get("updated_at", "")),
        )


@dataclass(slots=True)
class RuntimeRecap:
    subject_key: str
    title: str
    bullets: list[str]
    artifact_refs: dict[str, str] = field(default_factory=dict)
    updated_at: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "subject_key": self.subject_key,
            "title": self.title,
            "bullets": list(self.bullets),
            "artifact_refs": self.artifact_refs,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> RuntimeRecap:
        bullets = payload.get("bullets") or []
        return cls(
            subject_key=str(payload.get("subject_key", "")),
            title=str(payload.get("title", "")),
            bullets=[str(item) for item in bullets] if isinstance(bullets, list) else [],
            artifact_refs=_string_dict(payload.get("artifact_refs")),
            updated_at=str(payload.get("updated_at", "")),
        )
