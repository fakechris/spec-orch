from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _approval_history_path(repo_root: Path, mission_id: str) -> Path:
    return repo_root / "docs" / "specs" / mission_id / "operator" / "approval_actions.jsonl"


def _gather_latest_approval_request(repo_root: Path, mission_id: str) -> dict[str, Any] | None:
    rounds_dir = repo_root / "docs" / "specs" / mission_id / "rounds"
    if not rounds_dir.exists():
        return None

    from spec_orch.domain.models import RoundAction, RoundSummary

    latest: dict[str, Any] | None = None
    for round_dir in sorted(rounds_dir.glob("round-*")):
        summary_path = round_dir / "round_summary.json"
        if not summary_path.exists():
            continue
        try:
            summary = RoundSummary.from_dict(json.loads(summary_path.read_text(encoding="utf-8")))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
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
) -> dict[str, Any]:
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "action_key": action_key,
        "label": label,
        "message": message,
        "channel": channel,
    }
    history_path = _approval_history_path(repo_root, mission_id)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")
    return payload


__all__ = [
    "_gather_latest_approval_request",
    "_load_approval_history",
    "_record_approval_action",
    "_resolve_approval_action",
]
