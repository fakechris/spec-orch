"""Bounded graph runner for acceptance runtime."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
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
from spec_orch.runtime_chain.models import (
    ChainPhase,
    RuntimeChainEvent,
    RuntimeChainStatus,
    RuntimeSubjectKind,
)
from spec_orch.runtime_chain.store import append_chain_event, write_chain_status


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
    chain_root: Path | None = None,
    chain_id: str | None = None,
    span_id: str | None = None,
    parent_span_id: str | None = None,
) -> dict[str, Any]:
    subject_id = f"{mission_id}:round-{round_id}:acceptance-graph"
    _emit_chain_status(
        chain_root=chain_root,
        chain_id=chain_id,
        span_id=span_id,
        parent_span_id=parent_span_id,
        subject_id=subject_id,
        phase=ChainPhase.STARTED,
        status_reason="acceptance_graph_started",
    )
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
    try:
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
    except Exception:
        _emit_chain_status(
            chain_root=chain_root,
            chain_id=chain_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            subject_id=subject_id,
            phase=ChainPhase.DEGRADED,
            status_reason="acceptance_graph_failed",
            artifact_refs={"run_dir": str(run_dir)},
        )
        raise

    _emit_chain_status(
        chain_root=chain_root,
        chain_id=chain_id,
        span_id=span_id,
        parent_span_id=parent_span_id,
        subject_id=subject_id,
        phase=ChainPhase.COMPLETED,
        status_reason="acceptance_graph_completed",
        artifact_refs={"graph_run": str(run_dir / "graph_run.json")},
    )
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


def _emit_chain_status(
    *,
    chain_root: Path | None,
    chain_id: str | None,
    span_id: str | None,
    parent_span_id: str | None,
    subject_id: str,
    phase: ChainPhase,
    status_reason: str,
    artifact_refs: dict[str, str] | None = None,
) -> None:
    if chain_root is None or chain_id is None or span_id is None:
        return
    updated_at = datetime.now(UTC).isoformat()
    append_chain_event(
        chain_root,
        RuntimeChainEvent(
            chain_id=chain_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            subject_kind=RuntimeSubjectKind.ACCEPTANCE,
            subject_id=subject_id,
            phase=phase,
            status_reason=status_reason,
            artifact_refs=artifact_refs or {},
            updated_at=updated_at,
        ),
    )
    write_chain_status(
        chain_root,
        RuntimeChainStatus(
            chain_id=chain_id,
            active_span_id=span_id,
            subject_kind=RuntimeSubjectKind.ACCEPTANCE,
            subject_id=subject_id,
            phase=phase,
            status_reason=status_reason,
            artifact_refs=artifact_refs or {},
            updated_at=updated_at,
        ),
    )
