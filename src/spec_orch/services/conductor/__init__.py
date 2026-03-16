"""Conductor — progressive formalization layer for spec-orch.

Bridges free-form conversation and the structured lifecycle pipeline
by classifying user intent and proposing formalization when actionable
work crystallizes from discussion.
"""

from spec_orch.services.conductor.conductor import (
    APPROVE_RE_PATTERN,
    Conductor,
    ConductorAction,
    ConductorResponse,
)
from spec_orch.services.conductor.intent_classifier import classify_intent
from spec_orch.services.conductor.types import (
    ACTIONABLE_CONFIDENCE_THRESHOLD,
    ACTIONABLE_INTENTS,
    ConductorState,
    ConversationMode,
    DMAStage,
    FormalizationProposal,
    IntentCategory,
    IntentSignal,
    InterceptAction,
    InterceptResult,
    UserInputSource,
)

__all__ = [
    "ACTIONABLE_CONFIDENCE_THRESHOLD",
    "ACTIONABLE_INTENTS",
    "APPROVE_RE_PATTERN",
    "Conductor",
    "ConductorAction",
    "ConductorResponse",
    "ConductorState",
    "ConversationMode",
    "DMAStage",
    "FormalizationProposal",
    "IntentCategory",
    "IntentSignal",
    "InterceptAction",
    "InterceptResult",
    "UserInputSource",
    "classify_intent",
]
