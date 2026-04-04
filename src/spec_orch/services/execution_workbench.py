from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from spec_orch.services.execution_substrate import build_execution_substrate_snapshot


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _latest_browser_evidence(mission_root: Path) -> tuple[Path, dict[str, Any]] | None:
    candidates: list[tuple[Path, dict[str, Any]]] = []
    for round_dir in sorted((mission_root / "rounds").glob("round-*")):
        for file_name in ("browser_evidence.json", "exploratory_browser_evidence.json"):
            evidence_path = round_dir / file_name
            if not evidence_path.exists():
                continue
            payload = _load_json(evidence_path)
            if payload is not None:
                candidates.append((evidence_path, payload))
    if not candidates:
        return None
    return candidates[-1]


def _flatten_recent_interactions(
    interactions: dict[str, Any],
    *,
    limit: int = 6,
) -> list[dict[str, str]]:
    recent: list[dict[str, str]] = []
    for route, steps in interactions.items():
        if not isinstance(route, str) or not isinstance(steps, list):
            continue
        for step in steps:
            if not isinstance(step, dict):
                continue
            recent.append(
                {
                    "route": route,
                    "action": str(step.get("action", "")).strip(),
                    "description": str(step.get("description", "")).strip(),
                    "status": str(step.get("status", "")).strip(),
                }
            )
    return recent[:limit]


def _build_browser_panel(mission_root: Path, mission_id: str) -> dict[str, Any]:
    result = _latest_browser_evidence(mission_root)
    if result is None:
        return {
            "status": "missing",
            "mission_id": mission_id,
            "tested_route_count": 0,
            "interaction_count": 0,
            "screenshot_count": 0,
            "console_error_count": 0,
            "page_error_count": 0,
            "current_task_summary": "No browser evidence recorded yet.",
            "tested_routes": [],
            "recent_interactions": [],
            "artifact_paths": {},
        }
    evidence_path, payload = result
    tested_routes = [item for item in payload.get("tested_routes", []) if isinstance(item, str)]
    interactions = payload.get("interactions", {})
    interaction_count = (
        sum(len(steps) for steps in interactions.values() if isinstance(steps, list))
        if isinstance(interactions, dict)
        else 0
    )
    screenshots = payload.get("screenshots", {})
    console_errors = payload.get("console_errors", [])
    page_errors = payload.get("page_errors", [])
    round_dir = evidence_path.parent
    round_id = round_dir.name
    normalized_interactions = interactions if isinstance(interactions, dict) else {}
    return {
        "status": "available",
        "mission_id": mission_id,
        "round_id": round_id,
        "evidence_path": str(evidence_path),
        "tested_route_count": len(tested_routes),
        "interaction_count": interaction_count,
        "screenshot_count": len(screenshots) if isinstance(screenshots, dict) else 0,
        "console_error_count": len(console_errors) if isinstance(console_errors, list) else 0,
        "page_error_count": len(page_errors) if isinstance(page_errors, list) else 0,
        "current_task_summary": (
            f"{len(tested_routes)} routes replayed across {interaction_count} interactions"
        ),
        "tested_routes": tested_routes,
        "recent_interactions": _flatten_recent_interactions(normalized_interactions),
        "artifact_paths": payload.get("artifact_paths", {}),
        "review_route": f"/?mission={mission_id}&mode=missions&tab=execution",
    }


def _tail_jsonl_event(path: Path) -> dict[str, Any] | None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _tail_activity(path: Path, *, limit: int = 3) -> list[str]:
    try:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError:
        return []
    return lines[-limit:]


def _budget_scope_counts(items: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for item in items:
        runtime_role = str(item.get("subject_kind", "")).strip() or "unknown"
        budget_state = str(item.get("budget_state", "")).strip() or "unknown"
        role_counts = counts.setdefault(
            runtime_role,
            {"healthy": 0, "constrained": 0, "saturated": 0},
        )
        role_counts.setdefault(budget_state, 0)
        role_counts[budget_state] += 1
    return counts


def _pressure_by_role(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        runtime_role = str(item.get("subject_kind", "")).strip() or "unknown"
        counts[runtime_role] = counts.get(runtime_role, 0) + 1
    return counts


def _build_terminal_panel(mission_root: Path, mission_id: str) -> dict[str, Any]:
    sessions: list[dict[str, Any]] = []
    for worker_dir in sorted((mission_root / "workers").glob("*")):
        if not worker_dir.is_dir():
            continue
        report_path = worker_dir / "builder_report.json"
        report = _load_json(report_path)
        if report is None:
            continue
        telemetry_dir = worker_dir / "telemetry"
        events_path = telemetry_dir / "events.jsonl"
        activity_log_path = telemetry_dir / "activity.log"
        last_event = _tail_jsonl_event(events_path)
        sessions.append(
            {
                "packet_id": worker_dir.name,
                "session_name": str(report.get("session_name", "")).strip(),
                "terminal_reason": str(report.get("terminal_reason", "")).strip(),
                "session_health": str(report.get("session_health", "")).strip(),
                "exit_code": report.get("exit_code"),
                "event_count": int(report.get("event_count", 0) or 0),
                "commands_completed": int(report.get("commands_completed", 0) or 0),
                "recent_activity": _tail_activity(activity_log_path),
                "last_event_type": (
                    str(last_event.get("event_type", "")).strip() if last_event else ""
                ),
                "last_event_message": (
                    str(last_event.get("message", "")).strip() if last_event else ""
                ),
                "report_path": str(report_path),
                "activity_log_path": str(activity_log_path),
                "events_path": str(events_path),
                "chain_id": str(report.get("chain_id", "")).strip(),
                "span_id": str(report.get("span_id", "")).strip(),
            }
        )
    if not sessions:
        return {
            "status": "missing",
            "mission_id": mission_id,
            "session_count": 0,
            "failed_session_count": 0,
            "current_task_summary": "No terminal sessions recorded yet.",
            "sessions": [],
        }
    failed_session_count = sum(
        1
        for item in sessions
        if str(item.get("session_health", "")).strip() not in {"healthy", "active"}
        or str(item.get("terminal_reason", "")).strip() not in {"process_exit_success", ""}
    )
    return {
        "status": "available",
        "mission_id": mission_id,
        "session_count": len(sessions),
        "failed_session_count": failed_session_count,
        "current_task_summary": f"{len(sessions)} terminal session(s) recorded",
        "sessions": sessions,
        "review_route": f"/?mission={mission_id}&mode=missions&tab=execution",
    }


def _execution_surface_summaries(
    repo_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    browser_surfaces: list[dict[str, Any]] = []
    terminal_surfaces: list[dict[str, Any]] = []
    for mission_root in sorted((Path(repo_root) / "docs" / "specs").glob("*")):
        if not mission_root.is_dir():
            continue
        mission_id = mission_root.name
        browser_panel = _build_browser_panel(mission_root, mission_id)
        if browser_panel["status"] == "available":
            browser_surfaces.append(
                {
                    "workspace_id": mission_id,
                    "round_id": browser_panel.get("round_id", ""),
                    "tested_route_count": browser_panel.get("tested_route_count", 0),
                    "interaction_count": browser_panel.get("interaction_count", 0),
                    "error_count": int(browser_panel.get("console_error_count", 0) or 0)
                    + int(browser_panel.get("page_error_count", 0) or 0),
                    "current_task_summary": browser_panel.get("current_task_summary", ""),
                    "review_route": browser_panel.get("review_route", ""),
                }
            )
        terminal_panel = _build_terminal_panel(mission_root, mission_id)
        if terminal_panel["status"] == "available":
            terminal_surfaces.append(
                {
                    "workspace_id": mission_id,
                    "session_count": terminal_panel.get("session_count", 0),
                    "failed_session_count": terminal_panel.get("failed_session_count", 0),
                    "current_task_summary": terminal_panel.get("current_task_summary", ""),
                    "review_route": terminal_panel.get("review_route", ""),
                }
            )
    return browser_surfaces, terminal_surfaces


def build_execution_workbench(repo_root: Path) -> dict[str, Any]:
    snapshot = build_execution_substrate_snapshot(Path(repo_root))
    browser_surfaces, terminal_surfaces = _execution_surface_summaries(Path(repo_root))
    summary = snapshot.get("summary", {})
    runtimes = [item for item in snapshot.get("runtimes", []) if isinstance(item, dict)]
    pressure_signals = [
        item for item in snapshot.get("pressure_signals", []) if isinstance(item, dict)
    ]

    return {
        "summary": {
            "running_count": int(summary.get("running_count", 0) or 0),
            "queued_count": int(summary.get("queued_count", 0) or 0),
            "stalled_count": sum(
                1
                for item in pressure_signals
                if str(item.get("pressure_kind", "")).strip() == "stall"
            ),
            "degraded_runtime_count": sum(
                1
                for item in runtimes
                if str(item.get("health", "")).strip() in {"degraded", "failed"}
            ),
            "intervention_needed_count": int(summary.get("intervention_needed_count", 0) or 0),
            "budget_scope_counts": summary.get("budget_scope_counts", {}),
            "pressure_by_role": summary.get("pressure_by_role", {}),
        },
        "active_work": list(snapshot.get("active_work", [])),
        "agents": list(snapshot.get("agents", [])),
        "runtimes": runtimes,
        "queue": list(snapshot.get("queue", [])),
        "interventions": list(snapshot.get("interventions", [])),
        "execution_sessions": list(snapshot.get("execution_sessions", [])),
        "event_trail": list(snapshot.get("execution_events", [])),
        "pressure_signals": pressure_signals,
        "admission_decisions": list(snapshot.get("admission_decisions", [])),
        "browser_surfaces": browser_surfaces,
        "terminal_surfaces": terminal_surfaces,
        "review_route": "/?mode=execution",
    }


def build_mission_execution_workbench(
    repo_root: Path,
    mission_id: str,
    available_actions: list[str],
) -> dict[str, Any]:
    snapshot = build_execution_substrate_snapshot(Path(repo_root))
    mission_root = Path(repo_root) / "docs" / "specs" / mission_id

    def _filter(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            item
            for item in items
            if isinstance(item, dict) and str(item.get("workspace_id", "")) == mission_id
        ]

    active_work = _filter(snapshot.get("active_work", []))
    queue = _filter(snapshot.get("queue", []))
    interventions = _filter(snapshot.get("interventions", []))
    execution_sessions = _filter(snapshot.get("execution_sessions", []))
    execution_events = _filter(snapshot.get("execution_events", []))
    resource_budgets = _filter(snapshot.get("resource_budgets", []))
    pressure_signals = _filter(snapshot.get("pressure_signals", []))
    admission_decisions = _filter(snapshot.get("admission_decisions", []))
    budget_scope_counts = _budget_scope_counts(resource_budgets)
    pressure_by_role = _pressure_by_role(pressure_signals)

    agent_ids = {
        str(item.get("agent_id", ""))
        for item in active_work + execution_sessions
        if isinstance(item, dict) and str(item.get("agent_id", "")).strip()
    }
    runtime_ids = {
        str(item.get("runtime_id", ""))
        for item in active_work + execution_sessions
        if isinstance(item, dict) and str(item.get("runtime_id", "")).strip()
    }
    agents = [
        item
        for item in snapshot.get("agents", [])
        if isinstance(item, dict) and str(item.get("agent_id", "")) in agent_ids
    ]
    runtimes = [
        item
        for item in snapshot.get("runtimes", [])
        if isinstance(item, dict) and str(item.get("runtime_id", "")) in runtime_ids
    ]

    current_active = active_work[0] if active_work else {}
    last_event = execution_events[-1] if execution_events else {}
    posture_reasons = sorted(
        {
            (
                str(item.get("pressure_reason", "")).strip()
                or str(item.get("degrade_reason", "")).strip()
            )
            for item in admission_decisions
            if (
                str(item.get("pressure_reason", "")).strip()
                or str(item.get("degrade_reason", "")).strip()
            )
        }
    )

    return {
        "mission_id": mission_id,
        "overview": {
            "active_work_count": len(active_work),
            "queued_count": len(queue),
            "open_intervention_count": len(interventions),
            "runtime_count": len(runtimes),
            "agent_count": len(agents),
            "pressure_signal_count": len(pressure_signals),
            "admission_decision_count": len(admission_decisions),
            "budget_scope_counts": budget_scope_counts,
            "pressure_by_role": pressure_by_role,
            "posture_reasons": posture_reasons,
            "current_phase": str(current_active.get("phase", "")),
            "current_health": str(current_active.get("health", "")),
            "last_event_summary": str(last_event.get("event_summary", "")),
        },
        "active_work": active_work,
        "event_trail": execution_events,
        "queue": queue,
        "interventions": interventions,
        "resource_budgets": resource_budgets,
        "pressure_signals": pressure_signals,
        "admission_decisions": admission_decisions,
        "runtime": runtimes[0] if runtimes else None,
        "agents": agents,
        "execution_sessions": execution_sessions,
        "available_actions": list(dict.fromkeys(available_actions)),
        "browser_panel": _build_browser_panel(mission_root, mission_id),
        "terminal_panel": _build_terminal_panel(mission_root, mission_id),
        "review_route": f"/?mission={mission_id}&mode=missions&tab=execution",
    }


__all__ = ["build_execution_workbench", "build_mission_execution_workbench"]
