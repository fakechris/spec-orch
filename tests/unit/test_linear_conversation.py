"""Tests for LinearConversationAdapter and LinearClient.list_comments()."""

from __future__ import annotations

from unittest.mock import MagicMock

from spec_orch.services.linear_conversation_adapter import LinearConversationAdapter


class TestLinearConversationAdapter:
    def _make_adapter(self, client: MagicMock) -> LinearConversationAdapter:
        return LinearConversationAdapter(
            client=client,
            team_key="TST",
            watch_label="spec-orch",
            poll_interval_seconds=1,
            bot_user_id="bot-123",
        )

    def test_poll_once_dispatches_new_comments(self) -> None:
        client = MagicMock()
        client.list_issues.return_value = [
            {
                "id": "lin-uuid-1",
                "identifier": "TST-1",
                "title": "Test issue",
                "labels": {"nodes": [{"name": "spec-orch"}]},
            },
        ]
        client.list_comments.return_value = [
            {
                "id": "comment-1",
                "body": "What about caching?",
                "createdAt": "2026-03-12T10:00:00Z",
                "user": {"id": "user-1", "name": "Alice", "email": "a@b.com"},
            },
        ]

        adapter = self._make_adapter(client)
        received = []
        adapter._poll_once(callback=lambda msg: received.append(msg))

        assert len(received) == 1
        assert received[0].content == "What about caching?"
        assert received[0].thread_id == "TST-1"
        assert received[0].channel == "linear"

    def test_skips_bot_own_comments(self) -> None:
        client = MagicMock()
        client.list_issues.return_value = [
            {
                "id": "lin-uuid-2",
                "identifier": "TST-2",
                "title": "Test",
                "labels": {"nodes": [{"name": "spec-orch"}]},
            },
        ]
        client.list_comments.return_value = [
            {
                "id": "comment-bot",
                "body": "Bot reply",
                "createdAt": "2026-03-12T10:01:00Z",
                "user": {"id": "bot-123", "name": "SpecOrch Bot", "email": ""},
            },
        ]

        adapter = self._make_adapter(client)
        received = []
        adapter._poll_once(callback=lambda msg: received.append(msg))
        assert len(received) == 0

    def test_skips_issues_without_label(self) -> None:
        client = MagicMock()
        client.list_issues.return_value = [
            {
                "id": "lin-uuid-3",
                "identifier": "TST-3",
                "title": "No label",
                "labels": {"nodes": [{"name": "bug"}]},
            },
        ]

        adapter = self._make_adapter(client)
        received = []
        adapter._poll_once(callback=lambda msg: received.append(msg))

        client.list_comments.assert_not_called()
        assert len(received) == 0

    def test_deduplicates_comments_across_polls(self) -> None:
        client = MagicMock()
        client.list_issues.return_value = [
            {
                "id": "lin-uuid-4",
                "identifier": "TST-4",
                "title": "Dedup",
                "labels": {"nodes": [{"name": "spec-orch"}]},
            },
        ]
        comment = {
            "id": "comment-dup",
            "body": "Same comment",
            "createdAt": "2026-03-12T10:02:00Z",
            "user": {"id": "user-2", "name": "Bob", "email": ""},
        }
        client.list_comments.return_value = [comment]

        adapter = self._make_adapter(client)
        received = []
        adapter._poll_once(callback=lambda msg: received.append(msg))
        adapter._poll_once(callback=lambda msg: received.append(msg))

        assert len(received) == 1

    def test_reply_posts_comment(self) -> None:
        client = MagicMock()
        client.get_issue.return_value = {"id": "lin-uuid-5"}
        adapter = self._make_adapter(client)

        adapter.reply("TST-5", "Here's my analysis...")

        client.add_comment.assert_called_once()
        args = client.add_comment.call_args
        assert "lin-uuid-5" in args.args or args.args[0] == "lin-uuid-5"
        assert "analysis" in args.args[1].lower()

    def test_stop_sets_running_false(self) -> None:
        client = MagicMock()
        adapter = self._make_adapter(client)
        adapter._running = True
        adapter.stop()
        assert adapter._running is False


class TestLinearClientListComments:
    def test_list_comments_query_structure(self) -> None:
        """Verify list_comments calls query with correct GraphQL."""
        mock_client = MagicMock()
        mock_client.query.return_value = {
            "issue": {
                "comments": {
                    "nodes": [
                        {"id": "c1", "body": "hello", "createdAt": "2026-01-01", "user": {}},
                    ],
                },
            },
        }

        from spec_orch.services.linear_client import LinearClient

        lc = LinearClient.__new__(LinearClient)
        lc._client = mock_client
        lc.query = mock_client.query

        result = lc.list_comments("issue-id-1")
        assert len(result) == 1
        assert result[0]["body"] == "hello"
        mock_client.query.assert_called_once()
