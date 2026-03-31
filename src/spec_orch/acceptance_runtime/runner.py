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
    for index, step in enumerate(graph.steps, start=1):
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
        persisted = write_step_artifact(run_dir, index, result)
        step_paths.append(persisted["json_path"])
        final_transition = result.next_transition

    return {
        "graph_run": str(run_dir / "graph_run.json"),
        "graph_profile": graph.profile.value,
        "step_artifacts": step_paths,
        "final_transition": final_transition,
    }
