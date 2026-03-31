"""Graph models for the bounded acceptance runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from spec_orch.acceptance_core.routing import AcceptanceGraphProfile


@dataclass(slots=True)
class AcceptanceGraphStep:
    key: str
    instruction: str
    input_keys: list[str] = field(default_factory=list)
    output_keys: list[str] = field(default_factory=list)
    optional: bool = False


@dataclass(slots=True)
class AcceptanceGraphProfileDefinition:
    profile: AcceptanceGraphProfile
    steps: list[AcceptanceGraphStep]
    supports_compare_overlay: bool = False
    loop_step_key: str = ""
    expected_step_artifacts: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AcceptanceStepInput:
    mission_id: str
    round_id: int
    graph_profile: AcceptanceGraphProfile
    step_key: str
    goal: str
    target: str
    evidence: dict[str, Any] = field(default_factory=dict)
    prior_outputs: dict[str, Any] = field(default_factory=dict)
    compare_overlay: bool = False


@dataclass(slots=True)
class AcceptanceStepResult:
    step_key: str
    decision: str
    outputs: dict[str, Any] = field(default_factory=dict)
    next_transition: str = ""
    warnings: list[str] = field(default_factory=list)
    review_markdown: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_key": self.step_key,
            "decision": self.decision,
            "outputs": dict(self.outputs),
            "next_transition": self.next_transition,
            "warnings": list(self.warnings),
            "review_markdown": self.review_markdown,
            "created_at": self.created_at,
        }


@dataclass(slots=True)
class AcceptanceGraphRun:
    run_id: str
    mission_id: str
    round_id: int
    graph_profile: AcceptanceGraphProfile
    step_keys: list[str]
    compare_overlay: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "mission_id": self.mission_id,
            "round_id": self.round_id,
            "graph_profile": self.graph_profile.value,
            "step_keys": list(self.step_keys),
            "compare_overlay": self.compare_overlay,
            "created_at": self.created_at,
        }
