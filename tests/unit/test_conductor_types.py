"""Tests for Conductor types."""

from spec_orch.services.conductor.types import (
    ACTIONABLE_INTENTS,
    ConductorState,
    ConversationMode,
    FormalizationProposal,
    IntentCategory,
    IntentSignal,
)


class TestIntentCategory:
    def test_values(self):
        assert IntentCategory.EXPLORATION == "exploration"
        assert IntentCategory.FEATURE == "feature"
        assert IntentCategory.BUG == "bug"
        assert IntentCategory.QUICK_FIX == "quick_fix"
        assert IntentCategory.QUESTION == "question"
        assert IntentCategory.DRIFT == "drift"

    def test_actionable_set(self):
        assert IntentCategory.FEATURE in ACTIONABLE_INTENTS
        assert IntentCategory.BUG in ACTIONABLE_INTENTS
        assert IntentCategory.QUICK_FIX in ACTIONABLE_INTENTS
        assert IntentCategory.EXPLORATION not in ACTIONABLE_INTENTS
        assert IntentCategory.QUESTION not in ACTIONABLE_INTENTS


class TestIntentSignal:
    def test_actionable_high_confidence(self):
        sig = IntentSignal(category=IntentCategory.FEATURE, confidence=0.8)
        assert sig.is_actionable()

    def test_not_actionable_low_confidence(self):
        sig = IntentSignal(category=IntentCategory.FEATURE, confidence=0.4)
        assert not sig.is_actionable()

    def test_exploration_never_actionable(self):
        sig = IntentSignal(category=IntentCategory.EXPLORATION, confidence=0.99)
        assert not sig.is_actionable()


class TestConversationMode:
    def test_values(self):
        assert ConversationMode.EXPLORE == "explore"
        assert ConversationMode.CRYSTALLIZE == "crystallize"
        assert ConversationMode.EXECUTE == "execute"


class TestConductorState:
    def test_roundtrip(self):
        state = ConductorState(
            thread_id="t-1",
            mode=ConversationMode.CRYSTALLIZE,
            intent_history=[
                IntentSignal(
                    category=IntentCategory.FEATURE,
                    confidence=0.8,
                    summary="Need auth module",
                    suggested_title="Add auth",
                ),
            ],
            topic_anchors=["auth", "login"],
            formalized_issues=["SON-10"],
        )
        d = state.to_dict()
        restored = ConductorState.from_dict(d)
        assert restored.thread_id == "t-1"
        assert restored.mode == ConversationMode.CRYSTALLIZE
        assert len(restored.intent_history) == 1
        assert restored.intent_history[0].category == IntentCategory.FEATURE
        assert restored.topic_anchors == ["auth", "login"]
        assert restored.formalized_issues == ["SON-10"]
        assert restored.pending_proposal is None

    def test_roundtrip_with_pending_proposal(self):
        proposal = FormalizationProposal(
            proposal_type="epic",
            title="Refactor auth",
            description="Full auth overhaul",
            intent_category=IntentCategory.FEATURE,
            confidence=0.92,
        )
        state = ConductorState(
            thread_id="t-2",
            mode=ConversationMode.CRYSTALLIZE,
            pending_proposal=proposal,
        )
        d = state.to_dict()
        assert "pending_proposal" in d
        assert d["pending_proposal"]["title"] == "Refactor auth"

        restored = ConductorState.from_dict(d)
        assert restored.pending_proposal is not None
        assert restored.pending_proposal.title == "Refactor auth"
        assert restored.pending_proposal.proposal_type == "epic"
        assert restored.pending_proposal.intent_category == IntentCategory.FEATURE
        assert restored.pending_proposal.confidence == 0.92


class TestFormalizationProposal:
    def test_format_for_user(self):
        proposal = FormalizationProposal(
            proposal_type="issue",
            title="Add login page",
            description="Users need a login page with OAuth support.",
            intent_category=IntentCategory.FEATURE,
            confidence=0.85,
        )
        text = proposal.format_for_user()
        assert "Issue" in text
        assert "Add login page" in text
        assert "@spec-orch approve" in text
