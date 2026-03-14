"""Core types for the Conductor — progressive formalization layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class ConversationMode(StrEnum):
    """Which phase the conversation is in."""

    EXPLORE = "explore"
    CRYSTALLIZE = "crystallize"
    EXECUTE = "execute"


class IntentCategory(StrEnum):
    """Classification of a single user message's intent."""

    EXPLORATION = "exploration"
    QUESTION = "question"
    QUICK_FIX = "quick_fix"
    FEATURE = "feature"
    BUG = "bug"
    DRIFT = "drift"


ACTIONABLE_INTENTS = frozenset(
    {
        IntentCategory.QUICK_FIX,
        IntentCategory.FEATURE,
        IntentCategory.BUG,
    }
)

ACTIONABLE_CONFIDENCE_THRESHOLD = 0.6


@dataclass
class IntentSignal:
    """Result of classifying a single message."""

    category: IntentCategory
    confidence: float
    summary: str = ""
    suggested_title: str = ""
    reasoning: str = ""

    def is_actionable(self) -> bool:
        return (
            self.category in ACTIONABLE_INTENTS
            and self.confidence >= ACTIONABLE_CONFIDENCE_THRESHOLD
        )


@dataclass
class ConductorState:
    """Running state of a Conductor session tied to a conversation thread.

    Tracks the current mode, accumulated intent signals, and any
    formalization proposals that have been offered to the user.
    """

    thread_id: str
    mode: ConversationMode = ConversationMode.EXPLORE
    intent_history: list[IntentSignal] = field(default_factory=list)
    topic_anchors: list[str] = field(default_factory=list)
    pending_proposal: FormalizationProposal | None = None
    formalized_issues: list[str] = field(default_factory=list)
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "thread_id": self.thread_id,
            "mode": self.mode.value,
            "intent_history": [
                {
                    "category": s.category.value,
                    "confidence": s.confidence,
                    "summary": s.summary,
                    "suggested_title": s.suggested_title,
                }
                for s in self.intent_history
            ],
            "topic_anchors": self.topic_anchors,
            "formalized_issues": self.formalized_issues,
            "updated_at": self.updated_at,
        }
        if self.pending_proposal is not None:
            result["pending_proposal"] = {
                "proposal_type": self.pending_proposal.proposal_type,
                "title": self.pending_proposal.title,
                "description": self.pending_proposal.description,
                "intent_category": self.pending_proposal.intent_category.value,
                "confidence": self.pending_proposal.confidence,
            }
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConductorState:
        signals = [
            IntentSignal(
                category=IntentCategory(s["category"]),
                confidence=s.get("confidence", 0.5),
                summary=s.get("summary", ""),
                suggested_title=s.get("suggested_title", ""),
            )
            for s in data.get("intent_history", [])
        ]
        proposal: FormalizationProposal | None = None
        raw_proposal = data.get("pending_proposal")
        if raw_proposal is not None:
            proposal = FormalizationProposal(
                proposal_type=raw_proposal["proposal_type"],
                title=raw_proposal["title"],
                description=raw_proposal.get("description", ""),
                intent_category=IntentCategory(raw_proposal.get("intent_category", "feature")),
                confidence=raw_proposal.get("confidence", 0.5),
            )
        return cls(
            thread_id=data["thread_id"],
            mode=ConversationMode(data.get("mode", "explore")),
            intent_history=signals,
            topic_anchors=data.get("topic_anchors", []),
            pending_proposal=proposal,
            formalized_issues=data.get("formalized_issues", []),
            updated_at=data.get("updated_at", datetime.now(UTC).isoformat()),
        )


@dataclass
class FormalizationProposal:
    """A proposed conversion from conversation to structured work."""

    proposal_type: str  # "issue", "epic", "quick_fix"
    title: str
    description: str
    intent_category: IntentCategory
    confidence: float

    def format_for_user(self) -> str:
        kind = {
            "issue": "Issue",
            "epic": "Epic",
            "quick_fix": "Quick Fix",
        }.get(self.proposal_type, self.proposal_type)
        lines = [
            f"I think this conversation has crystallized into a **{kind}**:",
            "",
            f"**{self.title}**",
            "",
            self.description,
            "",
            "Reply `@spec-orch approve` to create it, or keep discussing to refine further.",
        ]
        return "\n".join(lines)
