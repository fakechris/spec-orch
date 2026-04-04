"""Core multi-turn brainstorming engine.

Routes incoming ``ConversationMessage`` objects to the LLM planner, persists
thread state as JSON files, and supports a ``freeze`` command that distils the
discussion into a canonical ``docs/specs/`` spec via ``MissionService``.
"""

from __future__ import annotations

import json
import re
import tomllib
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spec_orch.domain.models import (
    ConversationMessage,
    ConversationThread,
    ThreadStatus,
)
from spec_orch.services.io import atomic_write_json
from spec_orch.services.linear_client import LinearClient
from spec_orch.services.linear_write_back import LinearWriteBackService

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
        enable_conductor: bool = True,
    ) -> None:
        self.repo_root = Path(repo_root)
        self._threads_dir = self.repo_root / _THREADS_DIR
        self._threads_dir.mkdir(parents=True, exist_ok=True)
        self._planner = planner
        self._threads: dict[str, ConversationThread] = {}
        self._conductor: Any | None = None

        if enable_conductor:
            try:
                from spec_orch.services.conductor import Conductor

                self._conductor = Conductor(
                    repo_root=self.repo_root,
                    planner=planner,
                )
            except ImportError:
                pass

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

        # Route approve to Conductor before legacy command handling
        if self._conductor is not None:
            from spec_orch.services.conductor.conductor import APPROVE_RE_PATTERN

            if re.search(APPROVE_RE_PATTERN, msg.content, re.IGNORECASE):
                response = self._conductor.process_message(msg, thread)
                result: str = response.conductor_message or "Nothing to approve."
                if response.action == "formalized":
                    self._emit_conductor_event("formalized", thread.thread_id, response.intent)
                return result

        cmd_match = _COMMAND_RE.search(msg.content)
        if cmd_match:
            return self._handle_command(cmd_match.group(1).strip(), thread)

        # Run through Conductor for intent analysis
        if self._conductor is not None:
            response = self._conductor.process_message(msg, thread)
            if response.action in ("propose", "formalized"):
                return self._handle_conductor_response(response, thread)

        return self._brainstorm_reply(thread)

    def _handle_conductor_response(self, response: Any, thread: ConversationThread) -> str:
        """Consolidate Conductor propose/formalized handling."""
        if response.action == "propose":
            self._emit_conductor_event("crystallize", thread.thread_id, response.intent)
            brainstorm = self._brainstorm_reply(thread)
            return f"{brainstorm}\n\n---\n\n{response.conductor_message}"
        self._emit_conductor_event("formalized", thread.thread_id, response.intent)
        msg_text: str = response.conductor_message or ""
        return msg_text

    def _emit_conductor_event(
        self,
        action: str,
        thread_id: str,
        intent: Any | None = None,
    ) -> None:
        try:
            from spec_orch.services.event_bus import Event, EventTopic, get_event_bus

            payload: dict[str, Any] = {
                "action": action,
                "thread_id": thread_id,
            }
            if intent is not None:
                cat = getattr(intent, "category", "unknown")
                payload["intent_category"] = cat.value if hasattr(cat, "value") else str(cat)
                payload["confidence"] = getattr(intent, "confidence", 0)
            get_event_bus().publish(
                Event(
                    topic=EventTopic.CONDUCTOR,
                    payload=payload,
                    source="conversation_service",
                )
            )
        except ImportError:
            pass

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
            title = cmd[len("mission create") :].strip().strip('"').strip("'")
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
        self._persist_thread_intake_artifacts(
            thread=thread,
            mission_id=mission.mission_id,
            title=title,
            spec_md=spec_md,
        )

        thread.status = ThreadStatus.FROZEN
        thread.spec_snapshot = mission.spec_path
        self._persist_thread(thread)

        return (
            f"Spec frozen to `{mission.spec_path}`.\n"
            f"Mission: {mission.mission_id}\n"
            f"Run `spec-orch mission approve {mission.mission_id}` when ready."
        )

    def _persist_thread_intake_artifacts(
        self,
        *,
        thread: ConversationThread,
        mission_id: str,
        title: str,
        spec_md: str,
    ) -> None:
        from spec_orch.dashboard.launcher import (
            _build_dashboard_intake_workspace,
            _operator_dir,
            _persist_dashboard_intake_workspace,
            _write_launch_metadata,
        )

        payload = self._conversation_payload_from_spec(thread, title=title, spec_md=spec_md)
        workspace = _build_dashboard_intake_workspace(
            self.repo_root,
            mission_id=mission_id,
            payload={
                **payload,
                "mission_id": mission_id,
                "title": title,
            },
        )
        _persist_dashboard_intake_workspace(
            self.repo_root,
            mission_id=mission_id,
            workspace=workspace,
        )
        operator_dir = _operator_dir(self.repo_root, mission_id)
        (operator_dir / "conversation_intake.json").write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )

        linear_ref = self._latest_linear_ref(thread)
        if linear_ref:
            launch_meta = {
                "linear_issue": {
                    "id": linear_ref["linear_issue_id"],
                    "identifier": linear_ref["linear_identifier"],
                    "title": title,
                }
            }
            _write_launch_metadata(self.repo_root, mission_id, launch_meta)
            self._sync_linear_issue_from_thread(
                mission_id=mission_id,
                linear_issue_id=linear_ref["linear_issue_id"],
            )

    def _conversation_payload_from_spec(
        self,
        thread: ConversationThread,
        *,
        title: str,
        spec_md: str,
    ) -> dict[str, Any]:
        problem = self._extract_markdown_section(spec_md, "Problem") or self._first_user_message(
            thread
        )
        goal = self._extract_markdown_section(spec_md, "Goal")
        acceptance = self._extract_markdown_bullets(spec_md, "Acceptance Criteria")
        constraints = self._extract_markdown_bullets(spec_md, "Constraints")
        evidence_expectations = self._extract_markdown_bullets(spec_md, "Verification Expectations")
        if not evidence_expectations:
            evidence_expectations = ["conversation thread review"]
        return {
            "title": title,
            "problem": problem,
            "goal": goal,
            "intent": f"Converged from {thread.channel} thread {thread.thread_id}.",
            "acceptance_criteria": acceptance,
            "constraints": constraints,
            "evidence_expectations": evidence_expectations,
            "current_system_understanding": (
                f"Conversation converged from {thread.channel} thread {thread.thread_id}."
            ),
        }

    def _sync_linear_issue_from_thread(self, *, mission_id: str, linear_issue_id: str) -> None:
        client = LinearClient(token_env=self._linear_token_env())
        try:
            issue = client.query(
                """
                query($id: String!) {
                  issue(id: $id) { id description }
                }
                """,
                {"id": linear_issue_id},
            ).get("issue")
            if not isinstance(issue, dict):
                return
            LinearWriteBackService(client=client).sync_issue_mirror_from_mission(
                repo_root=self.repo_root,
                mission_id=mission_id,
                linear_id=linear_issue_id,
                current_description=str(issue.get("description") or ""),
            )
        finally:
            client.close()

    def _linear_token_env(self) -> str:
        config_path = self.repo_root / "spec-orch.toml"
        if not config_path.exists():
            return "SPEC_ORCH_LINEAR_TOKEN"
        try:
            with config_path.open("rb") as handle:
                raw = tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError):
            return "SPEC_ORCH_LINEAR_TOKEN"
        linear = raw.get("linear", {})
        if not isinstance(linear, dict):
            return "SPEC_ORCH_LINEAR_TOKEN"
        return str(linear.get("token_env", "SPEC_ORCH_LINEAR_TOKEN"))

    @staticmethod
    def _extract_markdown_section(spec_md: str, heading: str) -> str:
        pattern = re.compile(
            rf"^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s|\Z)",
            re.MULTILINE | re.DOTALL,
        )
        match = pattern.search(spec_md)
        if not match:
            return ""
        return match.group(1).strip()

    def _extract_markdown_bullets(self, spec_md: str, heading: str) -> list[str]:
        section = self._extract_markdown_section(spec_md, heading)
        items: list[str] = []
        for line in section.splitlines():
            stripped = line.strip()
            if stripped.startswith("- "):
                items.append(stripped[2:].strip())
        return items

    @staticmethod
    def _first_user_message(thread: ConversationThread) -> str:
        for message in thread.messages:
            if message.sender == "user":
                content = _COMMAND_RE.sub("", message.content).strip()
                if content:
                    return content
        return ""

    @staticmethod
    def _latest_linear_ref(thread: ConversationThread) -> dict[str, str] | None:
        for message in reversed(thread.messages):
            metadata = message.metadata
            linear_issue_id = str(metadata.get("linear_issue_id", "")).strip()
            linear_identifier = str(metadata.get("linear_identifier", "")).strip()
            if linear_issue_id and linear_identifier:
                return {
                    "linear_issue_id": linear_issue_id,
                    "linear_identifier": linear_identifier,
                }
        return None

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
        atomic_write_json(path, data)

    def _load_thread(self, path: Path) -> ConversationThread:
        data = json.loads(path.read_text())
        messages = [ConversationMessage(**m) for m in data.get("messages", [])]
        fallback_ts = datetime.fromtimestamp(
            path.stat().st_mtime,
            tz=UTC,
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
