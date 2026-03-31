"""Execution helpers for a single acceptance graph step."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Mapping
from typing import Any, cast

from spec_orch.acceptance_runtime.graph_models import (
    AcceptanceGraphProfileDefinition,
    AcceptanceGraphStep,
    AcceptanceStepInput,
    AcceptanceStepResult,
)
from spec_orch.acceptance_runtime.prompts import compose_step_prompt


def _parse_json_object_from_text(raw_text: str) -> dict[str, object]:
    decoder = json.JSONDecoder()
    last_error: ValueError | None = None
    for match in re.finditer(r"\{", raw_text):
        start = match.start()
        try:
            payload, _end = decoder.raw_decode(raw_text[start:])
        except ValueError as exc:
            last_error = exc
            continue
        if isinstance(payload, dict):
            return payload
    if last_error is not None:
        raise ValueError("step output contained an unbalanced JSON object") from last_error
    raise ValueError("step output did not contain a JSON object")


def _extract_json(raw_output: str) -> dict[str, object]:
    fenced = re.search(r"```json\s*([\s\S]*?)\s*```", raw_output, flags=re.DOTALL)
    candidate = fenced.group(1) if fenced else raw_output
    return _parse_json_object_from_text(candidate)


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
    raw_outputs = payload.get("outputs")
    outputs: dict[str, Any] = (
        dict(cast(Mapping[str, Any], raw_outputs)) if isinstance(raw_outputs, Mapping) else {}
    )
    raw_warnings = payload.get("warnings", [])
    warning_items: Iterable[object]
    if isinstance(raw_warnings, Iterable) and not isinstance(raw_warnings, (str, bytes)):
        warning_items = raw_warnings
    else:
        warning_items = []
    return AcceptanceStepResult(
        step_key=step.key,
        decision=str(payload.get("decision") or ""),
        outputs=outputs,
        next_transition=str(payload.get("next_transition") or ""),
        warnings=[str(item) for item in warning_items if item],
        review_markdown=str(payload.get("review_markdown") or ""),
    )
