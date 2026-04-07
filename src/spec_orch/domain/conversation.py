"""Conversation and spec-related domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from spec_orch.domain.issue import Issue


@dataclass(slots=True)
class Question:
    """A question raised during planning or execution."""

    id: str
    asked_by: str
    target: str
    category: str
    blocking: bool
    text: str
    answer: str | None = None
    answered_by: str | None = None


@dataclass(slots=True)
class Decision:
    """A formal answer to a Question."""

    question_id: str
    answer: str
    decided_by: str
    timestamp: str


@dataclass
class SpecSnapshot:
    """Frozen, approved specification consumed by the builder."""

    version: int
    approved: bool
    approved_by: str | None
    issue: Issue
    questions: list[Question] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)

    def has_unresolved_blocking_questions(self) -> bool:
        blocking_ids = {q.id for q in self.questions if q.blocking}
        answered_ids = {d.question_id for d in self.decisions}
        return bool(blocking_ids - answered_ids)


@dataclass(slots=True)
class PlannerResult:
    """Output of a PlannerAdapter.plan() call."""

    questions: list[Question]
    spec_draft: SpecSnapshot | None = None
    raw_response: str = ""


class ThreadStatus(StrEnum):
    """Lifecycle states for a conversation thread."""

    ACTIVE = "active"
    FROZEN = "frozen"
    ARCHIVED = "archived"


@dataclass
class ConversationMessage:
    """A single message in a discussion thread — channel-agnostic."""

    message_id: str
    thread_id: str
    sender: str
    content: str
    timestamp: str
    channel: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversationThread:
    """Persistent state for a multi-turn brainstorming discussion."""

    thread_id: str
    channel: str
    mission_id: str | None = None
    messages: list[ConversationMessage] = field(default_factory=list)
    status: ThreadStatus = ThreadStatus.ACTIVE
    spec_snapshot: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class DeviationSeverity(StrEnum):
    MINOR = "minor"
    MAJOR = "major"
    BLOCKING = "blocking"


class DeviationResolution(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    SPEC_AMENDED = "spec_amended"
    REVERTED = "reverted"


@dataclass(slots=True)
class SpecDeviation:
    """Records how execution diverged from the approved spec."""

    deviation_id: str
    issue_id: str
    mission_id: str = ""
    description: str = ""
    severity: str = DeviationSeverity.MINOR
    resolution: str = DeviationResolution.PENDING
    detected_by: str = "gate"
    file_path: str | None = None
