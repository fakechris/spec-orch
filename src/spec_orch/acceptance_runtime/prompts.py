"""Prompt composition for step-scoped acceptance graph execution."""

from __future__ import annotations

import json

from spec_orch.acceptance_runtime.graph_models import (
    AcceptanceGraphProfileDefinition,
    AcceptanceGraphStep,
    AcceptanceStepInput,
)


def compose_step_prompt(
    *,
    graph: AcceptanceGraphProfileDefinition,
    step: AcceptanceGraphStep,
    step_input: AcceptanceStepInput,
) -> tuple[str, str]:
    allowed_prior_outputs = {
        key: value
        for key, value in step_input.prior_outputs.items()
        if key.startswith(step.key) or key in step.input_keys
    }
    system_prompt = (
        "You are executing one bounded acceptance graph step.\n"
        "Return a JSON object with: decision, outputs, next_transition, warnings, review_markdown."
    )
    user_payload = {
        "graph_profile": step_input.graph_profile.value,
        "step_key": step.key,
        "goal": step_input.goal,
        "target": step_input.target,
        "compare_overlay": step_input.compare_overlay,
        "instruction": step.instruction,
        "allowed_prior_outputs": allowed_prior_outputs,
        "evidence": step_input.evidence,
        "available_graph_steps": [step.key],
    }
    user_prompt = (
        f"Current step: {step.key}\n"
        f"Instruction: {step.instruction}\n"
        "Only reason about this step.\n"
        f"{json.dumps(user_payload, ensure_ascii=False, indent=2)}"
    )
    return system_prompt, user_prompt
