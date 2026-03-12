"""Tests for SlackConversationAdapter — without requiring slack-bolt installed."""

from __future__ import annotations

from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from spec_orch.domain.models import ConversationMessage


class TestSlackConversationAdapter:
    def _make_adapter(self):
        """Create a SlackConversationAdapter with mocked slack dependencies."""
        mock_bolt = ModuleType("slack_bolt")
        mock_bolt.App = MagicMock
        mock_socket = ModuleType("slack_bolt.adapter.socket_mode")
        mock_socket.SocketModeHandler = MagicMock

        with patch.dict(
            "sys.modules",
            {
                "slack_bolt": mock_bolt,
                "slack_bolt.adapter.socket_mode": mock_socket,
            },
        ):
            from spec_orch.services.slack_conversation_adapter import (
                SlackConversationAdapter,
            )

            return SlackConversationAdapter(
                bot_token_env="TEST_SLACK_BOT_TOKEN",
                app_token_env="TEST_SLACK_APP_TOKEN",
            )

    def test_adapter_name(self):
        adapter = self._make_adapter()
        assert adapter.ADAPTER_NAME == "slack_conversation"

    def test_stop_clears_handler(self):
        adapter = self._make_adapter()
        adapter._handler = MagicMock()
        adapter.stop()
        assert adapter._handler is None

    def test_on_message_skips_bot_own_messages(self):
        adapter = self._make_adapter()
        adapter._bot_user_id = "U_BOT"

        say_mock = MagicMock()
        callback = MagicMock(return_value="reply text")

        event = {
            "user": "U_BOT",
            "text": "I am the bot",
            "ts": "123.456",
            "thread_ts": "123.000",
            "channel": "C123",
        }

        adapter._on_message(event, say_mock, callback)
        callback.assert_not_called()
        say_mock.assert_not_called()

    def test_on_message_dispatches_user_message(self):
        adapter = self._make_adapter()
        adapter._bot_user_id = "U_BOT"

        say_mock = MagicMock()
        callback = MagicMock(return_value="bot reply")

        event = {
            "user": "U_USER",
            "text": "<@U_BOT> what should we build?",
            "ts": "124.456",
            "thread_ts": "124.000",
            "channel": "C123",
        }

        adapter._on_message(event, say_mock, callback)

        callback.assert_called_once()
        msg = callback.call_args.args[0]
        assert isinstance(msg, ConversationMessage)
        assert msg.content == "what should we build?"
        assert msg.channel == "slack"
        assert msg.thread_id == "124.000"

        say_mock.assert_called_once_with(text="bot reply", thread_ts="124.000")

    def test_on_message_no_reply_when_callback_returns_none(self):
        adapter = self._make_adapter()
        adapter._bot_user_id = "U_BOT"

        say_mock = MagicMock()
        callback = MagicMock(return_value=None)

        event = {
            "user": "U_USER",
            "text": "thinking...",
            "ts": "125.456",
            "thread_ts": "125.000",
            "channel": "C123",
        }

        adapter._on_message(event, say_mock, callback)
        callback.assert_called_once()
        say_mock.assert_not_called()

    def test_listen_requires_tokens(self):
        adapter = self._make_adapter()
        with pytest.raises((ValueError, Exception)):
            adapter.listen(callback=MagicMock())


class TestSlackAdapterReply:
    def test_reply_with_handler(self):
        mock_bolt = ModuleType("slack_bolt")
        mock_bolt.App = MagicMock
        mock_socket = ModuleType("slack_bolt.adapter.socket_mode")
        mock_socket.SocketModeHandler = MagicMock

        with patch.dict(
            "sys.modules",
            {
                "slack_bolt": mock_bolt,
                "slack_bolt.adapter.socket_mode": mock_socket,
            },
        ):
            from spec_orch.services.slack_conversation_adapter import (
                SlackConversationAdapter,
            )

            adapter = SlackConversationAdapter()
            mock_handler = MagicMock()
            mock_handler.app.client.chat_postMessage = MagicMock()
            adapter._handler = mock_handler

            adapter.reply("C123", "hello there")

            mock_handler.app.client.chat_postMessage.assert_called_once_with(
                channel="C123",
                text="hello there",
                thread_ts="C123",
            )
