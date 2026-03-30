from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spec_orch.decision_core.review_queue import (
    append_intervention_response,
    load_intervention_response_history,
    load_latest_intervention,
)


def _approval_history_path(repo_root: Path, mission_id: str) -> Path:
    return repo_root / "docs" / "specs" / mission_id / "operator" / "approval_actions.jsonl"


def _gather_latest_approval_request(repo_root: Path, mission_id: str) -> dict[str, Any] | None:
    intervention = load_latest_intervention(repo_root, mission_id)
    if intervention is not None:
        questions = intervention.get("questions", [])
        blocking_question = questions[0] if questions else None
        round_id = int(intervention.get("round_id", 0))
        review_route = str(
            intervention.get("review_route")
            or f"/?mission={mission_id}&mode=missions&tab=approvals&round={round_id}"
        )
        return {
            "round_id": round_id,
            "timestamp": str(intervention.get("created_at", "")),
            "summary": str(intervention.get("summary") or "Human approval required."),
            "blocking_question": blocking_question,
            "decision_action": "ask_human",
            "review_route": review_route,
            "actions": [
                {
                    "key": "approve",
                    "label": "Approve",
                    "message": "@approve "
                    + (blocking_question if blocking_question else "Approve this round."),
                },
                {
                    "key": "request_revision",
                    "label": "Request revision",
                    "message": "@request-revision Please revise this round before rollout.",
                },
                {
                    "key": "ask_followup",
                    "label": "Ask follow-up",
                    "message": "@follow-up I need more detail before approving this round.",
                },
            ],
        }

    rounds_dir = repo_root / "docs" / "specs" / mission_id / "rounds"
    if not rounds_dir.exists():
        return None

    from spec_orch.domain.models import RoundAction, RoundSummary

    latest: dict[str, Any] | None = None
    latest_round_id_seen = -1
    for round_dir in sorted(rounds_dir.glob("round-*")):
        summary_path = round_dir / "round_summary.json"
        if not summary_path.exists():
            continue
        try:
            summary = RoundSummary.from_dict(json.loads(summary_path.read_text(encoding="utf-8")))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        latest_round_id_seen = max(latest_round_id_seen, int(summary.round_id))
        if summary.decision is None or summary.decision.action is not RoundAction.ASK_HUMAN:
            continue

        latest = {
            "round_id": summary.round_id,
            "timestamp": summary.completed_at or summary.started_at or "",
            "summary": summary.decision.summary or "Human approval required.",
            "blocking_question": (
                summary.decision.blocking_questions[0]
                if summary.decision.blocking_questions
                else None
            ),
            "decision_action": summary.decision.action.value,
            "review_route": (
                f"/?mission={mission_id}&mode=missions&tab=approvals&round={summary.round_id}"
            ),
            "actions": [
                {
                    "key": "approve",
                    "label": "Approve",
                    "message": "@approve "
                    + (
                        summary.decision.blocking_questions[0]
                        if summary.decision.blocking_questions
                        else "Approve this round."
                    ),
                },
                {
                    "key": "request_revision",
                    "label": "Request revision",
                    "message": "@request-revision Please revise this round before rollout.",
                },
                {
                    "key": "ask_followup",
                    "label": "Ask follow-up",
                    "message": "@follow-up I need more detail before approving this round.",
                },
            ],
        }
    if latest is None:
        return None
    if int(latest.get("round_id", -1)) != latest_round_id_seen:
        return None
    return latest


def _resolve_approval_action(
    repo_root: Path,
    mission_id: str,
    action_key: str,
) -> dict[str, str] | None:
    approval_request = _gather_latest_approval_request(repo_root, mission_id)
    if approval_request is None:
        return None
    for action in approval_request.get("actions", []):
        if action.get("key") == action_key:
            return {
                "key": action_key,
                "label": str(action.get("label") or action_key),
                "message": str(action.get("message") or ""),
            }
    return None


def _load_approval_history(repo_root: Path, mission_id: str) -> list[dict[str, Any]]:
    response_history = load_intervention_response_history(repo_root, mission_id)
    if response_history:
        return response_history

    history_path = _approval_history_path(repo_root, mission_id)
    if not history_path.exists():
        return []

    history: list[dict[str, Any]] = []
    for line in history_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            history.append(payload)

    history.sort(key=lambda item: str(item.get("timestamp", "")), reverse=True)
    return history


def _record_approval_action(
    repo_root: Path,
    mission_id: str,
    *,
    action_key: str,
    label: str,
    message: str,
    channel: str,
    status: str = "sent",
) -> dict[str, Any]:
    timestamp = datetime.now(UTC).isoformat()
    effect = {
        "approve": "approval_granted",
        "request_revision": "revision_requested",
        "ask_followup": "followup_requested",
    }.get(action_key, "guidance_sent")
    payload = {
        "timestamp": timestamp,
        "action_key": action_key,
        "label": label,
        "message": message,
        "channel": channel,
        "status": status,
        "effect": effect,
    }
    history_path = _approval_history_path(repo_root, mission_id)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")

    intervention = load_latest_intervention(repo_root, mission_id)
    if intervention is not None:
        append_intervention_response(
            repo_root,
            mission_id,
            intervention_id=str(intervention.get("intervention_id") or ""),
            decision_record_id=(
                str(intervention.get("decision_record_id"))
                if intervention.get("decision_record_id") is not None
                else None
            ),
            action_key=action_key,
            label=label,
            message=message,
            channel=channel,
            status=status,
            effect=effect,
            timestamp=timestamp,
        )
    return payload


__all__ = [
    "_gather_latest_approval_request",
    "_load_approval_history",
    "_record_approval_action",
    "_resolve_approval_action",
]
