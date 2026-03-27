from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from spec_orch.services.mission_service import MissionService
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


def _gather_missions(repo_root: Path) -> list[dict[str, Any]]:
    svc = MissionService(repo_root=repo_root)
    missions = svc.list_missions()
    results = []
    for mission in missions:
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
            }
        )
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
                    "updated_at": lifecycle.get("updated_at")
                    or approval_request["timestamp"],
                    "current_round": lifecycle.get(
                        "current_round", approval_request["round_id"]
                    ),
                    "blocking_question": approval_request["blocking_question"],
                    "decision_action": approval_request["decision_action"],
                    "latest_operator_action": (
                        approval_history[0] if approval_history else None
                    ),
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
                        blocking_questions[0]
                        if blocking_questions
                        else "Paused for human input."
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
                    "summary": incidents[0].get(
                        "message", "Mission budget threshold reached."
                    ),
                    "updated_at": lifecycle.get("updated_at"),
                    "current_round": lifecycle.get("current_round", 0),
                    "budget_status": budget_status,
                    "cost_usd": costs.get("summary", {}).get("cost_usd", 0.0),
                    "operator_guidance": incidents[0].get("operator_guidance"),
                }
            )

    items.sort(
        key=lambda item: (
            {"approval": 0, "budget": 1, "paused": 2, "failed": 3}.get(
                item["kind"], 9
            ),
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
    from .surfaces import _gather_mission_costs, _gather_mission_visual_qa

    visual_qa = _gather_mission_visual_qa(repo_root, mission_id)
    costs = _gather_mission_costs(repo_root, mission_id)

    rounds_dir = repo_root / "docs/specs" / mission_id / "rounds"
    round_summaries: list[dict[str, Any]] = []
    current_round = 0
    if rounds_dir.exists():
        from spec_orch.domain.models import RoundSummary

        for round_dir in sorted(rounds_dir.glob("round-*")):
            summary_path = round_dir / "round_summary.json"
            if not summary_path.exists():
                continue
            try:
                summary = RoundSummary.from_dict(
                    json.loads(summary_path.read_text(encoding="utf-8"))
                )
            except (OSError, ValueError, json.JSONDecodeError):
                logger.warning("Skipping malformed round summary: %s", summary_path)
                continue
            current_round = max(current_round, summary.round_id)
            review_path = round_dir / "supervisor_review.md"
            visual_path = round_dir / "visual_evaluation.json"
            payload = summary.to_dict()
            payload["paths"] = {
                "round_dir": str(round_dir.relative_to(repo_root)),
                "review_memo": (
                    str(review_path.relative_to(repo_root))
                    if review_path.exists()
                    else None
                ),
                "visual_evaluation": (
                    str(visual_path.relative_to(repo_root))
                    if visual_path.exists()
                    else None
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

    actions = ["inject_guidance"]
    status_value = mission.status.value
    if status_value in {"approved", "drafting"}:
        actions.append("approve")
    if status_value in {"failed"}:
        actions.extend(["retry", "rerun"])
    if status_value in {"executing", "planned", "promoting"}:
        actions.extend(["resume", "stop", "rerun"])

    if lifecycle and lifecycle.get("round_orchestrator_state", {}).get("paused"):
        actions.append("resume")

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
        "costs": costs,
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
    "_gather_lifecycle_states",
    "_gather_mission_detail",
    "_gather_missions",
]
