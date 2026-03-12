"""Slack Bot — uses Slack Bolt with Socket Mode for thread-based brainstorming.

Requires the ``slack`` extra: ``pip install spec-orch[slack]``.
Configuration is driven by two environment variables (configurable via
``spec-orch.toml``):

- ``SLACK_BOT_TOKEN``  — the ``xoxb-`` Bot User OAuth Token
- ``SLACK_APP_TOKEN``  — the ``xapp-`` App-Level Token (Socket Mode)
"""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from spec_orch.domain.models import ConversationMessage

_CHANNEL = "slack"


class SlackConversationAdapter:
    """ConversationAdapter implementation using Slack Bolt + Socket Mode."""

    ADAPTER_NAME: str = "slack_conversation"

    def __init__(
        self,
        *,
        bot_token_env: str = "SLACK_BOT_TOKEN",
        app_token_env: str = "SLACK_APP_TOKEN",
    ) -> None:
        self._bot_token_env = bot_token_env
        self._app_token_env = app_token_env
        self._handler: Any = None
        self._bot_user_id: str | None = None
        self._thread_channels: dict[str, str] = {}

    def listen(
        self,
        callback: Callable[[ConversationMessage], str | None],
    ) -> None:
        """Start the Slack Socket Mode listener (blocks until ``stop()``)."""
        try:
            from slack_bolt import App
            from slack_bolt.adapter.socket_mode import SocketModeHandler
        except ImportError as exc:
            raise ImportError(
                "slack-bolt is required for SlackConversationAdapter. "
                "Install with: pip install spec-orch[slack]"
            ) from exc

        bot_token = os.environ.get(self._bot_token_env, "")
        app_token = os.environ.get(self._app_token_env, "")
        if not bot_token or not app_token:
            raise ValueError(
                f"Slack tokens required. Set {self._bot_token_env} and "
                f"{self._app_token_env} environment variables."
            )

        app = App(token=bot_token)

        auth = app.client.auth_test()
        self._bot_user_id = auth.get("user_id")

        @app.event("app_mention")
        def handle_mention(event: dict[str, Any], say: Callable[..., Any]) -> None:
            self._on_message(event, say, callback)

        @app.event("message")
        def handle_message(event: dict[str, Any], say: Callable[..., Any]) -> None:
            if "thread_ts" not in event:
                return
            if event.get("subtype"):
                return
            self._on_message(event, say, callback)

        self._handler = SocketModeHandler(app, app_token)
        print("[slack-conv] starting Socket Mode listener")
        self._handler.start()

    def _on_message(
        self,
        event: dict[str, Any],
        say: Callable[..., Any],
        callback: Callable[[ConversationMessage], str | None],
    ) -> None:
        user_id = event.get("user", "")
        if user_id == self._bot_user_id:
            return

        thread_ts = event.get("thread_ts") or event.get("ts", "")
        text = event.get("text", "")
        if self._bot_user_id:
            text = text.replace(f"<@{self._bot_user_id}>", "").strip()

        slack_channel = event.get("channel", "")
        self._thread_channels[thread_ts] = slack_channel

        msg = ConversationMessage(
            message_id=event.get("ts", ""),
            thread_id=thread_ts,
            sender=user_id,
            content=text,
            timestamp=datetime.now(UTC).isoformat(),
            channel=_CHANNEL,
            metadata={
                "slack_channel": slack_channel,
                "slack_thread_ts": thread_ts,
                "slack_user": user_id,
            },
        )

        reply_text = callback(msg)

        if reply_text:
            say(text=reply_text, thread_ts=thread_ts)

    def reply(self, thread_id: str, content: str) -> None:
        """Post a reply to a Slack thread.

        This is used for out-of-band replies (not in the listen callback path).
        In the normal flow, replies are sent via ``say()`` inside ``_on_message``.
        Requires that the thread was previously seen via ``_on_message`` so the
        channel ID is cached in ``_thread_channels``.
        """
        channel = self._thread_channels.get(thread_id)
        if not channel:
            print(f"[slack-conv] no channel cached for thread {thread_id}")
            return
        if self._handler and hasattr(self._handler, "app"):
            try:
                self._handler.app.client.chat_postMessage(
                    channel=channel,
                    text=content,
                    thread_ts=thread_id,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[slack-conv] reply error: {exc}")

    def stop(self) -> None:
        if self._handler:
            self._handler.close()
            self._handler = None
