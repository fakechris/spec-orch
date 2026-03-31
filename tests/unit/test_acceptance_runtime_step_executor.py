from __future__ import annotations

import json

from spec_orch.acceptance_core.routing import AcceptanceGraphProfile


def test_compose_step_prompt_reveals_only_current_step_instruction() -> None:
    from spec_orch.acceptance_runtime.graph_models import (
        AcceptanceGraphProfileDefinition,
        AcceptanceGraphStep,
        AcceptanceStepInput,
    )
    from spec_orch.acceptance_runtime.prompts import compose_step_prompt

    graph = AcceptanceGraphProfileDefinition(
        profile=AcceptanceGraphProfile.TUNED_EXPLORATORY,
        steps=[
            AcceptanceGraphStep(key="surface_scan", instruction="scan the surface"),
            AcceptanceGraphStep(key="guided_probe", instruction="probe the surface"),
        ],
    )
    step = graph.steps[0]
    step_input = AcceptanceStepInput(
        mission_id="mission-1",
        round_id=1,
        graph_profile=AcceptanceGraphProfile.TUNED_EXPLORATORY,
        step_key="surface_scan",
        goal="Investigate transcript usability",
        target="/?mission=mission-1&tab=transcript",
        evidence={"browser_evidence": {"tested_routes": ["/"]}},
        prior_outputs={"surface_scan_notes": "old", "guided_probe_notes": "should-hide"},
    )

    system_prompt, user_prompt = compose_step_prompt(graph=graph, step=step, step_input=step_input)

    assert "scan the surface" in user_prompt
    assert "probe the surface" not in user_prompt
    assert "guided_probe_notes" not in user_prompt
    assert "surface_scan_notes" in user_prompt
    assert "Return a JSON object" in system_prompt


def test_execute_acceptance_step_parses_structured_output_from_invoker() -> None:
    from spec_orch.acceptance_runtime.graph_models import (
        AcceptanceGraphProfileDefinition,
        AcceptanceGraphStep,
        AcceptanceStepInput,
    )
    from spec_orch.acceptance_runtime.step_executor import execute_acceptance_step

    captured: dict[str, str] = {}

    def _invoke(system_prompt: str, user_prompt: str) -> str:
        captured["system"] = system_prompt
        captured["user"] = user_prompt
        return json.dumps(
            {
                "decision": "continue",
                "outputs": {"surface_scan_notes": "empty state is ambiguous"},
                "next_transition": "guided_probe",
                "warnings": ["bounded_exploration"],
                "review_markdown": "## Surface Scan\n- ambiguous empty state",
            }
        )

    graph = AcceptanceGraphProfileDefinition(
        profile=AcceptanceGraphProfile.TUNED_EXPLORATORY,
        steps=[AcceptanceGraphStep(key="surface_scan", instruction="scan the surface")],
    )
    step = graph.steps[0]
    step_input = AcceptanceStepInput(
        mission_id="mission-1",
        round_id=1,
        graph_profile=AcceptanceGraphProfile.TUNED_EXPLORATORY,
        step_key="surface_scan",
        goal="Investigate transcript usability",
        target="/?mission=mission-1&tab=transcript",
        evidence={"browser_evidence": {"tested_routes": ["/"]}},
    )

    result = execute_acceptance_step(
        graph=graph,
        step=step,
        step_input=step_input,
        invoke=_invoke,
    )

    assert result.step_key == "surface_scan"
    assert result.decision == "continue"
    assert result.outputs["surface_scan_notes"] == "empty state is ambiguous"
    assert result.next_transition == "guided_probe"
    assert result.review_markdown.startswith("## Surface Scan")
    assert "scan the surface" in captured["user"]
