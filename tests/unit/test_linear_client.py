from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from spec_orch.services.linear_client import LinearClient


@pytest.fixture()
def mock_httpx():
    with patch("spec_orch.services.linear_client.httpx") as mock:
        mock_client = MagicMock()
        mock.Client.return_value = mock_client
        yield mock_client


def _make_client(mock_httpx: MagicMock) -> LinearClient:
    with patch.dict("os.environ", {"SPEC_ORCH_LINEAR_TOKEN": "test-token"}):
        return LinearClient()


def test_client_requires_token():
    with (
        patch.dict("os.environ", {}, clear=True),
        pytest.raises(ValueError, match="Linear API token required"),
    ):
        LinearClient(token_env="NONEXISTENT_VAR")


def test_client_falls_back_to_linear_token_alias(mock_httpx: MagicMock):
    with patch("spec_orch.services.linear_client.httpx") as mock_httpx_module:
        mock_httpx_module.Client.return_value = MagicMock()
        with patch.dict(
            "os.environ",
            {"SPEC_ORCH_LINEAR_TOKEN": "", "LINEAR_TOKEN": "fallback-token"},
            clear=False,
        ):
            LinearClient()

    headers = mock_httpx_module.Client.call_args.kwargs["headers"]
    assert headers["Authorization"] == "fallback-token"


def test_get_issue(mock_httpx: MagicMock):
    client = _make_client(mock_httpx)
    mock_httpx.post.return_value = MagicMock(
        json=lambda: {
            "data": {
                "issue": {
                    "id": "uuid-123",
                    "identifier": "SPC-1",
                    "title": "Test issue",
                    "description": "desc",
                    "state": {"name": "Todo"},
                    "labels": {"nodes": []},
                    "assignee": None,
                }
            }
        },
        raise_for_status=MagicMock(),
    )
    issue = client.get_issue("SPC-1")
    assert issue["identifier"] == "SPC-1"
    assert issue["title"] == "Test issue"
    mock_httpx.post.assert_called_once()


def test_get_issue_not_found(mock_httpx: MagicMock):
    client = _make_client(mock_httpx)
    mock_httpx.post.return_value = MagicMock(
        json=lambda: {"data": {"issue": None}},
        raise_for_status=MagicMock(),
    )
    with pytest.raises(ValueError, match="Issue not found"):
        client.get_issue("NONEXIST-1")


def test_list_issues(mock_httpx: MagicMock):
    client = _make_client(mock_httpx)
    mock_httpx.post.return_value = MagicMock(
        json=lambda: {
            "data": {
                "issues": {
                    "nodes": [
                        {"id": "1", "identifier": "SPC-1", "title": "A"},
                        {"id": "2", "identifier": "SPC-2", "title": "B"},
                    ]
                }
            }
        },
        raise_for_status=MagicMock(),
    )
    issues = client.list_issues(team_key="SPC", filter_state="Todo")
    assert len(issues) == 2
    assert issues[0]["identifier"] == "SPC-1"


def test_list_issues_with_assigned_to_me(mock_httpx: MagicMock):
    client = _make_client(mock_httpx)
    mock_httpx.post.return_value = MagicMock(
        json=lambda: {"data": {"issues": {"nodes": []}}},
        raise_for_status=MagicMock(),
    )
    issues = client.list_issues(team_key="SPC", assigned_to_me=True)
    assert issues == []
    call_args = mock_httpx.post.call_args
    query_body = call_args[1]["json"]["query"]
    assert "isMe" in query_body


def test_add_comment(mock_httpx: MagicMock):
    client = _make_client(mock_httpx)
    mock_httpx.post.return_value = MagicMock(
        json=lambda: {
            "data": {
                "commentCreate": {
                    "success": True,
                    "comment": {"id": "c1", "body": "hello"},
                }
            }
        },
        raise_for_status=MagicMock(),
    )
    result = client.add_comment("uuid-123", "hello")
    assert result["success"] is True


def test_update_issue_description(mock_httpx: MagicMock):
    client = _make_client(mock_httpx)
    mock_httpx.post.return_value = MagicMock(
        json=lambda: {
            "data": {
                "issueUpdate": {
                    "success": True,
                    "issue": {"id": "uuid-123", "description": "updated"},
                }
            }
        },
        raise_for_status=MagicMock(),
    )

    result = client.update_issue_description("uuid-123", description="updated")

    assert result["success"] is True
    graphql = mock_httpx.post.call_args.kwargs["json"]["query"]
    variables = mock_httpx.post.call_args.kwargs["json"]["variables"]
    assert "issueUpdate" in graphql
    assert variables["description"] == "updated"


def test_query_graphql_errors(mock_httpx: MagicMock):
    client = _make_client(mock_httpx)
    mock_httpx.post.return_value = MagicMock(
        json=lambda: {"errors": [{"message": "bad request"}]},
        raise_for_status=MagicMock(),
    )
    with pytest.raises(RuntimeError, match="Linear GraphQL errors"):
        client.query("{ viewer { id } }")
