"""Core multi-turn brainstorming engine.

Routes incoming ``ConversationMessage`` objects to the LLM planner, persists
thread state as JSON files, and supports a ``freeze`` command that distils the
discussion into a canonical ``docs/specs/`` spec via ``MissionService``.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spec_orch.domain.models import (
    ConversationMessage,
    ConversationThread,
    ThreadStatus,
)

_THREADS_DIR = ".spec_orch_threads"
_COMMAND_RE = re.compile(
    r"@?spec[_-]?orch\s+"
    r"(freeze|status|mission\s+create\s+.+)",
    re.IGNORECASE,
)


class ConversationService:
    """Orchestrates multi-turn brainstorming and spec freeze."""

    def __init__(
        self,
        *,
        repo_root: Path,
        planner: Any | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self._threads_dir = self.repo_root / _THREADS_DIR
        self._threads_dir.mkdir(parents=True, exist_ok=True)
        self._planner = planner
        self._threads: dict[str, ConversationThread] = {}

    def handle_message(
        self,
        msg: ConversationMessage,
    ) -> str | None:
        """Process an incoming message and return a reply (or None for commands)."""
        thread = self._get_or_create_thread(msg.thread_id, msg.channel)

        if thread.status != ThreadStatus.ACTIVE:
            return f"This thread is {thread.status.value}. Start a new one to continue."

        thread.messages.append(msg)
        self._persist_thread(thread)

        cmd_match = _COMMAND_RE.search(msg.content)
        if cmd_match:
            return self._handle_command(cmd_match.group(1).strip(), thread)

        return self._brainstorm_reply(thread)

    def _brainstorm_reply(self, thread: ConversationThread) -> str:
        if self._planner is None:
            return (
                "No planner configured. Set [planner] in spec-orch.toml "
                "or pass --model to enable brainstorming."
            )

        history = self._build_history(thread)
        reply_text: str = self._planner.brainstorm(
            conversation_history=history,
        )

        bot_msg = ConversationMessage(
            message_id=f"bot-{uuid.uuid4().hex[:8]}",
            thread_id=thread.thread_id,
            sender="bot",
            content=reply_text,
            timestamp=datetime.now(UTC).isoformat(),
            channel=thread.channel,
        )
        thread.messages.append(bot_msg)
        self._persist_thread(thread)
        return reply_text

    def _handle_command(self, cmd: str, thread: ConversationThread) -> str:
        lower = cmd.lower()

        if lower == "freeze":
            return self._freeze_thread(thread)

        if lower == "status":
            n = len([m for m in thread.messages if m.sender == "user"])
            return (
                f"Thread {thread.thread_id}: {thread.status.value}, "
                f"{n} user messages, mission={thread.mission_id or 'none'}"
            )

        if lower.startswith("mission create"):
            title = cmd[len("mission create"):].strip().strip('"').strip("'")
            return self._create_mission_from_thread(thread, title)

        return f"Unknown command: {cmd}"

    @staticmethod
    def _extract_title_from_spec(spec_md: str, fallback: str) -> str:
        """Extract the H1 title from generated spec markdown."""
        for line in spec_md.splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                title = stripped[2:].strip()[:60]
                return title if title else fallback
        return fallback

    def _freeze_thread(self, thread: ConversationThread) -> str:
        if not thread.messages:
            return "Nothing to freeze — thread is empty."

        if self._planner is None:
            return "Cannot freeze: no planner configured."

        inferred = self._infer_title(thread)
        history = self._build_history(thread)

        spec_md: str = self._planner.summarise_to_spec(
            conversation_history=history,
            title=inferred,
        )

        title = self._extract_title_from_spec(spec_md, inferred)

        from spec_orch.services.mission_service import MissionService

        svc = MissionService(self.repo_root)
        mission = svc.create_mission(title)
        thread.mission_id = mission.mission_id

        spec_path = self.repo_root / mission.spec_path
        spec_path.write_text(spec_md)

        thread.status = ThreadStatus.FROZEN
        thread.spec_snapshot = mission.spec_path
        self._persist_thread(thread)

        return (
            f"Spec frozen to `{mission.spec_path}`.\n"
            f"Mission: {mission.mission_id}\n"
            f"Run `spec-orch mission approve {mission.mission_id}` when ready."
        )

    def _create_mission_from_thread(
        self,
        thread: ConversationThread,
        title: str,
    ) -> str:
        from spec_orch.services.mission_service import MissionService

        svc = MissionService(self.repo_root)
        mission = svc.create_mission(title)
        thread.mission_id = mission.mission_id
        self._persist_thread(thread)
        return (
            f"Mission created: {mission.mission_id}\n"
            f"Spec skeleton: `{mission.spec_path}`\n"
            f"Continue brainstorming, then `@spec-orch freeze` to fill it."
        )

    def _infer_title(self, thread: ConversationThread) -> str:
        first_user = next(
            (m for m in thread.messages if m.sender == "user"),
            None,
        )
        if first_user:
            raw = first_user.content.strip()
            raw = _COMMAND_RE.sub("", raw).strip()
            if raw:
                first_sentence = raw.split(".")[0].split("。")[0].split("\n")[0]
                return first_sentence[:60]
        return f"Discussion {thread.thread_id[:8]}"

    @staticmethod
    def _build_history(
        thread: ConversationThread,
    ) -> list[dict[str, str]]:
        history: list[dict[str, str]] = []
        for m in thread.messages:
            role = "assistant" if m.sender == "bot" else "user"
            history.append({"role": role, "content": m.content})
        return history

    def _get_or_create_thread(
        self,
        thread_id: str,
        channel: str,
    ) -> ConversationThread:
        if thread_id in self._threads:
            return self._threads[thread_id]

        path = self._threads_dir / f"{thread_id}.json"
        if path.exists():
            thread = self._load_thread(path)
            self._threads[thread_id] = thread
            return thread

        thread = ConversationThread(thread_id=thread_id, channel=channel)
        self._threads[thread_id] = thread
        return thread

    def _persist_thread(self, thread: ConversationThread) -> None:
        path = self._threads_dir / f"{thread.thread_id}.json"
        data: dict[str, Any] = {
            "thread_id": thread.thread_id,
            "channel": thread.channel,
            "mission_id": thread.mission_id,
            "status": thread.status.value,
            "spec_snapshot": thread.spec_snapshot,
            "created_at": thread.created_at,
            "messages": [
                {
                    "message_id": m.message_id,
                    "thread_id": m.thread_id,
                    "sender": m.sender,
                    "content": m.content,
                    "timestamp": m.timestamp,
                    "channel": m.channel,
                    "metadata": m.metadata,
                }
                for m in thread.messages
            ],
        }
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    def _load_thread(self, path: Path) -> ConversationThread:
        data = json.loads(path.read_text())
        messages = [
            ConversationMessage(**m)
            for m in data.get("messages", [])
        ]
        fallback_ts = datetime.fromtimestamp(
            path.stat().st_mtime, tz=UTC,
        ).isoformat()
        return ConversationThread(
            thread_id=data["thread_id"],
            channel=data["channel"],
            mission_id=data.get("mission_id"),
            messages=messages,
            status=ThreadStatus(data.get("status", "active")),
            spec_snapshot=data.get("spec_snapshot"),
            created_at=data.get("created_at", fallback_ts),
        )

    def list_threads(self) -> list[ConversationThread]:
        threads: list[ConversationThread] = []
        for path in sorted(self._threads_dir.glob("*.json")):
            threads.append(self._load_thread(path))
        return threads

    def get_thread(self, thread_id: str) -> ConversationThread | None:
        if thread_id in self._threads:
            return self._threads[thread_id]
        path = self._threads_dir / f"{thread_id}.json"
        if path.exists():
            thread = self._load_thread(path)
            self._threads[thread_id] = thread
            return thread
        return None
