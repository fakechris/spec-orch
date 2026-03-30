"""Helpers for bridging normalized execution/decision/acceptance signals into evolution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class EvolutionSignalSnapshot:
    """Summarized evolution inputs derived from the current normalized context."""

    execution_signal_count: int = 0
    reviewed_decision_failure_count: int = 0
    reviewed_decision_recipe_count: int = 0
    reviewed_acceptance_finding_count: int = 0
    recent_evolution_journal_count: int = 0

    @property
    def reviewed_evidence_count(self) -> int:
        return (
            self.reviewed_decision_failure_count
            + self.reviewed_decision_recipe_count
            + self.reviewed_acceptance_finding_count
        )

    @property
    def signal_origins(self) -> list[str]:
        origins: list[str] = []
        if self.execution_signal_count:
            origins.append("execution")
        if self.reviewed_decision_failure_count or self.reviewed_decision_recipe_count:
            origins.append("decision_review")
        if self.reviewed_acceptance_finding_count:
            origins.append("acceptance_review")
        if self.recent_evolution_journal_count:
            origins.append("evolution_journal")
        return origins

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_signal_count": self.execution_signal_count,
            "reviewed_decision_failure_count": self.reviewed_decision_failure_count,
            "reviewed_decision_recipe_count": self.reviewed_decision_recipe_count,
            "reviewed_acceptance_finding_count": self.reviewed_acceptance_finding_count,
            "recent_evolution_journal_count": self.recent_evolution_journal_count,
            "reviewed_evidence_count": self.reviewed_evidence_count,
            "signal_origins": self.signal_origins,
        }


def build_evolution_signal_snapshot(context: Any | None) -> EvolutionSignalSnapshot:
    """Build a compact normalized signal summary from a ContextBundle-like object."""
    if context is None:
        return EvolutionSignalSnapshot()

    execution = getattr(context, "execution", None)
    learning = getattr(context, "learning", None)

    execution_signal_count = 0
    if execution is not None:
        if getattr(execution, "verification_results", None) is not None:
            execution_signal_count += 1
        if getattr(execution, "gate_report", None) is not None:
            execution_signal_count += 1

    return EvolutionSignalSnapshot(
        execution_signal_count=execution_signal_count,
        reviewed_decision_failure_count=len(
            getattr(learning, "reviewed_decision_failures", []) or []
        ),
        reviewed_decision_recipe_count=len(
            getattr(learning, "reviewed_decision_recipes", []) or []
        ),
        reviewed_acceptance_finding_count=len(
            getattr(learning, "reviewed_acceptance_findings", []) or []
        ),
        recent_evolution_journal_count=len(getattr(learning, "recent_evolution_journal", []) or []),
    )
