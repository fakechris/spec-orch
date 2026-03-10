from __future__ import annotations

import os
from typing import Any

import httpx

LINEAR_API_URL = "https://api.linear.app/graphql"


class LinearClient:
    def __init__(
        self,
        *,
        token: str | None = None,
        token_env: str = "SPEC_ORCH_LINEAR_TOKEN",
    ) -> None:
        resolved = token or os.environ.get(token_env, "")
        if not resolved:
            raise ValueError(
                f"Linear API token required. Set {token_env} or pass token= explicitly."
            )
        self._client = httpx.Client(
            base_url=LINEAR_API_URL,
            headers={"Authorization": resolved, "Content-Type": "application/json"},
            timeout=30.0,
        )

    def query(self, graphql: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"query": graphql}
        if variables:
            payload["variables"] = variables
        resp = self._client.post("", json=payload)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        if "errors" in data:
            raise RuntimeError(f"Linear GraphQL errors: {data['errors']}")
        result: dict[str, Any] = data.get("data", {})
        return result

    def get_issue(self, issue_id: str) -> dict[str, Any]:
        result = self.query(
            """
            query($id: String!) {
              issue(id: $id) {
                id
                identifier
                title
                description
                state { name }
                labels { nodes { name } }
                assignee { name email }
              }
            }
            """,
            variables={"id": issue_id},
        )
        issue: dict[str, Any] | None = result.get("issue")
        if not issue:
            raise ValueError(f"Issue not found: {issue_id}")
        return issue

    def list_issues(
        self,
        *,
        team_key: str,
        filter_state: str | None = None,
        assigned_to_me: bool = False,
        first: int = 50,
    ) -> list[dict[str, Any]]:
        filter_parts = [f'team: {{ key: {{ eq: "{team_key}" }} }}']
        if filter_state:
            filter_parts.append(f'state: {{ name: {{ eq: "{filter_state}" }} }}')
        if assigned_to_me:
            filter_parts.append("assignee: { isMe: { eq: true } }")
        filter_str = ", ".join(filter_parts)
        result = self.query(
            f"""
            query($first: Int!) {{
              issues(filter: {{ {filter_str} }}, first: $first) {{
                nodes {{
                  id
                  identifier
                  title
                  description
                  state {{ name }}
                  labels {{ nodes {{ name }} }}
                  assignee {{ name email }}
                }}
              }}
            }}
            """,
            variables={"first": first},
        )
        nodes: list[dict[str, Any]] = result.get("issues", {}).get("nodes", [])
        return nodes

    def add_comment(self, issue_id: str, body: str) -> dict[str, Any]:
        result = self.query(
            """
            mutation($issueId: String!, $body: String!) {
              commentCreate(input: { issueId: $issueId, body: $body }) {
                success
                comment { id body }
              }
            }
            """,
            variables={"issueId": issue_id, "body": body},
        )
        create: dict[str, Any] = result.get("commentCreate", {})
        return create

    def update_issue_state(
        self, issue_id: str, state_name: str
    ) -> dict[str, Any]:
        result = self.query(
            """
            mutation($issueId: String!, $stateId: String!) {
              issueUpdate(id: $issueId, input: { stateId: $stateId }) {
                success
                issue { id state { name } }
              }
            }
            """,
            variables={"issueId": issue_id, "stateId": state_name},
        )
        update: dict[str, Any] = result.get("issueUpdate", {})
        return update

    def close(self) -> None:
        self._client.close()
