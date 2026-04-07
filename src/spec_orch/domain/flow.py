"""Flow engine domain models: FlowType, FlowStep, FlowGraph, FlowTransitionEvent."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from spec_orch.domain.issue import RunState


class FlowType(StrEnum):
    """Supported workflow tiers aligned with change-management-policy."""

    FULL = "full"
    STANDARD = "standard"
    HOTFIX = "hotfix"


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
