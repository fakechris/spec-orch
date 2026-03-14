"""Tests for the intent classifier (rule-based fallback)."""

from spec_orch.services.conductor.intent_classifier import classify_intent
from spec_orch.services.conductor.types import IntentCategory


class TestRuleClassifier:
    """Test the rule-based fallback classifier (no planner)."""

    def test_question_detected(self):
        sig = classify_intent("How does the authentication module work?")
        assert sig.category == IntentCategory.QUESTION

    def test_question_mark(self):
        sig = classify_intent("Can you explain the deployment process?")
        assert sig.category == IntentCategory.QUESTION

    def test_bug_detected(self):
        sig = classify_intent("The login page is broken when using Safari. It crashes on submit.")
        assert sig.category == IntentCategory.BUG

    def test_feature_detected(self):
        sig = classify_intent(
            "We need to implement a caching layer to improve performance of API responses."
        )
        assert sig.category == IntentCategory.FEATURE

    def test_quick_fix_short_message(self):
        sig = classify_intent("rename the config variable")
        assert sig.category == IntentCategory.QUICK_FIX

    def test_exploration_detected(self):
        sig = classify_intent("I'm thinking about maybe adding a dashboard")
        assert sig.category == IntentCategory.EXPLORATION

    def test_vague_defaults_to_exploration(self):
        sig = classify_intent("hmm yeah that looks good")
        assert sig.category == IntentCategory.EXPLORATION

    def test_confidence_below_one(self):
        sig = classify_intent("add a new feature for users")
        assert 0.0 <= sig.confidence <= 1.0

    def test_summary_populated(self):
        msg = "We need a better error handling system"
        sig = classify_intent(msg)
        assert sig.summary
        assert len(sig.summary) <= 100

    def test_feature_needs_length(self):
        sig = classify_intent("add x")
        assert sig.category != IntentCategory.FEATURE

    def test_bug_needs_length(self):
        sig = classify_intent("bug")
        assert sig.category != IntentCategory.BUG
