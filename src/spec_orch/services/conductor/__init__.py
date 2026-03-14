"""Conductor — progressive formalization layer for spec-orch.

Bridges free-form conversation and the structured lifecycle pipeline
by classifying user intent and proposing formalization when actionable
work crystallizes from discussion.
"""

from spec_orch.services.conductor.conductor import Conductor, ConductorResponse
from spec_orch.services.conductor.intent_classifier import classify_intent
from spec_orch.services.conductor.types import (
    ACTIONABLE_INTENTS,
    ConductorState,
    ConversationMode,
    FormalizationProposal,
    IntentCategory,
    IntentSignal,
)

__all__ = [
    "ACTIONABLE_INTENTS",
    "Conductor",
    "ConductorResponse",
    "ConductorState",
    "ConversationMode",
    "FormalizationProposal",
    "IntentCategory",
    "IntentSignal",
    "classify_intent",
]
