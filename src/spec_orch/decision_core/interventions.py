"""Intervention primitives for human-required decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from spec_orch.decision_core.models import DecisionRecord


class InterventionStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class Intervention:
    intervention_id: str
    point_key: str
    summary: str
    questions: list[str] = field(default_factory=list)
    status: InterventionStatus = InterventionStatus.OPEN
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "intervention_id": self.intervention_id,
            "point_key": self.point_key,
            "summary": self.summary,
            "questions": list(self.questions),
            "status": self.status.value,
            "created_at": self.created_at,
        }


def build_intervention_from_record(
    record: DecisionRecord,
    *,
    intervention_id: str,
    summary: str | None = None,
) -> Intervention:
    return Intervention(
        intervention_id=intervention_id,
        point_key=record.point_key,
        summary=summary or record.summary,
        questions=list(record.blocking_questions),
    )


__all__ = [
    "Intervention",
    "InterventionStatus",
    "build_intervention_from_record",
]
