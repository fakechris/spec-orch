"""LiteLLM-backed PlannerAdapter for autonomous Spec stage.

Requires the ``planner`` extra: ``pip install spec-orch[planner]``.
When running inside a coding environment (Cursor / Claude Code) the user
drives the spec stage via CLI commands instead — no LLM call needed.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from spec_orch.domain.models import (
    Issue,
    PlannerResult,
    Question,
    SpecSnapshot,
)

PLANNER_SYSTEM_PROMPT = """\
You are a technical planning assistant for SpecOrch.
Your job is to analyse a development issue and produce:
1. A list of clarifying **questions** that must be answered before implementation.
2. Optionally, a draft **spec** if you have enough information.

Each question must be a JSON object with these fields:
  id (string), asked_by ("planner"), target ("user"),
  category ("requirement" | "environment" | "architecture" | "risk"),
  blocking (boolean), text (string).

Respond with a JSON object:
{
  "questions": [ ... ],
  "spec_summary": "optional one-paragraph spec summary or null"
}
Do NOT include anything outside this JSON object.\
"""

_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "submit_plan_output",
            "description": "Submit the planner's analysis: questions and optional spec summary.",
            "parameters": {
                "type": "object",
                "properties": {
                    "questions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "category": {
                                    "type": "string",
                                    "enum": [
                                        "requirement",
                                        "environment",
                                        "architecture",
                                        "risk",
                                    ],
                                },
                                "blocking": {"type": "boolean"},
                                "text": {"type": "string"},
                            },
                            "required": ["id", "category", "blocking", "text"],
                        },
                    },
                    "spec_summary": {"type": ["string", "null"]},
                },
                "required": ["questions"],
            },
        },
    }
]


class LiteLLMPlannerAdapter:
    """Autonomous planner that calls an LLM via LiteLLM."""

    ADAPTER_NAME: str = "litellm_planner"

    def __init__(
        self,
        *,
        model: str = "anthropic/claude-sonnet-4-20250514",
        api_key: str | None = None,
        api_base: str | None = None,
        temperature: float = 0.3,
    ) -> None:
        self.model = model
        self.api_key = api_key or os.environ.get("SPEC_ORCH_LLM_API_KEY")
        self.api_base = api_base or os.environ.get("SPEC_ORCH_LLM_API_BASE")
        self.temperature = temperature

    def plan(
        self,
        *,
        issue: Issue,
        workspace: Path,
        existing_snapshot: SpecSnapshot | None = None,
    ) -> PlannerResult:
        try:
            import litellm
        except ImportError as exc:
            raise ImportError(
                "litellm is required for LiteLLMPlannerAdapter. "
                "Install with: pip install spec-orch[planner]"
            ) from exc

        user_message = self._build_user_message(issue, existing_snapshot)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            "temperature": self.temperature,
            "tools": _TOOLS,
            "tool_choice": {"type": "function", "function": {"name": "submit_plan_output"}},
        }
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.api_base:
            kwargs["api_base"] = self.api_base

        response = litellm.completion(**kwargs)
        return self._parse_response(response, issue)

    def _build_user_message(
        self,
        issue: Issue,
        existing_snapshot: SpecSnapshot | None,
    ) -> str:
        parts = [
            f"## Issue: {issue.issue_id}",
            f"**Title**: {issue.title}",
            f"**Summary**: {issue.summary}",
        ]
        if issue.builder_prompt:
            parts.append(f"\n**Builder Prompt**:\n{issue.builder_prompt}")
        if issue.acceptance_criteria:
            parts.append("\n**Acceptance Criteria**:")
            for criterion in issue.acceptance_criteria:
                parts.append(f"- {criterion}")
        if issue.context.architecture_notes:
            parts.append(f"\n**Architecture Notes**:\n{issue.context.architecture_notes}")
        if issue.context.constraints:
            parts.append("\n**Constraints**:")
            for c in issue.context.constraints:
                parts.append(f"- {c}")
        if existing_snapshot:
            parts.append(f"\n**Existing Spec** (v{existing_snapshot.version}):")
            if existing_snapshot.questions:
                parts.append("Previous questions:")
                for q in existing_snapshot.questions:
                    status = f" → {q.answer}" if q.answer else " (unanswered)"
                    parts.append(f"  - [{q.category}] {q.text}{status}")
        return "\n".join(parts)

    def _parse_response(self, response: Any, issue: Issue) -> PlannerResult:
        message = response.choices[0].message

        raw_text = ""
        parsed: dict[str, Any] = {}

        if hasattr(message, "tool_calls") and message.tool_calls:
            tool_call = message.tool_calls[0]
            raw_text = tool_call.function.arguments
            parsed = json.loads(raw_text)
        elif hasattr(message, "content") and message.content:
            raw_text = message.content
            parsed = json.loads(raw_text)

        questions = [
            Question(
                id=q.get("id", f"q-{uuid.uuid4().hex[:8]}"),
                asked_by="planner",
                target="user",
                category=q.get("category", "requirement"),
                blocking=q.get("blocking", True),
                text=q["text"],
            )
            for q in parsed.get("questions", [])
        ]

        return PlannerResult(
            questions=questions,
            raw_response=raw_text,
        )
