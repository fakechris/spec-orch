"""Protocol and types for extensible Gate check skills."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from spec_orch.domain.models import GateInput


@dataclass
class CheckResult:
    """Outcome of a single gate check skill execution."""

    passed: bool
    reason: str = ""
    condition_id: str = ""


@runtime_checkable
class GateCheckSkill(Protocol):
    """A single gate condition implemented as a pluggable skill."""

    @property
    def id(self) -> str: ...

    @property
    def description(self) -> str: ...

    def run(self, gate_input: GateInput) -> CheckResult: ...


class GateSkillRegistry:
    """Registry for builtin and custom gate check skills."""

    def __init__(self) -> None:
        self._builtin: dict[str, GateCheckSkill] = {}
        self._custom: dict[str, GateCheckSkill] = {}

    def register_builtin(self, skill: GateCheckSkill) -> None:
        self._builtin[skill.id] = skill

    def register(self, skill: GateCheckSkill) -> None:
        self._custom[skill.id] = skill

    def get(self, condition_id: str) -> GateCheckSkill | None:
        return self._custom.get(condition_id) or self._builtin.get(condition_id)

    def all_ids(self) -> set[str]:
        return set(self._builtin) | set(self._custom)
