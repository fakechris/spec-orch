"""Canonical home for decision-core models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class DecisionAuthority(StrEnum):
    RULE_OWNED = "rule_owned"
    LLM_OWNED = "llm_owned"
    HUMAN_REQUIRED = "human_required"


@dataclass(slots=True)
class DecisionPoint:
    key: str
    authority: DecisionAuthority
    owner: str
    summary: str
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "authority": self.authority.value,
            "owner": self.owner,
            "summary": self.summary,
            "description": self.description,
        }


@dataclass(slots=True)
class DecisionRecord:
    record_id: str
    point_key: str
    authority: DecisionAuthority
    owner: str
    selected_action: str
    summary: str
    rationale: str = ""
    confidence: float | None = None
    context_artifacts: list[str] = field(default_factory=list)
    blocking_questions: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "point_key": self.point_key,
            "authority": self.authority.value,
            "owner": self.owner,
            "selected_action": self.selected_action,
            "summary": self.summary,
            "rationale": self.rationale,
            "confidence": self.confidence,
            "context_artifacts": list(self.context_artifacts),
            "blocking_questions": list(self.blocking_questions),
            "created_at": self.created_at,
        }


@dataclass(slots=True)
class DecisionReview:
    review_id: str
    record_id: str
    reviewer_kind: str
    verdict: str
    summary: str
    recommended_authority: DecisionAuthority | None = None
    escalate_to_human: bool = False
    reflection: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "record_id": self.record_id,
            "reviewer_kind": self.reviewer_kind,
            "verdict": self.verdict,
            "summary": self.summary,
            "recommended_authority": (
                self.recommended_authority.value
                if self.recommended_authority is not None
                else None
            ),
            "escalate_to_human": self.escalate_to_human,
            "reflection": self.reflection,
            "created_at": self.created_at,
        }


__all__ = [
    "DecisionAuthority",
    "DecisionPoint",
    "DecisionRecord",
    "DecisionReview",
]
