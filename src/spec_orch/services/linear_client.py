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
        variables: dict[str, Any] = {"first": first, "teamKey": team_key}
        filter_parts = ["team: { key: { eq: $teamKey } }"]
        var_defs = "$first: Int!, $teamKey: String!"

        if filter_state:
            variables["filterState"] = filter_state
            filter_parts.append("state: { name: { eq: $filterState } }")
            var_defs += ", $filterState: String!"
        if assigned_to_me:
            filter_parts.append("assignee: { isMe: { eq: true } }")

        filter_str = ", ".join(filter_parts)
        query = (
            f"query({var_defs}) {{\n"
            f"  issues(filter: {{ {filter_str} }}, first: $first) {{\n"
            "    nodes {\n"
            "      id\n"
            "      identifier\n"
            "      title\n"
            "      description\n"
            "      state { name }\n"
            "      labels { nodes { name } }\n"
            "      assignee { name email }\n"
            "    }\n"
            "  }\n"
            "}"
        )
        result = self.query(query, variables=variables)
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

    def resolve_state_id(self, issue_id: str, state_name: str) -> str:
        """Resolve a human-readable state name to its Linear workflow state ID."""
        team_result = self.query(
            """
            query($issueId: String!) {
              issue(id: $issueId) {
                team {
                  states { nodes { id name } }
                }
              }
            }
            """,
            variables={"issueId": issue_id},
        )
        states = (
            team_result.get("issue", {})
            .get("team", {})
            .get("states", {})
            .get("nodes", [])
        )
        for state in states:
            if state.get("name") == state_name:
                state_id: str = state["id"]
                return state_id
        available = [s.get("name", "") for s in states]
        raise ValueError(
            f"State '{state_name}' not found for issue {issue_id}. "
            f"Available states: {available}"
        )

    def update_issue_state(
        self, issue_id: str, state_name: str
    ) -> dict[str, Any]:
        state_id = self.resolve_state_id(issue_id, state_name)
        result = self.query(
            """
            mutation($issueId: String!, $stateId: String!) {
              issueUpdate(id: $issueId, input: { stateId: $stateId }) {
                success
                issue { id state { name } }
              }
            }
            """,
            variables={"issueId": issue_id, "stateId": state_id},
        )
        update: dict[str, Any] = result.get("issueUpdate", {})
        return update

    def close(self) -> None:
        self._client.close()
