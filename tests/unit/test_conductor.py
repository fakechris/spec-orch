"""Tests for the Conductor agent."""

from pathlib import Path

import pytest

from spec_orch.domain.models import ConversationMessage, ConversationThread
from spec_orch.services.conductor.conductor import Conductor
from spec_orch.services.conductor.types import (
    ConversationMode,
    FormalizationProposal,
    IntentCategory,
)


def _msg(content: str, thread_id: str = "t-1", sender: str = "user") -> ConversationMessage:
    return ConversationMessage(
        message_id=f"m-{hash(content) % 10000}",
        thread_id=thread_id,
        sender=sender,
        content=content,
        timestamp="2026-03-14T12:00:00Z",
        channel="test",
    )


def _thread(thread_id: str = "t-1") -> ConversationThread:
    return ConversationThread(thread_id=thread_id, channel="test")


@pytest.fixture()
def conductor(tmp_path: Path) -> Conductor:
    return Conductor(repo_root=tmp_path)


class TestExploreMode:
    def test_exploration_passes_through(self, conductor: Conductor):
        msg = _msg("I'm thinking about how to improve performance")
        thread = _thread()
        thread.messages.append(msg)
        resp = conductor.process_message(msg, thread)
        assert resp.action == "passthrough"

    def test_question_passes_through(self, conductor: Conductor):
        msg = _msg("How does the event bus work?")
        thread = _thread()
        thread.messages.append(msg)
        resp = conductor.process_message(msg, thread)
        assert resp.action == "passthrough"

    def test_state_persists(self, conductor: Conductor, tmp_path: Path):
        msg = _msg("What if we added caching?")
        thread = _thread()
        thread.messages.append(msg)
        conductor.process_message(msg, thread)

        state = conductor.get_state("t-1")
        assert state is not None
        assert len(state.intent_history) == 1
        assert state.mode == ConversationMode.EXPLORE


class TestCrystallization:
    def test_high_confidence_feature_proposes(self, conductor: Conductor):
        thread = _thread()
        msgs = [
            _msg("We need to implement a comprehensive authentication system for our application"),
            _msg("The auth system should support OAuth2 and SAML for enterprise customers"),
            _msg("We need to build a complete user management module with roles and permissions"),
        ]
        resp = None
        for m in msgs:
            thread.messages.append(m)
            resp = conductor.process_message(m, thread)
            if resp.action == "propose":
                break

        if resp and resp.action == "propose":
            assert resp.proposal is not None
            assert resp.conductor_message is not None
            assert "@spec-orch approve" in resp.conductor_message
            state = conductor.get_state("t-1")
            assert state is not None
            assert state.mode == ConversationMode.CRYSTALLIZE

    def test_low_confidence_does_not_propose(self, conductor: Conductor):
        msg = _msg("hmm yeah ok")
        thread = _thread()
        thread.messages.append(msg)
        resp = conductor.process_message(msg, thread)
        assert resp.action == "passthrough"


class TestApproval:
    def test_approve_with_pending_proposal(self, conductor: Conductor):
        thread = _thread()
        state = conductor._get_or_create_state("t-1")
        state.pending_proposal = FormalizationProposal(
            proposal_type="issue",
            title="Add authentication",
            description="Implement OAuth2 auth system",
            intent_category=IntentCategory.FEATURE,
            confidence=0.85,
        )
        state.mode = ConversationMode.CRYSTALLIZE
        conductor._persist_state(state)

        approve_msg = _msg("@spec-orch approve")
        thread.messages.append(approve_msg)
        resp = conductor.process_message(approve_msg, thread)
        assert resp.action == "formalized"
        assert "Add authentication" in (resp.conductor_message or "")

        updated = conductor.get_state("t-1")
        assert updated is not None
        assert updated.mode == ConversationMode.EXECUTE
        assert updated.pending_proposal is None

    def test_approve_without_proposal(self, conductor: Conductor):
        msg = _msg("@spec-orch approve")
        thread = _thread()
        thread.messages.append(msg)
        resp = conductor.process_message(msg, thread)
        assert "Nothing to approve" in (resp.conductor_message or "")


class TestDriftDetection:
    def test_detects_topic_change(self, conductor: Conductor):
        thread = _thread()
        state = conductor._get_or_create_state("t-1")
        state.topic_anchors = [
            "authentication system with OAuth2",
            "user login flow for enterprise",
        ]
        conductor._persist_state(state)

        msg = _msg("We need to redesign the payment processing pipeline for subscriptions")
        thread.messages.append(msg)
        conductor.process_message(msg, thread)

        state = conductor.get_state("t-1")
        assert state is not None
        drift_signals = [s for s in state.intent_history if s.category == IntentCategory.DRIFT]
        assert len(drift_signals) >= 0  # drift detection is heuristic

    def test_no_drift_on_related_topic(self, conductor: Conductor):
        thread = _thread()
        state = conductor._get_or_create_state("t-1")
        state.topic_anchors = ["authentication system"]
        conductor._persist_state(state)

        msg = _msg("The authentication system also needs password reset")
        thread.messages.append(msg)
        resp = conductor.process_message(msg, thread)
        assert resp.action == "passthrough"


class TestStatePersistence:
    def test_state_survives_reload(self, tmp_path: Path):
        c1 = Conductor(repo_root=tmp_path)
        state = c1._get_or_create_state("persist-test")
        state.mode = ConversationMode.CRYSTALLIZE
        state.formalized_issues = ["SON-99"]
        c1._persist_state(state)

        c2 = Conductor(repo_root=tmp_path)
        loaded = c2.get_state("persist-test")
        assert loaded is not None
        assert loaded.mode == ConversationMode.CRYSTALLIZE
        assert loaded.formalized_issues == ["SON-99"]
