"""Tests for ConversationService — core brainstorming engine."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

from spec_orch.domain.models import (
    ConversationMessage,
    ConversationThread,
    ThreadStatus,
)
from spec_orch.services.conversation_service import ConversationService


def _make_msg(
    thread_id: str = "t-1",
    content: str = "hello",
    sender: str = "user",
    channel: str = "cli",
) -> ConversationMessage:
    return ConversationMessage(
        message_id=f"m-{id(content)}",
        thread_id=thread_id,
        sender=sender,
        content=content,
        timestamp=datetime.now(UTC).isoformat(),
        channel=channel,
    )


class TestConversationServiceBasic:
    def test_handle_message_no_planner(self, tmp_path: Path) -> None:
        svc = ConversationService(repo_root=tmp_path, planner=None)
        msg = _make_msg(content="what should we build?")
        reply = svc.handle_message(msg)
        assert reply is not None
        assert "no planner" in reply.lower()

    def test_handle_message_with_planner(self, tmp_path: Path) -> None:
        planner = MagicMock()
        planner.brainstorm.return_value = "Let's build a REST API."
        svc = ConversationService(repo_root=tmp_path, planner=planner)

        msg = _make_msg(content="what should we build?")
        reply = svc.handle_message(msg)

        assert reply == "Let's build a REST API."
        planner.brainstorm.assert_called_once()

    def test_thread_persistence(self, tmp_path: Path) -> None:
        planner = MagicMock()
        planner.brainstorm.return_value = "reply"
        svc = ConversationService(repo_root=tmp_path, planner=planner)

        msg = _make_msg(thread_id="persist-1", content="hi")
        svc.handle_message(msg)

        thread_file = tmp_path / ".spec_orch_threads" / "persist-1.json"
        assert thread_file.exists()
        data = json.loads(thread_file.read_text())
        assert data["thread_id"] == "persist-1"
        assert len(data["messages"]) == 2  # user + bot

    def test_thread_reload_across_instances(self, tmp_path: Path) -> None:
        planner = MagicMock()
        planner.brainstorm.return_value = "reply1"
        svc1 = ConversationService(repo_root=tmp_path, planner=planner)
        svc1.handle_message(_make_msg(thread_id="reload-1", content="msg1"))

        planner.brainstorm.return_value = "reply2"
        svc2 = ConversationService(repo_root=tmp_path, planner=planner)
        svc2.handle_message(_make_msg(thread_id="reload-1", content="msg2"))

        thread = svc2.get_thread("reload-1")
        assert thread is not None
        assert len(thread.messages) == 4  # msg1 + reply1 + msg2 + reply2

    def test_frozen_thread_rejects_messages(self, tmp_path: Path) -> None:
        planner = MagicMock()
        planner.brainstorm.return_value = "reply"
        planner.summarise_to_spec.return_value = "# Spec\n\n## Goal\nTest"
        svc = ConversationService(repo_root=tmp_path, planner=planner)

        svc.handle_message(_make_msg(thread_id="freeze-1", content="start"))
        svc.handle_message(_make_msg(thread_id="freeze-1", content="@spec-orch freeze"))

        reply = svc.handle_message(_make_msg(thread_id="freeze-1", content="more?"))
        assert reply is not None
        assert "frozen" in reply.lower()


class TestConversationServiceCommands:
    def test_status_command(self, tmp_path: Path) -> None:
        planner = MagicMock()
        planner.brainstorm.return_value = "reply"
        svc = ConversationService(repo_root=tmp_path, planner=planner)

        svc.handle_message(_make_msg(thread_id="stat-1", content="hello"))
        reply = svc.handle_message(
            _make_msg(thread_id="stat-1", content="@spec-orch status"),
        )
        assert reply is not None
        assert "stat-1" in reply
        assert "active" in reply

    def test_freeze_command(self, tmp_path: Path) -> None:
        planner = MagicMock()
        planner.brainstorm.return_value = "Let's do X"
        planner.summarise_to_spec.return_value = "# X\n\n## Goal\nDo X\n"
        svc = ConversationService(repo_root=tmp_path, planner=planner)

        svc.handle_message(_make_msg(thread_id="frz-1", content="build feature X"))
        reply = svc.handle_message(
            _make_msg(thread_id="frz-1", content="@spec-orch freeze"),
        )

        assert reply is not None
        assert "frozen" in reply.lower() or "spec" in reply.lower()
        planner.summarise_to_spec.assert_called_once()

        specs_dir = tmp_path / "docs" / "specs"
        assert specs_dir.exists()
        spec_files = list(specs_dir.rglob("spec.md"))
        assert len(spec_files) == 1
        assert "# X" in spec_files[0].read_text()

    def test_mission_create_command(self, tmp_path: Path) -> None:
        svc = ConversationService(repo_root=tmp_path, planner=None)
        reply = svc.handle_message(
            _make_msg(
                thread_id="mc-1",
                content='@spec-orch mission create "Test Feature"',
            ),
        )
        assert reply is not None
        assert "mission created" in reply.lower()

        mission_dirs = list((tmp_path / "docs" / "specs").iterdir())
        assert len(mission_dirs) == 1

    def test_freeze_with_minimal_history(self, tmp_path: Path) -> None:
        planner = MagicMock()
        planner.brainstorm.return_value = "Sure, let's do that."
        planner.summarise_to_spec.return_value = "# Minimal\n\n## Goal\nTest"
        svc = ConversationService(repo_root=tmp_path, planner=planner)

        svc.handle_message(_make_msg(thread_id="min-1", content="just a note"))
        reply = svc.handle_message(
            _make_msg(thread_id="min-1", content="@spec-orch freeze"),
        )
        assert reply is not None
        assert "spec" in reply.lower() or "frozen" in reply.lower()

    def test_freeze_command_persists_intake_workspace_and_syncs_linear_issue(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        planner = MagicMock()
        planner.brainstorm.return_value = "Let's do X"
        planner.summarise_to_spec.return_value = (
            "# X\n\n"
            "## Problem\n\n"
            "Linear thread convergence still requires manual issue shaping.\n\n"
            "## Goal\n\n"
            "Turn the thread into canonical issue state automatically.\n\n"
            "## Acceptance Criteria\n\n"
            "- Freeze writes an intake workspace.\n"
            "- The linked Linear issue gets a structured mirror.\n"
        )
        svc = ConversationService(repo_root=tmp_path, planner=planner)

        captured_descriptions: list[str] = []

        class FakeLinearClient:
            def __init__(self, **_: object) -> None:
                pass

            def query(self, graphql: str, variables: dict | None = None) -> dict:
                if "query($id: String!)" in graphql:
                    return {"issue": {"id": "issue-1", "description": "mission: frz-1"}}
                raise AssertionError(graphql)

            def update_issue_description(self, issue_id: str, *, description: str) -> dict:
                assert issue_id == "issue-1"
                captured_descriptions.append(description)
                return {"success": True, "issue": {"id": issue_id, "description": description}}

            def add_comment(self, issue_id: str, body: str) -> dict:
                return {"success": True, "comment": {"id": "c-1", "body": body}}

            def close(self) -> None:
                return None

        monkeypatch.setattr(
            "spec_orch.services.conversation_service.LinearClient", FakeLinearClient
        )

        svc.handle_message(
            _make_msg(
                thread_id="frz-1",
                content="Please make chat-to-issue work.",
                channel="linear",
                sender="user",
            ).__class__(
                message_id="m-linear",
                thread_id="frz-1",
                sender="user",
                content="Please make chat-to-issue work.",
                timestamp=datetime.now(UTC).isoformat(),
                channel="linear",
                metadata={"linear_issue_id": "issue-1", "linear_identifier": "SON-321"},
            )
        )
        reply = svc.handle_message(
            _make_msg(thread_id="frz-1", content="@spec-orch freeze", channel="linear"),
        )

        assert reply is not None
        spec_files = list((tmp_path / "docs" / "specs").rglob("operator/intake_workspace.json"))
        assert len(spec_files) == 1
        workspace = json.loads(spec_files[0].read_text(encoding="utf-8"))
        assert workspace["canonical_issue"]["problem"] == (
            "Linear thread convergence still requires manual issue shaping."
        )
        assert workspace["canonical_issue"]["goal"] == (
            "Turn the thread into canonical issue state automatically."
        )
        assert workspace["readiness"]["is_ready"] is True
        launch_path = spec_files[0].parent / "launch.json"
        assert launch_path.exists()
        launch_meta = json.loads(launch_path.read_text(encoding="utf-8"))
        assert launch_meta["linear_issue"]["identifier"] == "SON-321"
        assert captured_descriptions
        assert "## SpecOrch Mirror" in captured_descriptions[0]
        assert '"next_action": "create_workspace"' in captured_descriptions[0]

    def test_freeze_command_keeps_thread_frozen_when_linear_sync_fails(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        planner = MagicMock()
        planner.brainstorm.return_value = "Let's do X"
        planner.summarise_to_spec.return_value = "# X\n\n## Goal\nDo X\n"
        svc = ConversationService(repo_root=tmp_path, planner=planner)

        def fail_sync(*_: object, **__: object) -> None:
            raise RuntimeError("linear unavailable")

        monkeypatch.setattr(svc, "_sync_linear_issue_from_thread", fail_sync)

        svc.handle_message(
            ConversationMessage(
                message_id="m-linear",
                thread_id="frz-fail",
                sender="user",
                content="Please make chat-to-issue work.",
                timestamp=datetime.now(UTC).isoformat(),
                channel="linear",
                metadata={"linear_issue_id": "issue-1", "linear_identifier": "SON-321"},
            )
        )
        reply = svc.handle_message(
            _make_msg(thread_id="frz-fail", content="@spec-orch freeze", channel="linear"),
        )

        assert reply is not None
        thread = svc.get_thread("frz-fail")
        assert thread is not None
        assert thread.status == ThreadStatus.FROZEN
        assert thread.mission_id is not None
        launch_path = tmp_path / "docs" / "specs" / thread.mission_id / "operator" / "launch.json"
        assert launch_path.exists()


class TestConversationThreadModel:
    def test_defaults(self) -> None:
        thread = ConversationThread(thread_id="t-1", channel="slack")
        assert thread.status == ThreadStatus.ACTIVE
        assert thread.messages == []
        assert thread.mission_id is None
        assert thread.spec_snapshot is None

    def test_message_model(self) -> None:
        msg = ConversationMessage(
            message_id="m-1",
            thread_id="t-1",
            sender="user",
            content="hello",
            timestamp="2026-03-12T00:00:00",
            channel="slack",
        )
        assert msg.metadata == {}


class TestListThreads:
    def test_list_empty(self, tmp_path: Path) -> None:
        svc = ConversationService(repo_root=tmp_path)
        assert svc.list_threads() == []

    def test_list_after_messages(self, tmp_path: Path) -> None:
        planner = MagicMock()
        planner.brainstorm.return_value = "reply"
        svc = ConversationService(repo_root=tmp_path, planner=planner)

        svc.handle_message(_make_msg(thread_id="list-1", content="a"))
        svc.handle_message(_make_msg(thread_id="list-2", content="b"))

        threads = svc.list_threads()
        ids = {t.thread_id for t in threads}
        assert "list-1" in ids
        assert "list-2" in ids
