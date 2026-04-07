"""Evolution lifecycle domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class EvolutionChangeType(StrEnum):
    """Types of change an evolver can propose."""

    PROMPT_VARIANT = "prompt_variant"
    SCOPER_HINT = "scoper_hint"
    POLICY = "policy"
    HARNESS_RULE = "harness_rule"
    CONFIG_SUGGESTION = "config_suggestion"


class EvolutionValidationMethod(StrEnum):
    """How a proposal was validated."""

    AB_COMPARE = "a_b_compare"
    BACKTEST = "backtest"
    RULE_VALIDATOR = "rule_validator"
    EVAL_RUNNER = "eval_runner"
    AUTO = "auto"


@dataclass
class EvolutionProposal:
    """One proposed evolution change, produced by an evolver."""

    proposal_id: str
    evolver_name: str
    change_type: EvolutionChangeType
    content: dict[str, Any] = field(default_factory=dict)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.5
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self, *, include_content: bool = True) -> dict[str, Any]:
        d: dict[str, Any] = {
            "proposal_id": self.proposal_id,
            "evolver_name": self.evolver_name,
            "change_type": self.change_type.value,
            "evidence_count": len(self.evidence),
            "confidence": self.confidence,
            "created_at": self.created_at,
        }
        if include_content:
            d["content"] = self.content
        return d


@dataclass
class EvolutionOutcome:
    """Result of validating a proposal."""

    proposal_id: str
    accepted: bool
    validation_method: EvolutionValidationMethod = EvolutionValidationMethod.AUTO
    metrics: dict[str, float] = field(default_factory=dict)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "accepted": self.accepted,
            "validation_method": self.validation_method.value,
            "metrics": self.metrics,
            "reason": self.reason,
        }
