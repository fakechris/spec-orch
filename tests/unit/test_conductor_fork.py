"""Tests for Conductor fork logic (Change 02)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from spec_orch.domain.models import ConversationMessage, ConversationThread
from spec_orch.services.conductor.conductor import Conductor
from spec_orch.services.conductor.types import (
    ConductorState,
    ConversationMode,
    ForkResult,
    IntentCategory,
    IntentSignal,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _msg(
    content: str,
    thread_id: str = "t-fork",
    sender: str = "user",
    message_id: str = "",
) -> ConversationMessage:
    return ConversationMessage(
        message_id=message_id or f"m-{hash(content) % 10000}",
        thread_id=thread_id,
        sender=sender,
        content=content,
        timestamp="2026-03-14T12:00:00Z",
        channel="test",
    )


def _thread(
    thread_id: str = "t-fork", messages: list[ConversationMessage] | None = None
) -> ConversationThread:
    t = ConversationThread(thread_id=thread_id, channel="test")
    if messages:
        t.messages.extend(messages)
    return t


def _make_conductor(
    tmp_path: Path,
    *,
    linear_client: Any = None,
    event_bus: Any = None,
    fork_enabled: bool = True,
) -> Conductor:
    env_patch = {"SPEC_ORCH_FORK_ENABLED": "true" if fork_enabled else "false"}
    with patch.dict("os.environ", env_patch):
        return Conductor(
            repo_root=tmp_path,
            linear_client=linear_client,
            event_bus=event_bus,
            fork_team_key="SON",
        )


def _mock_linear_client(identifier: str = "SON-999") -> MagicMock:
    client = MagicMock()
    client.create_issue.return_value = {"identifier": identifier, "id": "uuid-1", "title": "test"}
    return client


# ---------------------------------------------------------------------------
# ForkResult type
# ---------------------------------------------------------------------------


class TestForkResult:
    def test_defaults(self):
        r = ForkResult(forked=False)
        assert r.forked is False
        assert r.linear_issue_id == ""
        assert r.title == ""
        assert r.error == ""

    def test_success(self):
        r = ForkResult(forked=True, linear_issue_id="SON-42", title="Fix payment")
        assert r.forked is True
        assert r.linear_issue_id == "SON-42"


# ---------------------------------------------------------------------------
# ConductorState serialization with forked_intent_ids
# ---------------------------------------------------------------------------


class TestConductorStateFork:
    def test_to_dict_includes_forked(self):
        state = ConductorState(thread_id="t-1", forked_intent_ids=["abc123"])
        d = state.to_dict()
        assert d["forked_intent_ids"] == ["abc123"]

    def test_from_dict_round_trip(self):
        state = ConductorState(thread_id="t-1", forked_intent_ids=["abc123", "def456"])
        d = state.to_dict()
        restored = ConductorState.from_dict(d)
        assert restored.forked_intent_ids == ["abc123", "def456"]

    def test_from_dict_missing_field_defaults(self):
        state = ConductorState.from_dict({"thread_id": "t-1"})
        assert state.forked_intent_ids == []


# ---------------------------------------------------------------------------
# _maybe_fork direct tests
# ---------------------------------------------------------------------------


class TestMaybeForkDirect:
    def test_fork_with_linear_client(self, tmp_path: Path):
        client = _mock_linear_client("SON-100")
        c = _make_conductor(tmp_path, linear_client=client)
        state = ConductorState(thread_id="t-1")
        signal = IntentSignal(
            category=IntentCategory.BUG,
            confidence=0.8,
            summary="Payment refund logic broken",
        )
        thread = _thread("t-1", [_msg("fix refund", "t-1")])

        result = c._maybe_fork(state, signal, thread)

        assert result.forked is True
        assert result.linear_issue_id == "SON-100"
        client.create_issue.assert_called_once()

    def test_fork_disabled(self, tmp_path: Path):
        c = _make_conductor(tmp_path, fork_enabled=False)
        state = ConductorState(thread_id="t-1")
        signal = IntentSignal(category=IntentCategory.BUG, confidence=0.8, summary="bug")
        result = c._maybe_fork(state, signal, _thread())
        assert result.forked is False

    def test_fork_dedup_same_signal(self, tmp_path: Path):
        client = _mock_linear_client()
        c = _make_conductor(tmp_path, linear_client=client)
        state = ConductorState(thread_id="t-1")
        signal = IntentSignal(category=IntentCategory.BUG, confidence=0.8, summary="same bug")
        thread = _thread("t-1", [_msg("bug report", "t-1")])

        r1 = c._maybe_fork(state, signal, thread)
        assert r1.forked is True

        r2 = c._maybe_fork(state, signal, thread)
        assert r2.forked is False
        assert client.create_issue.call_count == 1

    def test_fork_debounce_within_window(self, tmp_path: Path):
        client = _mock_linear_client()
        c = _make_conductor(tmp_path, linear_client=client)
        state = ConductorState(thread_id="t-1")
        thread = _thread("t-1", [_msg("msg", "t-1")])

        s1 = IntentSignal(category=IntentCategory.BUG, confidence=0.8, summary="bug A")
        r1 = c._maybe_fork(state, s1, thread)
        assert r1.forked is True

        s2 = IntentSignal(category=IntentCategory.FEATURE, confidence=0.9, summary="feature B")
        r2 = c._maybe_fork(state, s2, thread)
        assert r2.forked is False

    def test_fork_no_linear_falls_back_to_local(self, tmp_path: Path):
        c = _make_conductor(tmp_path, linear_client=None)
        state = ConductorState(thread_id="t-1")
        signal = IntentSignal(category=IntentCategory.BUG, confidence=0.8, summary="offline bug")
        thread = _thread("t-1", [_msg("report", "t-1")])

        result = c._maybe_fork(state, signal, thread)

        assert result.forked is True
        assert result.linear_issue_id == ""
        forks_path = tmp_path / ".spec_orch_conductor" / "forks.jsonl"
        assert forks_path.exists()
        data = json.loads(forks_path.read_text().strip())
        assert data["thread_id"] == "t-1"
        assert data["title"] == "offline bug"

    def test_fork_linear_failure_logs_and_continues(self, tmp_path: Path):
        client = MagicMock()
        client.create_issue.side_effect = RuntimeError("network error")
        c = _make_conductor(tmp_path, linear_client=client)
        state = ConductorState(thread_id="t-1")
        signal = IntentSignal(category=IntentCategory.BUG, confidence=0.8, summary="bug")
        thread = _thread("t-1", [_msg("msg", "t-1")])

        result = c._maybe_fork(state, signal, thread)
        assert result.forked is True
        assert result.error != ""
        forks_path = tmp_path / ".spec_orch_conductor" / "forks.jsonl"
        assert forks_path.exists()

    def test_fork_title_fallback(self, tmp_path: Path):
        c = _make_conductor(tmp_path, linear_client=None)
        state = ConductorState(thread_id="t-1")
        signal = IntentSignal(category=IntentCategory.BUG, confidence=0.8, summary="")
        thread = _thread("t-1", [_msg("x", "t-1")])

        result = c._maybe_fork(state, signal, thread)
        assert result.title == "Forked from conversation"


# ---------------------------------------------------------------------------
# EventBus integration
# ---------------------------------------------------------------------------


class TestForkEventBus:
    def test_event_published_on_fork(self, tmp_path: Path):
        bus = MagicMock()
        c = _make_conductor(tmp_path, linear_client=_mock_linear_client(), event_bus=bus)
        state = ConductorState(thread_id="t-1")
        signal = IntentSignal(category=IntentCategory.BUG, confidence=0.8, summary="bug")
        c._maybe_fork(state, signal, _thread("t-1", [_msg("m", "t-1")]))

        bus.publish.assert_called_once()
        event = bus.publish.call_args[0][0]
        assert event.payload["action"] == "fork"
        assert event.payload["thread_id"] == "t-1"

    def test_no_event_bus_no_error(self, tmp_path: Path):
        c = _make_conductor(tmp_path, event_bus=None, linear_client=_mock_linear_client())
        state = ConductorState(thread_id="t-1")
        signal = IntentSignal(category=IntentCategory.BUG, confidence=0.8, summary="bug")
        result = c._maybe_fork(state, signal, _thread("t-1", [_msg("m", "t-1")]))
        assert result.forked is True


# ---------------------------------------------------------------------------
# Integration: fork triggered via process_message
# ---------------------------------------------------------------------------


class TestForkViaProcessMessage:
    def _setup_drift_conductor(self, tmp_path: Path, linear_client: Any = None) -> Conductor:
        """Pre-populate state with topic anchors so drift can trigger."""
        c = _make_conductor(tmp_path, linear_client=linear_client)
        state = c._get_or_create_state("t-drift")
        state.topic_anchors = [
            "login page redesign details",
            "login page authentication flow",
            "login page CSS styling improvements",
        ]
        c._persist_state(state)
        return c

    def test_drift_triggers_fork(self, tmp_path: Path):
        client = _mock_linear_client("SON-201")
        c = self._setup_drift_conductor(tmp_path, linear_client=client)

        msg = _msg(
            "payment refund module has critical bugs in production",
            thread_id="t-drift",
        )
        thread = _thread("t-drift", [msg])
        c.process_message(msg, thread)

        state = c.get_state("t-drift")
        assert state is not None
        assert len(state.forked_intent_ids) >= 1
        client.create_issue.assert_called()

    def test_drift_does_not_change_mode(self, tmp_path: Path):
        client = _mock_linear_client()
        c = self._setup_drift_conductor(tmp_path, linear_client=client)

        msg = _msg("payment refund issues in production", thread_id="t-drift")
        thread = _thread("t-drift", [msg])

        state_before = c.get_state("t-drift")
        mode_before = state_before.mode if state_before else ConversationMode.EXPLORE

        c.process_message(msg, thread)

        state_after = c.get_state("t-drift")
        assert state_after is not None
        assert state_after.mode == mode_before

    def test_new_actionable_in_execute_triggers_fork(self, tmp_path: Path):
        client = _mock_linear_client("SON-301")
        c = _make_conductor(tmp_path, linear_client=client)

        state = c._get_or_create_state("t-exec")
        state.mode = ConversationMode.EXECUTE
        state.topic_anchors = ["fix CSV encoding"] * 3
        state.intent_history = [
            IntentSignal(
                category=IntentCategory.QUICK_FIX, confidence=0.9, summary="fix CSV encoding"
            ),
        ]
        c._persist_state(state)

        msg = _msg(
            "we should also add a dark mode feature to the settings page",
            thread_id="t-exec",
        )
        thread = _thread("t-exec", [msg])
        resp = c.process_message(msg, thread)

        assert resp.action == "passthrough"
        updated = c.get_state("t-exec")
        assert updated is not None
        assert updated.mode == ConversationMode.EXECUTE

    def test_fork_nested_serial(self, tmp_path: Path):
        """S7.2: Multiple forks in one message are handled serially without nesting."""
        client = _mock_linear_client()
        c = _make_conductor(tmp_path, linear_client=client)

        state = c._get_or_create_state("t-serial")
        state.topic_anchors = [
            "database migration planning",
            "database schema optimization",
        ]
        c._persist_state(state)

        msg = _msg(
            "actually we need to redesign the entire payment system",
            thread_id="t-serial",
        )
        thread = _thread("t-serial", [msg])
        resp = c.process_message(msg, thread)
        assert resp.action == "passthrough"


# ---------------------------------------------------------------------------
# Description template
# ---------------------------------------------------------------------------


class TestForkDescription:
    def test_description_contains_required_fields(self, tmp_path: Path):
        c = _make_conductor(tmp_path)
        state = ConductorState(thread_id="t-desc")
        signal = IntentSignal(category=IntentCategory.BUG, confidence=0.8, summary="refund broken")
        messages = [_msg(f"message {i}", "t-desc") for i in range(7)]
        thread = _thread("t-desc", messages)

        desc = c._build_fork_description(state, signal, thread)
        assert "Source: thread:t-desc" in desc
        assert "refund broken" in desc
        assert "Conversation excerpt" in desc
        assert len(desc.split("\n")) >= 3

    def test_description_truncates_long_messages(self, tmp_path: Path):
        c = _make_conductor(tmp_path)
        state = ConductorState(thread_id="t-trunc")
        signal = IntentSignal(category=IntentCategory.BUG, confidence=0.8, summary="bug")
        long_msg = _msg("x" * 200, "t-trunc")
        thread = _thread("t-trunc", [long_msg])

        desc = c._build_fork_description(state, signal, thread)
        assert "…" in desc


# ---------------------------------------------------------------------------
# Signal hash
# ---------------------------------------------------------------------------


class TestSignalHash:
    def test_same_signal_same_hash(self):
        s1 = IntentSignal(category=IntentCategory.BUG, confidence=0.8, summary="fix it")
        s2 = IntentSignal(category=IntentCategory.BUG, confidence=0.5, summary="fix it")
        assert Conductor._signal_hash(s1) == Conductor._signal_hash(s2)

    def test_different_summary_different_hash(self):
        s1 = IntentSignal(category=IntentCategory.BUG, confidence=0.8, summary="fix A")
        s2 = IntentSignal(category=IntentCategory.BUG, confidence=0.8, summary="fix B")
        assert Conductor._signal_hash(s1) != Conductor._signal_hash(s2)

    def test_different_category_different_hash(self):
        s1 = IntentSignal(category=IntentCategory.BUG, confidence=0.8, summary="fix")
        s2 = IntentSignal(category=IntentCategory.FEATURE, confidence=0.8, summary="fix")
        assert Conductor._signal_hash(s1) != Conductor._signal_hash(s2)
