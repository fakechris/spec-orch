"""Bounded graph runner for acceptance runtime."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from spec_orch.acceptance_runtime.artifacts import (
    graph_run_dir,
    write_graph_run,
    write_step_artifact,
)
from spec_orch.acceptance_runtime.graph_models import (
    AcceptanceGraphProfileDefinition,
    AcceptanceGraphRun,
    AcceptanceStepInput,
)
from spec_orch.acceptance_runtime.step_executor import execute_acceptance_step


def run_acceptance_graph(
    *,
    base_dir: Path,
    run_id: str,
    graph: AcceptanceGraphProfileDefinition,
    mission_id: str,
    round_id: int,
    goal: str,
    target: str,
    evidence: dict[str, Any],
    compare_overlay: bool,
    invoke: Callable[[str, str], str],
    loop_budget: int = 1,
) -> dict[str, Any]:
    run = AcceptanceGraphRun(
        run_id=run_id,
        mission_id=mission_id,
        round_id=round_id,
        graph_profile=graph.profile,
        step_keys=[step.key for step in graph.steps],
        compare_overlay=compare_overlay,
    )
    run_dir = graph_run_dir(base_dir, run_id)
    write_graph_run(run_dir, run)

    prior_outputs: dict[str, Any] = {}
    step_paths: list[str] = []
    final_transition = ""
    transitions: list[str] = []
    step_index = 0
    artifact_index = 1
    remaining_loop_budget = max(0, loop_budget)
    while step_index < len(graph.steps):
        step = graph.steps[step_index]
        if step.key == "candidate_review" and not _has_reviewable_observations(prior_outputs):
            step_index += 1
            continue
        step_input = AcceptanceStepInput(
            mission_id=mission_id,
            round_id=round_id,
            graph_profile=graph.profile,
            step_key=step.key,
            goal=goal,
            target=target,
            evidence=evidence,
            prior_outputs=prior_outputs,
            compare_overlay=compare_overlay,
        )
        result = execute_acceptance_step(
            graph=graph,
            step=step,
            step_input=step_input,
            invoke=invoke,
        )
        prior_outputs.update(result.outputs)
        persisted = write_step_artifact(run_dir, artifact_index, result)
        step_paths.append(persisted["json_path"])
        artifact_index += 1
        next_transition = result.next_transition
        if next_transition == "candidate_review" and not _has_reviewable_observations(
            prior_outputs
        ):
            next_transition = "summarize_judgment"
        final_transition = next_transition
        if next_transition:
            transitions.append(f"{step.key}->{next_transition}")
        if (
            graph.loop_step_key
            and step.key == graph.loop_step_key
            and result.decision == "loop"
            and next_transition == step.key
            and remaining_loop_budget > 0
        ):
            remaining_loop_budget -= 1
            continue
        step_index += 1

    return {
        "graph_run": str(run_dir / "graph_run.json"),
        "graph_profile": graph.profile.value,
        "step_artifacts": step_paths,
        "graph_transitions": transitions,
        "final_transition": final_transition,
    }


def _has_reviewable_observations(prior_outputs: dict[str, Any]) -> bool:
    observations = prior_outputs.get("observations")
    if isinstance(observations, list) and observations:
        return True
    candidate_ids = prior_outputs.get("candidate_ids")
    if isinstance(candidate_ids, list) and candidate_ids:
        return True
    reviewable = prior_outputs.get("reviewable_observations")
    return isinstance(reviewable, list) and bool(reviewable)
