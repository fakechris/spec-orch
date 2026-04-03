from __future__ import annotations

import os
from typing import Any

import httpx

LINEAR_API_URL = "https://api.linear.app/graphql"
LINEAR_TOKEN_FALLBACKS = ("LINEAR_TOKEN", "LINEAR_API_TOKEN")


def resolve_linear_token(
    *,
    token: str | None = None,
    token_env: str = "SPEC_ORCH_LINEAR_TOKEN",
) -> str:
    if token:
        return token
    configured = os.environ.get(token_env, "")
    if configured:
        return configured
    for fallback in LINEAR_TOKEN_FALLBACKS:
        value = os.environ.get(fallback, "")
        if value:
            return value
    return ""


class LinearClient:
    def __init__(
        self,
        *,
        token: str | None = None,
        token_env: str = "SPEC_ORCH_LINEAR_TOKEN",
    ) -> None:
        resolved = resolve_linear_token(token=token, token_env=token_env)
        if not resolved:
            fallback_names = ", ".join(LINEAR_TOKEN_FALLBACKS)
            raise ValueError(
                "Linear API token required. "
                f"Set {token_env}, {fallback_names}, or pass token= explicitly."
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
        filter_labels: list[str] | None = None,
        exclude_labels: list[str] | None = None,
        exclude_parents: bool = False,
        assigned_to_me: bool = False,
        first: int = 50,
    ) -> list[dict[str, Any]]:
        variables: dict[str, Any] = {"first": first, "teamKey": team_key}
        filter_parts = ["{ team: { key: { eq: $teamKey } } }"]
        var_defs = "$first: Int!, $teamKey: String!"

        if filter_state:
            variables["filterState"] = filter_state
            filter_parts.append("{ state: { name: { eq: $filterState } } }")
            var_defs += ", $filterState: String!"
        if assigned_to_me:
            filter_parts.append("{ assignee: { isMe: { eq: true } } }")
        if filter_labels:
            label_list = ", ".join(f'"{lb}"' for lb in filter_labels)
            filter_parts.append(f"{{ labels: {{ some: {{ name: {{ in: [{label_list}] }} }} }} }}")
        if exclude_labels:
            excl_list = ", ".join(f'"{lb}"' for lb in exclude_labels)
            filter_parts.append(f"{{ labels: {{ every: {{ name: {{ nin: [{excl_list}] }} }} }} }}")

        child_fields = ""
        if exclude_parents:
            child_fields = "\n      children { nodes { id } }"

        filter_str = ", ".join(filter_parts)
        query = (
            f"query({var_defs}) {{\n"
            f"  issues(filter: {{ and: [{filter_str}] }}, first: $first) {{\n"
            "    nodes {\n"
            "      id\n"
            "      identifier\n"
            "      title\n"
            "      description\n"
            "      state { name }\n"
            "      labels { nodes { name } }\n"
            "      assignee { name email }"
            f"{child_fields}\n"
            "    }\n"
            "  }\n"
            "}"
        )
        result = self.query(query, variables=variables)
        nodes: list[dict[str, Any]] = result.get("issues", {}).get("nodes", [])

        if exclude_parents:
            nodes = [n for n in nodes if not n.get("children", {}).get("nodes")]

        return nodes

    def create_issue(
        self,
        *,
        team_key: str,
        title: str,
        description: str = "",
    ) -> dict[str, Any]:
        """Create a new issue in the given team."""
        team_result = self.query(
            """
            query($key: String!) {
              teams(filter: { key: { eq: $key } }) {
                nodes { id }
              }
            }
            """,
            variables={"key": team_key},
        )
        teams = team_result.get("teams", {}).get("nodes", [])
        if not teams:
            raise ValueError(f"Team not found: {team_key}")
        team_id: str = teams[0]["id"]

        result = self.query(
            """
            mutation($teamId: String!, $title: String!, $description: String) {
              issueCreate(input: {
                teamId: $teamId, title: $title, description: $description
              }) {
                success
                issue { id identifier title }
              }
            }
            """,
            variables={
                "teamId": team_id,
                "title": title,
                "description": description,
            },
        )
        create_data: dict[str, Any] = result.get("issueCreate", {})
        issue: dict[str, Any] = create_data.get("issue", {})
        return issue

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

    def update_issue_description(
        self,
        issue_id: str,
        *,
        description: str,
        title: str | None = None,
    ) -> dict[str, Any]:
        if title is None:
            result = self.query(
                """
                mutation($issueId: String!, $description: String!) {
                  issueUpdate(id: $issueId, input: { description: $description }) {
                    success
                    issue { id description }
                  }
                }
                """,
                variables={"issueId": issue_id, "description": description},
            )
        else:
            result = self.query(
                """
                mutation($issueId: String!, $description: String!, $title: String!) {
                  issueUpdate(id: $issueId, input: { description: $description, title: $title }) {
                    success
                    issue { id title description }
                  }
                }
                """,
                variables={"issueId": issue_id, "description": description, "title": title},
            )
        update: dict[str, Any] = result.get("issueUpdate", {})
        return update

    def list_comments(
        self,
        issue_id: str,
        *,
        first: int = 50,
    ) -> list[dict[str, Any]]:
        """Fetch comments for an issue, ordered by creation time."""
        result = self.query(
            """
            query($issueId: String!, $first: Int!) {
              issue(id: $issueId) {
                comments(first: $first, orderBy: createdAt) {
                  nodes {
                    id
                    body
                    createdAt
                    user { id name email }
                  }
                }
              }
            }
            """,
            variables={"issueId": issue_id, "first": first},
        )
        issue = result.get("issue")
        if not issue:
            return []
        nodes: list[dict[str, Any]] = issue.get("comments", {}).get("nodes", [])
        return nodes

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
        states = team_result.get("issue", {}).get("team", {}).get("states", {}).get("nodes", [])
        for state in states:
            if state.get("name") == state_name:
                state_id: str = state["id"]
                return state_id
        available = [s.get("name", "") for s in states]
        raise ValueError(
            f"State '{state_name}' not found for issue {issue_id}. Available states: {available}"
        )

    def update_issue_state(self, issue_id: str, state_name: str) -> dict[str, Any]:
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

    def add_label(self, issue_id: str, label_name: str) -> None:
        """Add a label to an issue by name. Resolves label ID automatically."""
        label_id = self._resolve_label_id(label_name)
        issue = self.get_issue(issue_id)
        existing = [n["name"] for n in issue.get("labels", {}).get("nodes", [])]
        if label_name in existing:
            return
        all_label_ids = [self._resolve_label_id(n) for n in existing]
        all_label_ids.append(label_id)
        self.query(
            """
            mutation($id: String!, $labelIds: [String!]!) {
                issueUpdate(id: $id, input: { labelIds: $labelIds }) {
                    success
                }
            }
            """,
            variables={"id": issue["id"], "labelIds": all_label_ids},
        )

    def remove_label(self, issue_id: str, label_name: str) -> None:
        """Remove a label from an issue by name."""
        issue = self.get_issue(issue_id)
        existing = [n["name"] for n in issue.get("labels", {}).get("nodes", [])]
        if label_name not in existing:
            return
        remaining_ids = [self._resolve_label_id(n) for n in existing if n != label_name]
        self.query(
            """
            mutation($id: String!, $labelIds: [String!]!) {
                issueUpdate(id: $id, input: { labelIds: $labelIds }) {
                    success
                }
            }
            """,
            variables={"id": issue["id"], "labelIds": remaining_ids},
        )

    def _resolve_label_id(self, label_name: str) -> str:
        result = self.query(
            """
            query($name: String!) {
                issueLabels(filter: { name: { eq: $name } }) {
                    nodes { id name }
                }
            }
            """,
            variables={"name": label_name},
        )
        nodes = result.get("issueLabels", {}).get("nodes", [])
        if not nodes:
            raise ValueError(f"Label not found: {label_name}")
        label_id: str = nodes[0]["id"]
        return label_id

    def close(self) -> None:
        self._client.close()
