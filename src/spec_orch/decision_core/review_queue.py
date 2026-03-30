"""Review queue primitives for decision follow-up."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from spec_orch.decision_core.interventions import Intervention
from spec_orch.decision_core.models import DecisionRecord, DecisionReview


def decision_record_path(round_dir: Path) -> Path:
    return Path(round_dir) / "decision_record.json"


def intervention_queue_path(repo_root: Path, mission_id: str) -> Path:
    return Path(repo_root) / "docs" / "specs" / mission_id / "operator" / "interventions.jsonl"


def intervention_response_history_path(repo_root: Path, mission_id: str) -> Path:
    return (
        Path(repo_root)
        / "docs"
        / "specs"
        / mission_id
        / "operator"
        / "intervention_responses.jsonl"
    )


def decision_review_history_path(repo_root: Path, mission_id: str) -> Path:
    return Path(repo_root) / "docs" / "specs" / mission_id / "operator" / "decision_reviews.jsonl"


def load_intervention_response_history(repo_root: Path, mission_id: str) -> list[dict[str, Any]]:
    path = intervention_response_history_path(repo_root, mission_id)
    if not path.exists():
        return []

    history: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
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


def write_round_decision_record(round_dir: Path, record: DecisionRecord) -> Path:
    path = decision_record_path(round_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def append_intervention(
    repo_root: Path,
    mission_id: str,
    *,
    round_id: int,
    intervention: Intervention,
    decision_record_id: str,
) -> dict[str, Any]:
    payload = {
        **intervention.to_dict(),
        "decision_record_id": decision_record_id,
        "mission_id": mission_id,
        "round_id": round_id,
        "review_route": f"/?mission={mission_id}&mode=missions&tab=approvals&round={round_id}",
    }
    path = intervention_queue_path(repo_root, mission_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return payload


def load_latest_intervention(repo_root: Path, mission_id: str) -> dict[str, Any] | None:
    path = intervention_queue_path(repo_root, mission_id)
    if not path.exists():
        return None
    latest: dict[str, Any] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        latest = payload
    return latest


def append_intervention_response(
    repo_root: Path,
    mission_id: str,
    *,
    intervention_id: str,
    decision_record_id: str | None,
    action_key: str,
    label: str,
    message: str,
    channel: str,
    status: str,
    effect: str,
    timestamp: str,
) -> dict[str, Any]:
    payload = {
        "timestamp": timestamp,
        "intervention_id": intervention_id,
        "decision_record_id": decision_record_id,
        "action_key": action_key,
        "label": label,
        "message": message,
        "channel": channel,
        "status": status,
        "effect": effect,
    }
    path = intervention_response_history_path(repo_root, mission_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return payload


def append_decision_review(
    repo_root: Path,
    mission_id: str,
    *,
    review: DecisionReview,
) -> dict[str, Any]:
    payload = review.to_dict()
    path = decision_review_history_path(repo_root, mission_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return payload


def load_decision_reviews(
    repo_root: Path,
    mission_id: str,
    *,
    record_id: str | None = None,
) -> list[dict[str, Any]]:
    path = decision_review_history_path(repo_root, mission_id)
    if not path.exists():
        return []

    reviews: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        if record_id is not None and str(payload.get("record_id") or "") != record_id:
            continue
        reviews.append(payload)

    reviews.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
    return reviews


__all__ = [
    "append_decision_review",
    "append_intervention",
    "append_intervention_response",
    "decision_record_path",
    "decision_review_history_path",
    "intervention_queue_path",
    "intervention_response_history_path",
    "load_decision_reviews",
    "load_intervention_response_history",
    "load_latest_intervention",
    "write_round_decision_record",
]
