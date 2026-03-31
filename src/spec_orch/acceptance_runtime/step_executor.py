"""Execution helpers for a single acceptance graph step."""

from __future__ import annotations

import json
import re
from collections.abc import Callable

from spec_orch.acceptance_runtime.graph_models import (
    AcceptanceGraphProfileDefinition,
    AcceptanceGraphStep,
    AcceptanceStepInput,
    AcceptanceStepResult,
)
from spec_orch.acceptance_runtime.prompts import compose_step_prompt


def _extract_json(raw_output: str) -> dict[str, object]:
    fenced = re.search(r"```json\s*(\{.*?\})\s*```", raw_output, flags=re.DOTALL)
    candidate = fenced.group(1) if fenced else raw_output
    payload = json.loads(candidate)
    if not isinstance(payload, dict):
        raise ValueError("step output must be a JSON object")
    return payload


def execute_acceptance_step(
    *,
    graph: AcceptanceGraphProfileDefinition,
    step: AcceptanceGraphStep,
    step_input: AcceptanceStepInput,
    invoke: Callable[[str, str], str],
) -> AcceptanceStepResult:
    system_prompt, user_prompt = compose_step_prompt(
        graph=graph,
        step=step,
        step_input=step_input,
    )
    raw_output = invoke(system_prompt, user_prompt)
    payload = _extract_json(raw_output)
    return AcceptanceStepResult(
        step_key=step.key,
        decision=str(payload.get("decision") or ""),
        outputs=dict(payload.get("outputs") or {}),
        next_transition=str(payload.get("next_transition") or ""),
        warnings=[str(item) for item in payload.get("warnings", []) if item],
        review_markdown=str(payload.get("review_markdown") or ""),
    )
