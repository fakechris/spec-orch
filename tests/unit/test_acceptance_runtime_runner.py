from __future__ import annotations

import json

from spec_orch.acceptance_core.routing import AcceptanceGraphProfile


def test_run_acceptance_graph_executes_steps_and_persists_trace(tmp_path) -> None:
    from spec_orch.acceptance_runtime.graph_registry import graph_definition_for
    from spec_orch.acceptance_runtime.runner import run_acceptance_graph

    seen_steps: list[str] = []

    def _invoke(system_prompt: str, user_prompt: str) -> str:
        payload = json.loads(user_prompt.split("\n", 3)[-1])
        step_key = payload["step_key"]
        seen_steps.append(step_key)
        next_transition = {
            "surface_scan": "guided_probe",
            "guided_probe": "candidate_review",
            "candidate_review": "summarize_judgment",
            "summarize_judgment": "",
        }[step_key]
        return json.dumps(
            {
                "decision": "continue" if next_transition else "complete",
                "outputs": {f"{step_key}_notes": f"artifact for {step_key}"},
                "next_transition": next_transition,
                "warnings": [],
                "review_markdown": f"## {step_key}\n- ok",
            }
        )

    definition = graph_definition_for(AcceptanceGraphProfile.TUNED_EXPLORATORY)
    result = run_acceptance_graph(
        base_dir=tmp_path,
        run_id="agr-1",
        graph=definition,
        mission_id="mission-1",
        round_id=1,
        goal="Dogfood transcript UX",
        target="/?mission=mission-1&tab=transcript",
        evidence={"browser_evidence": {"tested_routes": ["/"]}},
        compare_overlay=False,
        invoke=_invoke,
    )

    assert seen_steps == [
        "surface_scan",
        "guided_probe",
        "candidate_review",
        "summarize_judgment",
    ]
    assert result["graph_profile"] == "tuned_exploratory_graph"
    assert len(result["step_artifacts"]) == 4
    assert result["step_artifacts"][0].endswith("01-surface_scan.json")
    assert (tmp_path / "acceptance_graph_runs" / "agr-1" / "graph_run.json").exists()
    assert (
        tmp_path / "acceptance_graph_runs" / "agr-1" / "steps" / "04-summarize_judgment.json"
    ).exists()
