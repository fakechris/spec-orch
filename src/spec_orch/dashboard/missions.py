from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from spec_orch.runtime_chain.store import read_chain_events, read_chain_status
from spec_orch.runtime_core.readers import read_round_supervision_cycle
from spec_orch.services.execution_workbench import (
    build_execution_workbench,
    build_mission_execution_workbench,
)
from spec_orch.services.judgment_workbench import (
    build_judgment_workbench,
    build_mission_judgment_workbench,
)
from spec_orch.services.learning_workbench import (
    build_learning_workbench,
    build_mission_learning_workbench,
)
from spec_orch.services.mission_service import MissionService
from spec_orch.services.operator_semantics import workspace_from_mission_runtime
from spec_orch.services.pipeline_checker import check_pipeline
from spec_orch.services.promotion_service import load_plan

from .approvals import _gather_latest_approval_request, _load_approval_history

logger = logging.getLogger(__name__)


def _get_lifecycle_manager(repo_root: Path):
    try:
        from spec_orch.services.lifecycle_manager import MissionLifecycleManager

        return MissionLifecycleManager(repo_root)
    except ImportError:
        return None


def _derive_approval_state(
    approval_request: dict[str, Any] | None,
    approval_history: list[dict[str, Any]],
) -> dict[str, str] | None:
    if approval_request is None:
        return None

    latest_action = approval_history[0] if approval_history else None
    if latest_action is None:
        return {
            "status": "awaiting_human",
            "summary": "Awaiting operator decision",
        }

    status = str(latest_action.get("status") or "")
    effect = str(latest_action.get("effect") or "")
    if status == "failed":
        return {
            "status": "failed",
            "summary": "Latest operator action failed",
        }
    if effect == "approval_granted":
        return {
            "status": "approval_granted",
            "summary": "Operator approved this round",
        }
    if effect == "revision_requested":
        return {
            "status": "revision_requested",
            "summary": "Operator requested revision",
        }
    if effect == "followup_requested":
        return {
            "status": "followup_requested",
            "summary": "Operator requested follow-up",
        }
    if status == "not_applied":
        return {
            "status": "not_applied",
            "summary": "Latest operator action was recorded only",
        }
    if status == "applied":
        return {
            "status": "applied",
            "summary": "Latest operator action was applied",
        }
    return {
        "status": status or "awaiting_human",
        "summary": "Awaiting operator decision",
    }


def _mission_phase_rank(phase: str) -> int:
    normalized = str(phase or "").lower()
    if normalized == "executing":
        return 0
    if normalized in {"failed", "all_done", "retrospecting", "evolving"}:
        return 1
    if normalized in {"approved", "planning", "planned", "promoting"}:
        return 2
    if normalized == "completed":
        return 3
    return 4


def _mission_evidence_counts(repo_root: Path, specs_dir: Path) -> dict[str, int]:
    rounds_dir = specs_dir / "rounds"
    operator_dir = specs_dir / "operator"
    if not rounds_dir.exists() and not operator_dir.exists():
        return {
            "round_count": 0,
            "visual_round_count": 0,
            "approval_action_count": 0,
        }

    round_count = 0
    visual_round_count = 0
    if rounds_dir.exists():
        for round_dir in rounds_dir.glob("round-*"):
            if not round_dir.is_dir():
                continue
            if (round_dir / "round_summary.json").exists():
                round_count += 1
            if (round_dir / "visual_evaluation.json").exists():
                visual_round_count += 1

    approval_action_count = len(_load_approval_history(repo_root, specs_dir.name))

    return {
        "round_count": round_count,
        "visual_round_count": visual_round_count,
        "approval_action_count": approval_action_count,
    }


def _mission_sort_phase_rank(mission: dict[str, Any]) -> int:
    value = mission.get("sort_phase_rank", 9)
    return value if isinstance(value, int) else 9


def _mission_sort_timestamp(mission: dict[str, Any]) -> str:
    value = mission.get("sort_timestamp", "")
    return value if isinstance(value, str) else ""


def _mission_available_actions(
    mission_status: str,
    lifecycle: dict[str, Any] | None,
) -> list[str]:
    actions = ["inject_guidance"]
    if mission_status in {"approved", "drafting"}:
        actions.append("approve")
    if mission_status in {"failed"}:
        actions.extend(["retry", "rerun"])
    if mission_status in {"executing", "planned", "promoting"}:
        actions.extend(["resume", "stop", "rerun"])

    if lifecycle and lifecycle.get("round_orchestrator_state", {}).get("paused"):
        actions.append("resume")
    return sorted(set(actions))


def _gather_mission_execution_workbench(repo_root: Path, mission_id: str) -> dict[str, Any] | None:
    svc = MissionService(repo_root=repo_root)
    try:
        mission = svc.get_mission(mission_id)
    except FileNotFoundError:
        return None
    lifecycle = _gather_lifecycle_states(repo_root).get(mission_id)
    actions = _mission_available_actions(mission.status.value, lifecycle)
    return build_mission_execution_workbench(repo_root, mission_id, actions)


def _gather_execution_workbench(repo_root: Path) -> dict[str, Any]:
    return build_execution_workbench(repo_root)


def _gather_judgment_workbench(repo_root: Path) -> dict[str, Any]:
    return build_judgment_workbench(repo_root)


def _gather_mission_judgment_workbench(repo_root: Path, mission_id: str) -> dict[str, Any]:
    return build_mission_judgment_workbench(repo_root, mission_id)


def _gather_learning_workbench(repo_root: Path) -> dict[str, Any]:
    return build_learning_workbench(repo_root)


def _gather_mission_learning_workbench(repo_root: Path, mission_id: str) -> dict[str, Any]:
    return build_mission_learning_workbench(repo_root, mission_id)


def _gather_mission_runtime_chain(
    repo_root: Path,
    mission_id: str,
    *,
    event_limit: int = 20,
) -> dict[str, Any]:
    chain_root = repo_root / "docs" / "specs" / mission_id / "operator" / "runtime_chain"
    status_error = False
    try:
        current_status = read_chain_status(chain_root)
    except Exception:
        current_status = None
        status_error = True
    try:
        recent_events = read_chain_events(chain_root)[-event_limit:]
    except Exception:
        recent_events = []
        status_error = True
    if status_error:
        status = "corrupt"
    elif current_status is not None or recent_events:
        status = "present"
    else:
        status = "missing"
    return {
        "mission_id": mission_id,
        "chain_root": str(chain_root.relative_to(repo_root)),
        "status": status,
        "current_status": current_status.to_dict() if current_status is not None else None,
        "recent_events": [event.to_dict() for event in recent_events],
    }


def _gather_missions(repo_root: Path) -> list[dict[str, Any]]:
    svc = MissionService(repo_root=repo_root)
    missions = svc.list_missions()
    lifecycle_states = _gather_lifecycle_states(repo_root)
    results = []
    for mission in missions:
        specs_dir = repo_root / "docs/specs" / mission.mission_id
        plan_path = repo_root / "docs/specs" / mission.mission_id / "plan.json"
        plan_info: dict[str, Any] | None = None
        if plan_path.exists():
            plan = load_plan(plan_path)
            plan_info = {
                "plan_id": plan.plan_id,
                "status": plan.status.value,
                "wave_count": len(plan.waves),
                "packet_count": sum(len(wave.work_packets) for wave in plan.waves),
                "waves": [
                    {
                        "wave_number": wave.wave_number,
                        "description": wave.description,
                        "packets": [
                            {
                                "packet_id": packet.packet_id,
                                "title": packet.title,
                                "run_class": packet.run_class,
                                "linear_issue_id": packet.linear_issue_id,
                                "depends_on": packet.depends_on,
                            }
                            for packet in wave.work_packets
                        ],
                    }
                    for wave in plan.waves
                ],
            }

        stages = check_pipeline(mission.mission_id, repo_root)
        pipeline = [
            {
                "key": stage.key,
                "label": stage.label,
                "status": stage.status,
                "hint": stage.command_hint,
            }
            for stage in stages
        ]
        lifecycle = lifecycle_states.get(mission.mission_id, {})
        phase = str(lifecycle.get("phase") or mission.status.value)
        sort_timestamp = (
            str(lifecycle.get("updated_at") or "")
            or str(mission.completed_at or "")
            or str(mission.approved_at or "")
            or str(mission.created_at or "")
        )
        evidence = _mission_evidence_counts(repo_root, specs_dir)

        results.append(
            {
                "mission_id": mission.mission_id,
                "title": mission.title,
                "status": mission.status.value,
                "created_at": mission.created_at,
                "approved_at": mission.approved_at,
                "completed_at": mission.completed_at,
                "plan": plan_info,
                "pipeline": pipeline,
                "pipeline_done": sum(1 for stage in stages if stage.status == "done"),
                "pipeline_total": len(stages),
                "evidence": evidence,
                "sort_phase_rank": _mission_phase_rank(phase),
                "sort_timestamp": sort_timestamp,
            }
        )
    results.sort(key=_mission_sort_timestamp, reverse=True)
    results.sort(key=_mission_sort_phase_rank)
    return results


def _gather_inbox(repo_root: Path) -> dict[str, Any]:
    from .surfaces import _gather_mission_costs

    missions = _gather_missions(repo_root)
    lifecycle_states = _gather_lifecycle_states(repo_root)
    items: list[dict[str, Any]] = []

    for mission in missions:
        mission_id = mission["mission_id"]
        lifecycle = lifecycle_states.get(mission_id, {})
        round_state = lifecycle.get("round_orchestrator_state", {})
        approval_request = _gather_latest_approval_request(repo_root, mission_id)
        approval_history = _load_approval_history(repo_root, mission_id)

        if approval_request is not None:
            items.append(
                {
                    "mission_id": mission_id,
                    "title": mission["title"],
                    "kind": "approval",
                    "phase": lifecycle.get("phase", mission["status"]),
                    "summary": approval_request["summary"],
                    "updated_at": lifecycle.get("updated_at") or approval_request["timestamp"],
                    "current_round": lifecycle.get("current_round", approval_request["round_id"]),
                    "blocking_question": approval_request["blocking_question"],
                    "decision_action": approval_request["decision_action"],
                    "latest_operator_action": (approval_history[0] if approval_history else None),
                    "approval_request": approval_request,
                    "approval_state": _derive_approval_state(
                        approval_request,
                        approval_history,
                    ),
                }
            )
            continue

        if round_state.get("paused"):
            blocking_questions = round_state.get("blocking_questions", [])
            items.append(
                {
                    "mission_id": mission_id,
                    "title": mission["title"],
                    "kind": "paused",
                    "phase": lifecycle.get("phase", mission["status"]),
                    "summary": (
                        blocking_questions[0] if blocking_questions else "Paused for human input."
                    ),
                    "updated_at": lifecycle.get("updated_at"),
                    "current_round": lifecycle.get("current_round", 0),
                }
            )
            continue

        if lifecycle.get("phase") == "failed":
            items.append(
                {
                    "mission_id": mission_id,
                    "title": mission["title"],
                    "kind": "failed",
                    "phase": lifecycle.get("phase", mission["status"]),
                    "summary": lifecycle.get("error") or "Mission execution failed.",
                    "updated_at": lifecycle.get("updated_at"),
                    "current_round": lifecycle.get("current_round", 0),
                }
            )
            continue

        costs = _gather_mission_costs(repo_root, mission_id)
        budget_status = costs.get("summary", {}).get("budget_status")
        incidents = costs.get("incidents", [])
        if budget_status in {"warning", "critical"} and incidents:
            items.append(
                {
                    "mission_id": mission_id,
                    "title": mission["title"],
                    "kind": "budget",
                    "phase": lifecycle.get("phase", mission["status"]),
                    "summary": incidents[0].get("message", "Mission budget threshold reached."),
                    "updated_at": lifecycle.get("updated_at"),
                    "current_round": lifecycle.get("current_round", 0),
                    "budget_status": budget_status,
                    "cost_usd": costs.get("summary", {}).get("cost_usd", 0.0),
                    "operator_guidance": incidents[0].get("operator_guidance"),
                    "review_route": f"/?mission={mission_id}&mode=missions&tab=costs",
                }
            )

    items.sort(
        key=lambda item: (
            {"approval": 0, "budget": 1, "paused": 2, "failed": 3}.get(item["kind"], 9),
            item.get("updated_at") or "",
        )
    )

    return {
        "counts": {
            "approvals": sum(1 for item in items if item["kind"] == "approval"),
            "budgets": sum(1 for item in items if item["kind"] == "budget"),
            "paused": sum(1 for item in items if item["kind"] == "paused"),
            "failed": sum(1 for item in items if item["kind"] == "failed"),
            "attention": len(items),
        },
        "items": items,
    }


def _gather_mission_detail(repo_root: Path, mission_id: str) -> dict[str, Any] | None:
    svc = MissionService(repo_root=repo_root)
    try:
        mission = svc.get_mission(mission_id)
    except FileNotFoundError:
        return None

    plan_path = repo_root / "docs/specs" / mission_id / "plan.json"
    plan = load_plan(plan_path) if plan_path.exists() else None
    lifecycle = _gather_lifecycle_states(repo_root).get(mission_id)
    approval_request = _gather_latest_approval_request(repo_root, mission_id)
    approval_history = _load_approval_history(repo_root, mission_id)
    approval_state = _derive_approval_state(approval_request, approval_history)
    from .surfaces import (
        _gather_mission_acceptance_review,
        _gather_mission_costs,
        _gather_mission_visual_qa,
    )

    visual_qa = _gather_mission_visual_qa(repo_root, mission_id)
    acceptance_review = _gather_mission_acceptance_review(repo_root, mission_id)
    judgment_workbench = build_mission_judgment_workbench(repo_root, mission_id)
    learning_workbench = build_mission_learning_workbench(repo_root, mission_id)
    costs = _gather_mission_costs(repo_root, mission_id)
    runtime_chain = _gather_mission_runtime_chain(repo_root, mission_id)
    chain_root = repo_root / "docs" / "specs" / mission_id / "operator" / "runtime_chain"
    try:
        runtime_status = read_chain_status(chain_root)
    except Exception:
        runtime_status = None
    latest_shared_judgment = None
    latest_review = acceptance_review.get("latest_review")
    if isinstance(latest_review, dict):
        shared_judgments = latest_review.get("shared_judgments")
        if isinstance(shared_judgments, list) and shared_judgments:
            first = shared_judgments[0]
            if isinstance(first, dict):
                latest_shared_judgment = first
    workspace = workspace_from_mission_runtime(
        mission_id=mission_id,
        mission_title=mission.title,
        runtime_status=runtime_status,
        latest_judgment=latest_shared_judgment,
    )

    rounds_dir = repo_root / "docs/specs" / mission_id / "rounds"
    round_summaries: list[dict[str, Any]] = []
    current_round = 0
    if rounds_dir.exists():
        for round_dir in sorted(rounds_dir.glob("round-*")):
            normalized = read_round_supervision_cycle(round_dir)
            if normalized is not None:
                summary_payload = normalized.get("summary", {})
                if not isinstance(summary_payload, dict):
                    summary_payload = {}
                round_id = summary_payload.get("round_id")
                if not isinstance(round_id, int):
                    try:
                        round_id = int(round_dir.name.split("-")[-1])
                    except (TypeError, ValueError, IndexError):
                        round_id = 0
                current_round = max(current_round, round_id)
                review_artifact = normalized.get("artifacts", {}).get("review_report")
                visual_artifact = normalized.get("artifacts", {}).get("visual_report")
                payload = dict(summary_payload)
                payload["paths"] = {
                    "round_dir": str(round_dir.relative_to(repo_root)),
                    "review_memo": (
                        str(Path(review_artifact.path).relative_to(repo_root))
                        if review_artifact is not None
                        else None
                    ),
                    "visual_evaluation": (
                        str(Path(visual_artifact.path).relative_to(repo_root))
                        if visual_artifact is not None
                        else None
                    ),
                }
                round_summaries.append(payload)
                continue

            summary_path = round_dir / "round_summary.json"
            if not summary_path.exists():
                continue
            try:
                summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError):
                logger.warning("Skipping malformed round summary: %s", summary_path)
                continue
            if not isinstance(summary_payload, dict):
                logger.warning("Skipping non-object round summary: %s", summary_path)
                continue
            round_id = summary_payload.get("round_id")
            if not isinstance(round_id, int):
                try:
                    round_id = int(round_dir.name.split("-")[-1])
                except (TypeError, ValueError, IndexError):
                    round_id = 0
            current_round = max(current_round, round_id)
            review_path = round_dir / "supervisor_review.md"
            visual_path = round_dir / "visual_evaluation.json"
            payload = dict(summary_payload)
            payload["paths"] = {
                "round_dir": str(round_dir.relative_to(repo_root)),
                "review_memo": (
                    str(review_path.relative_to(repo_root)) if review_path.exists() else None
                ),
                "visual_evaluation": (
                    str(visual_path.relative_to(repo_root)) if visual_path.exists() else None
                ),
            }
            round_summaries.append(payload)

    packets: list[dict[str, Any]] = []
    if plan is not None:
        for wave in plan.waves:
            for packet in wave.work_packets:
                packets.append(
                    {
                        "packet_id": packet.packet_id,
                        "title": packet.title,
                        "wave_id": wave.wave_number,
                        "run_class": packet.run_class,
                        "linear_issue_id": packet.linear_issue_id,
                        "depends_on": packet.depends_on,
                        "files_in_scope": packet.files_in_scope,
                    }
                )

    actions = _mission_available_actions(mission.status.value, lifecycle)
    execution_workbench = build_mission_execution_workbench(repo_root, mission_id, actions)

    return {
        "mission": {
            "mission_id": mission.mission_id,
            "title": mission.title,
            "status": mission.status.value,
            "created_at": mission.created_at,
            "approved_at": mission.approved_at,
            "completed_at": mission.completed_at,
            "acceptance_criteria": mission.acceptance_criteria,
            "constraints": mission.constraints,
            "spec_path": mission.spec_path,
        },
        "lifecycle": lifecycle,
        "current_round": current_round,
        "rounds": round_summaries,
        "packets": packets,
        "actions": sorted(set(actions)),
        "approval_request": approval_request,
        "approval_history": approval_history,
        "approval_state": approval_state,
        "visual_qa": visual_qa,
        "acceptance_review": acceptance_review,
        "judgment_workbench": judgment_workbench,
        "learning_workbench": learning_workbench,
        "costs": costs,
        "runtime_chain": runtime_chain,
        "workspace": workspace.to_dict(),
        "execution_workbench": execution_workbench,
        "artifacts": {
            "spec": str((repo_root / mission.spec_path).relative_to(repo_root)),
            "plan": str(plan_path.relative_to(repo_root)) if plan_path.exists() else None,
            "rounds_dir": str(rounds_dir.relative_to(repo_root)) if rounds_dir.exists() else None,
        },
    }


def _gather_lifecycle_states(repo_root: Path) -> dict[str, Any]:
    manager = _get_lifecycle_manager(repo_root)
    if manager is None:
        return {}
    return {mission_id: state.to_dict() for mission_id, state in manager.all_states().items()}


__all__ = [
    "_derive_approval_state",
    "_gather_inbox",
    "_gather_judgment_workbench",
    "_gather_learning_workbench",
    "_gather_lifecycle_states",
    "_gather_mission_detail",
    "_gather_mission_execution_workbench",
    "_gather_mission_judgment_workbench",
    "_gather_mission_learning_workbench",
    "_gather_mission_runtime_chain",
    "_gather_missions",
]
