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
from spec_orch.runtime_core.observability.budget import build_budget_visibility
from spec_orch.runtime_core.observability.models import (
    RuntimeBatchSummary,
    RuntimeBudgetVisibility,
    RuntimeLiveSummary,
    RuntimeProgressEvent,
    RuntimeRecap,
    RuntimeStepSummary,
)
from spec_orch.runtime_core.observability.progress import (
    build_batch_summary,
    build_step_summary,
    derive_stall_signal,
)
from spec_orch.runtime_core.observability.recap import build_runtime_recap
from spec_orch.runtime_core.observability.store import (
    append_batch_summary,
    append_progress_event,
    append_recap,
    append_step_summary,
    write_live_summary,
)
from spec_orch.services.memory.service import MemoryService


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
    observability_root: Path | None = None,
    memory_service: MemoryService | None = None,
) -> dict[str, Any]:
    subject_id = f"{mission_id}:round-{round_id}:acceptance-graph"
    subject_key = subject_id
    total_steps = len(graph.steps)
    _write_observability_summary(
        observability_root=observability_root,
        summary=RuntimeLiveSummary(
            subject_key=subject_key,
            phase="started",
            status_reason="acceptance_graph_started",
            current_step_key="",
            budget=_budget_visibility(
                graph=graph,
                completed_steps=0,
                loop_budget=loop_budget,
                remaining_loop_budget=loop_budget,
            ),
            updated_at=datetime.now(UTC).isoformat(),
        ),
    )
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
    executed_steps: list[str] = []
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
            executed_steps.append(step.key)
            prior_outputs.update(result.outputs)
            persisted = write_step_artifact(run_dir, artifact_index, result)
            step_paths.append(persisted["json_path"])
            completed_steps = len(step_paths)
            budget = _budget_visibility(
                graph=graph,
                completed_steps=completed_steps,
                loop_budget=loop_budget,
                remaining_loop_budget=remaining_loop_budget,
            )
            stall_signal = derive_stall_signal(
                repeated_steps=transitions.count(f"{step.key}->{step.key}")
                + int(result.decision == "loop" and result.next_transition == step.key),
                idle_seconds=0,
                low_yield=step.key == "summarize_judgment",
            )
            _append_observability_progress(
                observability_root=observability_root,
                event=RuntimeProgressEvent(
                    subject_key=subject_key,
                    phase="running",
                    step_key=step.key,
                    message=f"Completed step {step.key}",
                    budget=budget,
                    stall_signal=stall_signal,
                    artifact_refs={"step_artifact": persisted["json_path"]},
                    updated_at=datetime.now(UTC).isoformat(),
                ),
            )
            _append_step_summary(
                observability_root=observability_root,
                summary=build_step_summary(
                    subject_key=subject_key,
                    step_key=step.key,
                    summary=result.review_markdown.strip() or f"Completed step {step.key}",
                    artifact_refs={"step_artifact": persisted["json_path"]},
                    updated_at=datetime.now(UTC).isoformat(),
                ),
            )
            _write_observability_summary(
                observability_root=observability_root,
                summary=RuntimeLiveSummary(
                    subject_key=subject_key,
                    phase="running",
                    status_reason="step_completed",
                    current_step_key=step.key,
                    budget=budget,
                    stall_signal=stall_signal,
                    artifact_refs={"last_step_artifact": persisted["json_path"]},
                    updated_at=datetime.now(UTC).isoformat(),
                ),
            )
            if memory_service is not None and memory_service.should_snapshot_session(
                completed_steps
            ):
                facts = [
                    line.strip() for line in result.review_markdown.splitlines() if line.strip()
                ]
                memory_service.record_session_snapshot(
                    session_id=run_id,
                    subject_kind="acceptance_graph",
                    subject_id=subject_key,
                    event_count=completed_steps,
                    facts=facts[:6],
                    artifact_refs={
                        "step_artifact": persisted["json_path"],
                        "graph_run": str(run_dir / "graph_run.json"),
                    },
                )
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
        _write_observability_summary(
            observability_root=observability_root,
            summary=RuntimeLiveSummary(
                subject_key=subject_key,
                phase="degraded",
                status_reason="acceptance_graph_failed",
                current_step_key=graph.steps[step_index].key if step_index < total_steps else "",
                budget=_budget_visibility(
                    graph=graph,
                    completed_steps=len(step_paths),
                    loop_budget=loop_budget,
                    remaining_loop_budget=remaining_loop_budget,
                ),
                artifact_refs={"graph_run": str(run_dir / "graph_run.json")},
                updated_at=datetime.now(UTC).isoformat(),
            ),
        )
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

    final_budget = _budget_visibility(
        graph=graph,
        completed_steps=len(step_paths),
        loop_budget=loop_budget,
        remaining_loop_budget=remaining_loop_budget,
    )
    _write_observability_summary(
        observability_root=observability_root,
        summary=RuntimeLiveSummary(
            subject_key=subject_key,
            phase="completed",
            status_reason="acceptance_graph_completed",
            current_step_key=graph.steps[-1].key if graph.steps else "",
            budget=final_budget,
            artifact_refs={"graph_run": str(run_dir / "graph_run.json")},
            updated_at=datetime.now(UTC).isoformat(),
        ),
    )
    _append_batch_summary(
        observability_root=observability_root,
        summary=build_batch_summary(
            subject_key=subject_key,
            batch_key=f"{graph.profile.value}:full-run",
            steps=list(executed_steps),
            summary=f"Completed acceptance graph with {len(step_paths)} steps",
            artifact_refs={"graph_run": str(run_dir / "graph_run.json")},
            updated_at=datetime.now(UTC).isoformat(),
        ),
    )
    _append_observability_recap(
        observability_root=observability_root,
        recap=build_runtime_recap(
            subject_key=subject_key,
            title="Acceptance graph completed",
            bullets=[
                f"{len(step_paths)} steps completed",
                f"final transition: {final_transition or 'none'}",
                f"graph profile: {graph.profile.value}",
            ],
            artifact_refs={"graph_run": str(run_dir / "graph_run.json")},
            updated_at=datetime.now(UTC).isoformat(),
        ),
    )
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


def _budget_visibility(
    *,
    graph: AcceptanceGraphProfileDefinition,
    completed_steps: int,
    loop_budget: int,
    remaining_loop_budget: int,
) -> RuntimeBudgetVisibility:
    planned_steps = len(graph.steps)
    return build_budget_visibility(
        budget_key=graph.profile.value,
        planned_steps=planned_steps,
        completed_steps=completed_steps,
        loop_budget=max(0, loop_budget),
        remaining_loop_budget=max(0, remaining_loop_budget),
    )


def _append_observability_progress(
    *,
    observability_root: Path | None,
    event: RuntimeProgressEvent,
) -> None:
    if observability_root is None:
        return
    append_progress_event(observability_root, event)


def _write_observability_summary(
    *,
    observability_root: Path | None,
    summary: RuntimeLiveSummary,
) -> None:
    if observability_root is None:
        return
    write_live_summary(observability_root, summary)


def _append_observability_recap(
    *,
    observability_root: Path | None,
    recap: RuntimeRecap,
) -> None:
    if observability_root is None:
        return
    append_recap(observability_root, recap)


def _append_step_summary(
    *,
    observability_root: Path | None,
    summary: RuntimeStepSummary,
) -> None:
    if observability_root is None:
        return
    append_step_summary(observability_root, summary)


def _append_batch_summary(
    *,
    observability_root: Path | None,
    summary: RuntimeBatchSummary,
) -> None:
    if observability_root is None:
        return
    append_batch_summary(observability_root, summary)


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
