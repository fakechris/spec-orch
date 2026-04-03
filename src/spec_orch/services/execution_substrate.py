from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from spec_orch.domain.operator_semantics import (
    ActiveWork,
    AdmissionDecision,
    Agent,
    ExecutionEvent,
    ExecutionSession,
    OperatorIntervention,
    PressureSignal,
    QueueEntry,
    ResourceBudget,
    Runtime,
)
from spec_orch.runtime_chain.models import (
    ChainPhase,
    RuntimeChainEvent,
    RuntimeChainStatus,
    RuntimeSubjectKind,
)
from spec_orch.runtime_chain.store import read_chain_events, read_chain_status
from spec_orch.runtime_core.observability.store import read_live_summary
from spec_orch.services.operator_semantics import execution_session_from_runtime_chain_status

_LOCAL_RUNTIME_ID = "runtime:local"


def _discover_chain_roots(repo_root: Path) -> list[Path]:
    roots: list[Path] = []
    for path in (repo_root / "docs" / "specs").glob("*/operator/runtime_chain"):
        if (path / "chain_status.json").exists():
            roots.append(path)
    for base in (repo_root / ".worktrees", repo_root / ".spec_orch_runs"):
        if not base.exists():
            continue
        for path in base.glob("*/telemetry/runtime_chain"):
            if (path / "chain_status.json").exists():
                roots.append(path)
    return sorted(roots)


def _workspace_id_for_chain_root(
    repo_root: Path,
    chain_root: Path,
    status: RuntimeChainStatus,
) -> str:
    try:
        relative = chain_root.relative_to(repo_root)
    except ValueError:
        return status.subject_id
    parts = relative.parts
    if len(parts) >= 4 and parts[0] == "docs" and parts[1] == "specs":
        return parts[2]
    if len(parts) >= 3 and parts[0] in {".worktrees", ".spec_orch_runs"}:
        return parts[1]
    return status.subject_id


def _workspace_id_for_operator_path(repo_root: Path, operator_path: Path) -> str:
    try:
        relative = operator_path.relative_to(repo_root)
    except ValueError:
        return operator_path.parent.name
    parts = relative.parts
    if len(parts) >= 4 and parts[0] == "docs" and parts[1] == "specs":
        return parts[2]
    return operator_path.parent.name


def _health_from_phase(phase: ChainPhase) -> str:
    if phase in {ChainPhase.STARTED, ChainPhase.HEARTBEAT}:
        return "active"
    if phase is ChainPhase.COMPLETED:
        return "healthy"
    if phase is ChainPhase.DEGRADED:
        return "degraded"
    return "failed"


def _available_actions_for_health(health: str) -> list[str]:
    if health == "active":
        return ["cancel", "takeover"]
    if health in {"degraded", "failed"}:
        return ["retry", "takeover"]
    return []


def _agent_identity(status: RuntimeChainStatus) -> tuple[str, str, str]:
    mapping = {
        RuntimeSubjectKind.ISSUE: ("run_controller", "Run Controller", "issue_execution"),
        RuntimeSubjectKind.MISSION: ("mission_supervisor", "Mission Supervisor", "supervision"),
        RuntimeSubjectKind.ROUND: ("round_supervisor", "Round Supervisor", "supervision"),
        RuntimeSubjectKind.PACKET: ("packet_worker", "Packet Worker", "execution"),
        RuntimeSubjectKind.SUPERVISOR: ("supervisor", "Supervisor", "supervision"),
        RuntimeSubjectKind.ACCEPTANCE: (
            "acceptance_evaluator",
            "Acceptance Evaluator",
            "acceptance",
        ),
        RuntimeSubjectKind.REPLAY: ("replay_runtime", "Replay Runtime", "replay"),
    }
    return mapping.get(
        status.subject_kind,
        ("runtime_operator", "Runtime Operator", "execution"),
    )


def _active_work_from_status(
    *,
    workspace_id: str,
    status: RuntimeChainStatus,
) -> ActiveWork:
    health = _health_from_phase(status.phase)
    agent_id, _name, _role = _agent_identity(status)
    return ActiveWork(
        active_work_id=f"{workspace_id}:{status.active_span_id}",
        workspace_id=workspace_id,
        subject_id=status.subject_id,
        subject_kind=status.subject_kind.value,
        agent_id=agent_id,
        runtime_id=_LOCAL_RUNTIME_ID,
        phase=status.phase.value,
        health=health,
        status_reason=status.status_reason,
        started_at=status.updated_at,
        updated_at=status.updated_at,
        available_actions=_available_actions_for_health(health),
    )


def _agent_from_status(*, workspace_id: str, status: RuntimeChainStatus) -> Agent:
    agent_id, name, role = _agent_identity(status)
    return Agent(
        agent_id=agent_id,
        name=name,
        role=role,
        status=_health_from_phase(status.phase),
        runtime_id=_LOCAL_RUNTIME_ID,
        active_workspace_id=workspace_id,
        last_active_at=status.updated_at,
        recent_subject_refs=[f"{status.subject_kind.value}:{status.subject_id}"],
    )


def _read_jsonl_dicts(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _discover_operator_dirs(repo_root: Path) -> list[Path]:
    return sorted(
        path for path in (repo_root / "docs" / "specs").glob("*/operator") if path.exists()
    )


def _subject_kind_for_queue_payload(payload: dict[str, Any]) -> str:
    round_id = str(payload.get("round_id", "")).strip()
    if round_id:
        return "round"
    return "mission"


def _collect_queue_and_interventions(
    repo_root: Path,
) -> tuple[list[QueueEntry], list[OperatorIntervention]]:
    pending_queue_rows: list[tuple[str, dict[str, Any], dict[str, Any] | None, Path]] = []
    interventions: list[OperatorIntervention] = []

    for operator_dir in _discover_operator_dirs(repo_root):
        workspace_id = _workspace_id_for_operator_path(repo_root, operator_dir)
        response_map: dict[str, dict[str, Any]] = {}
        for payload in _read_jsonl_dicts(operator_dir / "intervention_responses.jsonl"):
            intervention_id = str(payload.get("intervention_id", "")).strip()
            if not intervention_id:
                continue
            current = response_map.get(intervention_id)
            payload_ts = str(payload.get("timestamp", "")).strip()
            current_ts = str(current.get("timestamp", "")).strip() if current else ""
            if current is None or payload_ts >= current_ts:
                response_map[intervention_id] = payload

        for payload in _read_jsonl_dicts(operator_dir / "interventions.jsonl"):
            intervention_id = str(payload.get("intervention_id", "")).strip()
            if not intervention_id:
                continue
            latest_response = response_map.get(intervention_id)
            raw_status = str(payload.get("status", "")).strip().lower() or "open"
            response_effect = (
                str(latest_response.get("effect", "")).strip().lower() if latest_response else ""
            )
            outcome = response_effect or raw_status
            outcome_reason = (
                str(latest_response.get("message", "")).strip()
                if latest_response
                else str(payload.get("summary", "")).strip()
            )
            audit_refs = [str(operator_dir / "interventions.jsonl")]
            review_route = str(payload.get("review_route", "")).strip()
            if review_route:
                audit_refs.append(review_route)
            if latest_response is not None:
                audit_refs.append(str(operator_dir / "intervention_responses.jsonl"))
            interventions.append(
                OperatorIntervention(
                    intervention_id=intervention_id,
                    workspace_id=workspace_id,
                    action=str(payload.get("point_key", "")).strip() or "intervention_review",
                    requested_by="decision_core",
                    requested_at=str(payload.get("created_at", "")).strip(),
                    outcome=outcome or "open",
                    outcome_reason=outcome_reason,
                    audit_refs=audit_refs,
                )
            )
            if outcome in {"resolved", "cancelled", "approved", "rejected"}:
                continue
            pending_queue_rows.append((workspace_id, payload, latest_response, operator_dir))

    pending_queue_rows.sort(key=lambda item: str(item[1].get("created_at", "")).strip())
    queue_entries: list[QueueEntry] = []
    for position, (workspace_id, payload, latest_response, _operator_dir) in enumerate(
        pending_queue_rows,
        start=1,
    ):
        intervention_id = str(payload.get("intervention_id", "")).strip()
        round_id = str(payload.get("round_id", "")).strip()
        subject_id = workspace_id
        if round_id:
            subject_id = f"{workspace_id}:round-{round_id}"
        queue_entries.append(
            QueueEntry(
                queue_entry_id=f"{workspace_id}:{intervention_id}",
                workspace_id=workspace_id,
                subject_id=subject_id,
                queue_name="operator_intervention",
                position=position,
                queue_state="defer",
                claimed_by_agent_id=(
                    str(latest_response.get("channel", "")).strip() if latest_response else ""
                ),
                claimed_at=(
                    str(latest_response.get("timestamp", "")).strip()
                    if latest_response
                    else str(payload.get("created_at", "")).strip()
                ),
            )
        )
    return queue_entries, interventions


def _collect_pressure_signals(repo_root: Path) -> dict[str, list[dict[str, Any]]]:
    pressure_by_workspace: dict[str, list[dict[str, Any]]] = {}
    pattern = "*/operator/observability/*/live_summary.json"
    for live_summary_path in (repo_root / "docs" / "specs").glob(pattern):
        observability_root = live_summary_path.parent
        operator_dir = observability_root.parent.parent
        workspace_id = _workspace_id_for_operator_path(repo_root, operator_dir)
        summary = read_live_summary(observability_root)
        if summary is None:
            continue
        if not (
            summary.stall_signal.stalled
            or not summary.budget.justified
            or summary.budget.continuation_count > 0
            or summary.budget.remaining_loop_budget == 0
        ):
            continue
        pressure_by_workspace.setdefault(workspace_id, []).append(
            {
                "subject_key": summary.subject_key,
                "phase": summary.phase,
                "status_reason": summary.status_reason,
                "current_step_key": summary.current_step_key,
                "budget_key": summary.budget.budget_key,
                "remaining_steps": summary.budget.remaining_steps,
                "remaining_loop_budget": summary.budget.remaining_loop_budget,
                "continuation_count": summary.budget.continuation_count,
                "recent_token_growth": summary.budget.recent_token_growth,
                "justified": summary.budget.justified,
                "stalled": summary.stall_signal.stalled,
                "idle_seconds": summary.stall_signal.idle_seconds,
                "stall_reason": summary.stall_signal.reason,
                "repeated_steps": summary.stall_signal.repeated_steps,
                "updated_at": summary.updated_at,
            }
        )
    for signals in pressure_by_workspace.values():
        signals.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
    return pressure_by_workspace


def _build_resource_budgets(
    pressure_by_workspace: dict[str, list[dict[str, Any]]],
) -> list[ResourceBudget]:
    budgets: list[ResourceBudget] = []
    for workspace_id, signals in sorted(pressure_by_workspace.items()):
        for signal in signals:
            budget_key = str(signal.get("budget_key", "")).strip()
            if not budget_key:
                continue
            budget_state = "healthy"
            if (
                bool(signal.get("stalled"))
                or not bool(signal.get("justified", True))
                or int(signal.get("remaining_loop_budget", 0)) == 0
            ):
                budget_state = "saturated"
            elif int(signal.get("continuation_count", 0)) > 0:
                budget_state = "constrained"
            budgets.append(
                ResourceBudget(
                    budget_id=f"{workspace_id}:{budget_key}",
                    workspace_id=workspace_id,
                    subject_id=str(signal.get("subject_key", "")).strip() or workspace_id,
                    subject_kind="runtime_step",
                    budget_key=budget_key,
                    budget_state=budget_state,
                    remaining_steps=int(signal.get("remaining_steps", 0) or 0),
                    remaining_loop_budget=int(signal.get("remaining_loop_budget", 0) or 0),
                    continuation_count=int(signal.get("continuation_count", 0) or 0),
                    recent_token_growth=int(signal.get("recent_token_growth", 0) or 0),
                    justified=bool(signal.get("justified", False)),
                    recorded_at=str(signal.get("updated_at", "")).strip(),
                )
            )
    return budgets


def _build_pressure_signal_models(
    pressure_by_workspace: dict[str, list[dict[str, Any]]],
) -> list[PressureSignal]:
    models: list[PressureSignal] = []
    for workspace_id, signals in sorted(pressure_by_workspace.items()):
        for signal in signals:
            pressure_kind = "stall" if bool(signal.get("stalled")) else "budget"
            severity = "warning"
            if (
                not bool(signal.get("justified", True))
                or int(signal.get("remaining_loop_budget", 0)) == 0
            ):
                severity = "high"
            models.append(
                PressureSignal(
                    pressure_signal_id=(
                        f"{workspace_id}:{str(signal.get('subject_key', '')).strip() or 'signal'}"
                    ),
                    workspace_id=workspace_id,
                    subject_id=str(signal.get("subject_key", "")).strip() or workspace_id,
                    subject_kind="runtime_step",
                    budget_key=str(signal.get("budget_key", "")).strip(),
                    pressure_kind=pressure_kind,
                    severity=severity,
                    reason=(
                        str(signal.get("stall_reason", "")).strip()
                        or str(signal.get("status_reason", "")).strip()
                    ),
                    details=dict(signal),
                    recorded_at=str(signal.get("updated_at", "")).strip(),
                )
            )
    return models


def _build_execution_sessions(
    *,
    active_work: list[ActiveWork],
    statuses: list[tuple[str, RuntimeChainStatus]],
) -> list[tuple[str, ExecutionSession]]:
    sessions: list[tuple[str, ExecutionSession]] = []
    active_work_by_workspace = {item.workspace_id: item for item in active_work}
    for workspace_id, status in sorted(
        statuses,
        key=lambda item: (item[0], item[1].updated_at, item[1].active_span_id),
    ):
        active_item = active_work_by_workspace.get(workspace_id)
        agent_id = active_item.agent_id if active_item is not None else ""
        runtime_id = active_item.runtime_id if active_item is not None else _LOCAL_RUNTIME_ID
        sessions.append(
            (
                workspace_id,
                execution_session_from_runtime_chain_status(
                    status,
                    workspace_id=workspace_id,
                    agent_id=agent_id,
                    runtime_id=runtime_id,
                ),
            )
        )
    return sessions


def _execution_event_from_runtime_chain_event(
    *,
    workspace_id: str,
    execution_session_id: str,
    event: RuntimeChainEvent,
) -> ExecutionEvent:
    artifact_refs = [
        str(value).strip() for value in event.artifact_refs.values() if str(value).strip()
    ]
    return ExecutionEvent(
        event_id=f"{workspace_id}:{event.span_id}",
        workspace_id=workspace_id,
        execution_session_id=execution_session_id,
        event_type=event.phase.value,
        event_summary=event.status_reason or event.phase.value,
        event_source="runtime_chain",
        created_at=event.updated_at,
        artifact_refs=artifact_refs,
    )


def _build_execution_events(
    *,
    active_work: list[ActiveWork],
    statuses: list[tuple[str, Path, RuntimeChainStatus]],
) -> list[ExecutionEvent]:
    active_work_by_workspace = {item.workspace_id: item for item in active_work}
    events: list[ExecutionEvent] = []
    for workspace_id, chain_root, status in sorted(
        statuses,
        key=lambda item: (item[0], item[2].updated_at, str(item[1])),
    ):
        active_item = active_work_by_workspace.get(workspace_id)
        agent_id = active_item.agent_id if active_item is not None else ""
        runtime_id = active_item.runtime_id if active_item is not None else _LOCAL_RUNTIME_ID
        session = execution_session_from_runtime_chain_status(
            status,
            workspace_id=workspace_id,
            agent_id=agent_id,
            runtime_id=runtime_id,
        )
        for event in sorted(read_chain_events(chain_root), key=lambda item: item.updated_at):
            events.append(
                _execution_event_from_runtime_chain_event(
                    workspace_id=workspace_id,
                    execution_session_id=session.execution_session_id,
                    event=event,
                )
            )
    return events


def _latest_pressure_reason_for_workspace(
    workspace_id: str,
    pressure_by_workspace: dict[str, list[dict[str, Any]]],
) -> str:
    signals = pressure_by_workspace.get(workspace_id) or []
    if not signals:
        return ""
    return str(signals[0].get("status_reason", "")).strip()


def _required_budget_keys_for_workspace(
    workspace_id: str,
    pressure_by_workspace: dict[str, list[dict[str, Any]]],
) -> list[str]:
    return sorted(
        {
            str(signal.get("budget_key", "")).strip()
            for signal in pressure_by_workspace.get(workspace_id, [])
            if str(signal.get("budget_key", "")).strip()
        }
    )


def _build_admission_decisions(
    *,
    active_work: list[ActiveWork],
    execution_sessions: list[tuple[str, ExecutionSession]],
    queue_entries: list[QueueEntry],
    pressure_by_workspace: dict[str, list[dict[str, Any]]],
) -> list[AdmissionDecision]:
    active_work_by_workspace = {item.workspace_id: item for item in active_work}
    decisions: list[AdmissionDecision] = []
    for workspace_id, session in execution_sessions:
        active_item = active_work_by_workspace.get(workspace_id)
        subject_id = active_item.subject_id if active_item is not None else workspace_id
        subject_kind = active_item.subject_kind if active_item is not None else "workspace"
        decision = "admit"
        if session.health == "failed":
            decision = "reject"
        elif session.health == "degraded":
            decision = "degrade"
        required_budgets = _required_budget_keys_for_workspace(workspace_id, pressure_by_workspace)
        granted_budgets = required_budgets if decision in {"admit", "degrade"} else []
        decisions.append(
            AdmissionDecision(
                admission_decision_id=f"{workspace_id}:{session.execution_session_id}",
                workspace_id=workspace_id,
                subject_id=subject_id,
                subject_kind=subject_kind,
                decision=decision,
                required_budgets=required_budgets,
                granted_budgets=granted_budgets,
                queue_position=None,
                pressure_reason=_latest_pressure_reason_for_workspace(
                    workspace_id,
                    pressure_by_workspace,
                ),
                degrade_reason=session.status_reason if decision == "degrade" else "",
                recorded_at=session.last_event_at,
            )
        )
    for queue_entry in queue_entries:
        decisions.append(
            AdmissionDecision(
                admission_decision_id=queue_entry.queue_entry_id,
                workspace_id=queue_entry.workspace_id,
                subject_id=queue_entry.subject_id,
                subject_kind="round" if ":round-" in queue_entry.subject_id else "mission",
                decision="defer",
                required_budgets=[queue_entry.queue_name],
                granted_budgets=[],
                queue_position=queue_entry.position,
                pressure_reason=_latest_pressure_reason_for_workspace(
                    queue_entry.workspace_id,
                    pressure_by_workspace,
                ),
                degrade_reason="",
                recorded_at=queue_entry.claimed_at,
            )
        )
    return decisions


def _runtime_from_active_work(
    active_work: list[ActiveWork],
    *,
    queue_entries: list[QueueEntry],
    interventions: list[OperatorIntervention],
    pressure_by_workspace: dict[str, list[dict[str, Any]]],
    admission_decisions: list[AdmissionDecision],
) -> list[Runtime]:
    if not active_work:
        return []
    degradation_flags = sorted(
        {
            item.status_reason
            for item in active_work
            if item.health in {"degraded", "failed"} and item.status_reason
        }
    )
    if any(item.health == "failed" for item in active_work):
        health = "failed"
    elif any(item.health == "degraded" for item in active_work):
        health = "degraded"
    else:
        health = "healthy"
    latest_heartbeat = max((item.updated_at for item in active_work), default="")
    pressure_signals = [signal for signals in pressure_by_workspace.values() for signal in signals]
    budget_keys = sorted(
        {
            str(signal.get("budget_key", "")).strip()
            for signal in pressure_signals
            if str(signal.get("budget_key", "")).strip()
        }
    )
    stalled_workspace_ids = sorted(
        {
            workspace_id
            for workspace_id, signals in pressure_by_workspace.items()
            if any(bool(signal.get("stalled")) for signal in signals)
        }
    )
    admission_decision_counts = {
        "admit": sum(1 for item in admission_decisions if item.decision == "admit"),
        "defer": sum(1 for item in admission_decisions if item.decision == "defer"),
        "reject": sum(1 for item in admission_decisions if item.decision == "reject"),
        "degrade": sum(1 for item in admission_decisions if item.decision == "degrade"),
    }
    return [
        Runtime(
            runtime_id=_LOCAL_RUNTIME_ID,
            runtime_kind="local",
            mode="interactive",
            health=health,
            heartbeat_at=latest_heartbeat,
            usage_summary={
                "active_sessions": len(active_work),
                "queued_sessions": len(queue_entries),
                "open_interventions": sum(1 for item in interventions if item.outcome == "open"),
                "pressure_signal_count": len(pressure_signals),
                "admission_decision_counts": admission_decision_counts,
            },
            activity_summary={
                "active_workspace_ids": sorted({item.workspace_id for item in active_work}),
                "active_agent_ids": sorted({item.agent_id for item in active_work}),
                "stalled_workspace_ids": stalled_workspace_ids,
                "budget_keys": budget_keys,
                "pressure_signals": pressure_signals,
            },
            degradation_flags=sorted(
                set(
                    degradation_flags
                    + [
                        str(signal.get("status_reason", "")).strip()
                        for signal in pressure_signals
                        if str(signal.get("status_reason", "")).strip()
                    ]
                )
            ),
        )
    ]


def build_execution_substrate_snapshot(repo_root: Path) -> dict[str, Any]:
    active_work_models: list[ActiveWork] = []
    agent_models: dict[str, Agent] = {}
    status_models: list[tuple[str, RuntimeChainStatus]] = []
    chain_roots: list[tuple[str, Path, RuntimeChainStatus]] = []
    for chain_root in _discover_chain_roots(Path(repo_root)):
        try:
            status = read_chain_status(chain_root)
        except Exception:
            status = None
        if status is None:
            continue
        workspace_id = _workspace_id_for_chain_root(Path(repo_root), chain_root, status)
        status_models.append((workspace_id, status))
        chain_roots.append((workspace_id, chain_root, status))
        work = _active_work_from_status(workspace_id=workspace_id, status=status)
        agent = _agent_from_status(workspace_id=workspace_id, status=status)
        active_work_models.append(work)
        existing = agent_models.get(agent.agent_id)
        if existing is None or agent.last_active_at >= existing.last_active_at:
            agent_models[agent.agent_id] = agent

    queue_models, intervention_models = _collect_queue_and_interventions(Path(repo_root))
    pressure_by_workspace = _collect_pressure_signals(Path(repo_root))
    execution_session_records = _build_execution_sessions(
        active_work=active_work_models,
        statuses=status_models,
    )
    execution_event_models = _build_execution_events(
        active_work=active_work_models,
        statuses=chain_roots,
    )
    resource_budget_models = _build_resource_budgets(pressure_by_workspace)
    pressure_signal_models = _build_pressure_signal_models(pressure_by_workspace)
    admission_decision_models = _build_admission_decisions(
        active_work=active_work_models,
        execution_sessions=execution_session_records,
        queue_entries=queue_models,
        pressure_by_workspace=pressure_by_workspace,
    )
    runtime_models = _runtime_from_active_work(
        active_work_models,
        queue_entries=queue_models,
        interventions=intervention_models,
        pressure_by_workspace=pressure_by_workspace,
        admission_decisions=admission_decision_models,
    )
    active_work = [item.to_dict() for item in active_work_models]
    queue = [item.to_dict() for item in queue_models]
    interventions = [item.to_dict() for item in intervention_models]
    execution_sessions = [item.to_dict() for _workspace_id, item in execution_session_records]
    execution_events = [item.to_dict() for item in execution_event_models]
    resource_budgets = [item.to_dict() for item in resource_budget_models]
    pressure_signals = [item.to_dict() for item in pressure_signal_models]
    admission_decisions = [item.to_dict() for item in admission_decision_models]
    agents = [
        item.to_dict() for item in sorted(agent_models.values(), key=lambda item: item.agent_id)
    ]
    runtimes = [item.to_dict() for item in runtime_models]
    admission_decision_counts = {
        "admit": sum(1 for item in admission_decision_models if item.decision == "admit"),
        "defer": sum(1 for item in admission_decision_models if item.decision == "defer"),
        "reject": sum(1 for item in admission_decision_models if item.decision == "reject"),
        "degrade": sum(1 for item in admission_decision_models if item.decision == "degrade"),
    }
    pressure_signal_count = sum(len(signals) for signals in pressure_by_workspace.values())
    intervention_needed_count = len(
        {item.workspace_id for item in active_work_models if item.health in {"degraded", "failed"}}
        | {item.workspace_id for item in intervention_models if item.outcome == "open"}
    )
    summary = {
        "active_work_count": len(active_work),
        "agent_count": len(agents),
        "runtime_count": len(runtimes),
        "running_count": sum(1 for item in active_work_models if item.health == "active"),
        "queued_count": len(queue_models),
        "degraded_count": sum(1 for item in active_work_models if item.health == "degraded"),
        "intervention_needed_count": intervention_needed_count,
        "open_intervention_count": sum(1 for item in intervention_models if item.outcome == "open"),
        "pressure_signal_count": pressure_signal_count,
        "admission_decision_counts": admission_decision_counts,
    }
    return {
        "summary": summary,
        "active_work": active_work,
        "agents": agents,
        "runtimes": runtimes,
        "queue": queue,
        "interventions": interventions,
        "execution_sessions": execution_sessions,
        "execution_events": execution_events,
        "resource_budgets": resource_budgets,
        "pressure_signals": pressure_signals,
        "admission_decisions": admission_decisions,
    }


__all__ = ["build_execution_substrate_snapshot"]
