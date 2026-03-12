"""Linear Comment Bot — polls issue comments and replies via the API.

Watched issues are determined by a configurable label (default: ``spec-orch``).
The adapter polls at a configurable interval and delegates new user comments
to a callback (typically ``ConversationService.handle_message``).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from spec_orch.domain.models import ConversationMessage
from spec_orch.services.linear_client import LinearClient

_CHANNEL = "linear"


class LinearConversationAdapter:
    """ConversationAdapter implementation that uses Linear issue comments."""

    ADAPTER_NAME: str = "linear_conversation"

    def __init__(
        self,
        *,
        client: LinearClient,
        team_key: str = "SON",
        watch_label: str = "spec-orch",
        poll_interval_seconds: int = 30,
        bot_user_id: str | None = None,
    ) -> None:
        self._client = client
        self._team_key = team_key
        self._watch_label = watch_label
        self._poll_interval = poll_interval_seconds
        self._bot_user_id = bot_user_id
        self._running = False
        self._seen_comment_ids: set[str] = set()

    def listen(
        self,
        callback: Callable[[ConversationMessage], str | None],
    ) -> None:
        """Poll Linear for new comments on watched issues."""
        self._running = True
        while self._running:
            try:
                self._poll_once(callback)
            except Exception as exc:  # noqa: BLE001
                print(f"[linear-conv] poll error: {exc}")
            self._sleep(self._poll_interval)

    def _poll_once(
        self,
        callback: Callable[[ConversationMessage], str | None],
    ) -> None:
        issues = self._client.list_issues(
            team_key=self._team_key,
            filter_state=None,
        )
        watched = [
            i for i in issues
            if self._has_label(i, self._watch_label)
        ]

        for issue in watched:
            linear_id: str = issue.get("id", "")
            identifier: str = issue.get("identifier", "")
            if not linear_id:
                continue

            comments = self._client.list_comments(linear_id)
            for comment in comments:
                cid: str = comment.get("id", "")
                if cid in self._seen_comment_ids:
                    continue
                self._seen_comment_ids.add(cid)

                user_info: dict[str, Any] = comment.get("user", {})
                user_id = user_info.get("id", "")
                if self._bot_user_id and user_id == self._bot_user_id:
                    continue

                msg = ConversationMessage(
                    message_id=cid,
                    thread_id=identifier,
                    sender=user_info.get("name", "user"),
                    content=comment.get("body", ""),
                    timestamp=comment.get("createdAt", datetime.now(UTC).isoformat()),
                    channel=_CHANNEL,
                    metadata={
                        "linear_issue_id": linear_id,
                        "linear_identifier": identifier,
                        "user_email": user_info.get("email", ""),
                    },
                )
                reply_text = callback(msg)
                if reply_text:
                    self.reply(msg.thread_id, reply_text)

    def reply(self, thread_id: str, content: str) -> None:
        """Post a comment back to the Linear issue."""
        linear_id = self._resolve_linear_id(thread_id)
        if not linear_id:
            print(f"[linear-conv] cannot resolve Linear ID for {thread_id}")
            return
        prefixed = f"**🤖 SpecOrch Bot**\n\n{content}"
        self._client.add_comment(linear_id, prefixed)

    def stop(self) -> None:
        self._running = False

    def _resolve_linear_id(self, identifier: str) -> str | None:
        """Resolve a human-readable identifier (e.g. SON-15) to a Linear UUID."""
        try:
            issue = self._client.get_issue(identifier)
            return issue.get("id")
        except (ValueError, RuntimeError):
            return None

    @staticmethod
    def _has_label(issue: dict[str, Any], label_name: str) -> bool:
        labels = issue.get("labels", {}).get("nodes", [])
        return any(
            lbl.get("name", "").lower() == label_name.lower()
            for lbl in labels
        )

    def _sleep(self, seconds: int) -> None:
        for _ in range(seconds):
            if not self._running:
                break
            time.sleep(1)
