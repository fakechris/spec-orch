from __future__ import annotations

from unittest.mock import MagicMock

from spec_orch.services.linear_conversation_adapter import LinearConversationAdapter


def test_reply_uses_cached_linear_issue_id_from_polled_thread() -> None:
    client = MagicMock()
    client.list_issues.return_value = [
        {
            "id": "issue-1",
            "identifier": "SON-321",
            "labels": {"nodes": [{"name": "spec-orch"}]},
        }
    ]
    client.list_comments.return_value = [
        {
            "id": "comment-1",
            "body": "please freeze this",
            "createdAt": "2026-04-04T00:00:00Z",
            "user": {"id": "user-1", "name": "Chris", "email": "c@example.com"},
        }
    ]

    adapter = LinearConversationAdapter(client=client)
    callback = MagicMock(return_value="done")

    adapter._poll_once(callback)
    adapter.reply("SON-321", "structured sync complete")

    client.get_issue.assert_not_called()
    client.add_comment.assert_called()
