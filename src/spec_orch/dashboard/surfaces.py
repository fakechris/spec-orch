from __future__ import annotations

import json
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spec_orch.domain.models import VisualEvaluationResult


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _load_cost_thresholds(repo_root: Path) -> dict[str, float] | None:
    config_path = repo_root / "spec-orch.toml"
    if not config_path.exists():
        return None
    try:
        with config_path.open("rb") as handle:
            raw = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return None
    dashboard_cfg = raw.get("dashboard", {})
    if not isinstance(dashboard_cfg, dict):
        return None
    costs_cfg = dashboard_cfg.get("costs", {})
    if not isinstance(costs_cfg, dict):
        return None

    warning = costs_cfg.get("warning_usd")
    critical = costs_cfg.get("critical_usd")
    thresholds: dict[str, float] = {}
    if warning is not None:
        thresholds["warning_usd"] = float(warning)
    if critical is not None:
        thresholds["critical_usd"] = float(critical)
    return thresholds or None


def _extract_visual_gallery(artifacts: dict[str, Any]) -> list[dict[str, str]]:
    image_suffixes = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg")
    gallery: list[dict[str, str]] = []
    for label, value in artifacts.items():
        if not isinstance(value, str):
            continue
        lowered = value.lower()
        if not lowered.endswith(image_suffixes):
            continue
        kind = "diff" if "diff" in label.lower() or "diff" in lowered else "image"
        gallery.append(
            {
                "label": str(label),
                "path": value,
                "kind": kind,
            }
        )
    return gallery


def _gather_approval_queue(repo_root: Path) -> dict[str, Any]:
    from .missions import _gather_inbox

    inbox = _gather_inbox(repo_root)
    approval_items = []
    for item in inbox.get("items", []):
        if item.get("kind") != "approval":
            continue
        updated_at = _parse_timestamp(str(item.get("updated_at") or ""))
        request_ts = _parse_timestamp(
            str(
                item.get("approval_request", {}).get("timestamp")
                or item.get("updated_at")
                or ""
            )
        )
        wait_minutes = 0
        if updated_at is not None and request_ts is not None:
            wait_minutes = max(0, int((updated_at - request_ts).total_seconds() // 60))

        approval_state = item.get("approval_state", {})
        urgency = "pending"
        if approval_state.get("status") == "followup_requested":
            urgency = "followup"
        elif wait_minutes >= 60:
            urgency = "stale"

        approval_items.append(
            {
                **item,
                "recommended_action": "Approve",
                "wait_minutes": wait_minutes,
                "urgency": urgency,
                "available_actions": [
                    str(action.get("key"))
                    for action in item.get("approval_request", {}).get("actions", [])
                    if action.get("key")
                ],
            }
        )

    return {
        "counts": {
            "pending": len(approval_items),
            "missions": len({item["mission_id"] for item in approval_items}),
            "requires_followup": sum(
                1 for item in approval_items if item.get("urgency") == "followup"
            ),
        },
        "items": approval_items,
    }


def _gather_mission_visual_qa(repo_root: Path, mission_id: str) -> dict[str, Any]:
    rounds_dir = repo_root / "docs" / "specs" / mission_id / "rounds"
    if not rounds_dir.exists():
        return {
            "mission_id": mission_id,
            "summary": {
                "total_rounds": 0,
                "blocking_findings": 0,
                "warning_findings": 0,
                "latest_confidence": 0.0,
            },
            "rounds": [],
        }

    visual_rounds: list[dict[str, Any]] = []
    for round_dir in sorted(rounds_dir.glob("round-*")):
        visual_path = round_dir / "visual_evaluation.json"
        if not visual_path.exists():
            continue
        try:
            payload = json.loads(visual_path.read_text(encoding="utf-8"))
            visual = VisualEvaluationResult.from_dict(payload)
        except (OSError, ValueError, json.JSONDecodeError):
            continue

        round_id = int(round_dir.name.split("-")[-1])
        findings = visual.findings or []
        severities = {str(finding.get("severity", "")).lower() for finding in findings}
        if "blocking" in severities:
            status = "blocking"
        elif "warning" in severities:
            status = "warning"
        else:
            status = "pass"
        visual_rounds.append(
            {
                "round_id": round_id,
                "summary": visual.summary,
                "confidence": visual.confidence,
                "status": status,
                "artifact_path": str(visual_path.relative_to(repo_root)),
                "findings": findings,
                "artifacts": visual.artifacts,
                "gallery": _extract_visual_gallery(visual.artifacts),
                "primary_artifact": (
                    _extract_visual_gallery(visual.artifacts)[0]["path"]
                    if _extract_visual_gallery(visual.artifacts)
                    else None
                ),
            }
        )

    visual_rounds.sort(key=lambda item: item["round_id"])
    latest_confidence = visual_rounds[-1]["confidence"] if visual_rounds else 0.0
    blocking_findings = sum(
        1
        for item in visual_rounds
        for finding in item["findings"]
        if str(finding.get("severity", "")).lower() == "blocking"
    )
    warning_findings = sum(
        1
        for item in visual_rounds
        for finding in item["findings"]
        if str(finding.get("severity", "")).lower() == "warning"
    )
    blocking_rounds = [
        item["round_id"] for item in visual_rounds if item.get("status") == "blocking"
    ]
    gallery_items = sum(len(item.get("gallery", [])) for item in visual_rounds)
    return {
        "mission_id": mission_id,
        "summary": {
            "total_rounds": len(visual_rounds),
            "blocking_findings": blocking_findings,
            "warning_findings": warning_findings,
            "latest_confidence": latest_confidence,
            "blocking_rounds": blocking_rounds,
            "gallery_items": gallery_items,
        },
        "rounds": visual_rounds,
    }


def _gather_mission_costs(repo_root: Path, mission_id: str) -> dict[str, Any]:
    thresholds = _load_cost_thresholds(repo_root)
    workers_dir = repo_root / "docs" / "specs" / mission_id / "workers"
    if not workers_dir.exists():
        return {
            "mission_id": mission_id,
            "summary": {
                "workers": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0.0,
                "budget_status": "unconfigured",
                "thresholds": thresholds,
            },
            "incidents": [],
            "workers": [],
        }

    worker_rows: list[dict[str, Any]] = []
    total_input = 0
    total_output = 0
    total_cost = 0.0
    for worker_dir in sorted(path for path in workers_dir.iterdir() if path.is_dir()):
        report_path = worker_dir / "builder_report.json"
        if not report_path.exists():
            continue
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}
        usage = metadata.get("usage", {}) if isinstance(metadata, dict) else {}
        input_tokens = int(usage.get("input_tokens", 0) or 0)
        output_tokens = int(usage.get("output_tokens", 0) or 0)
        cost_usd = float(metadata.get("cost_usd", 0.0) or 0.0)
        total_input += input_tokens
        total_output += output_tokens
        total_cost += cost_usd
        worker_rows.append(
            {
                "packet_id": worker_dir.name,
                "report_path": str(report_path.relative_to(repo_root)),
                "adapter": payload.get("adapter", ""),
                "turn_status": metadata.get("turn_status", ""),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": cost_usd,
            }
        )

    budget_status = "unconfigured"
    incidents: list[dict[str, Any]] = []
    if thresholds:
        warning = thresholds.get("warning_usd")
        critical = thresholds.get("critical_usd")
        if critical is not None and total_cost >= critical:
            budget_status = "critical"
            incidents.append(
                {
                    "severity": "critical",
                    "message": "Mission cost exceeded critical budget threshold.",
                    "actual_cost_usd": round(total_cost, 4),
                    "threshold_usd": critical,
                }
            )
        elif warning is not None and total_cost >= warning:
            budget_status = "warning"
            incidents.append(
                {
                    "severity": "warning",
                    "message": "Mission cost exceeded warning budget threshold.",
                    "actual_cost_usd": round(total_cost, 4),
                    "threshold_usd": warning,
                }
            )
        else:
            budget_status = "healthy"

    return {
        "mission_id": mission_id,
        "summary": {
            "workers": len(worker_rows),
            "input_tokens": total_input,
            "output_tokens": total_output,
            "cost_usd": total_cost,
            "budget_status": budget_status,
            "thresholds": thresholds,
        },
        "incidents": incidents,
        "workers": worker_rows,
    }


__all__ = [
    "_gather_approval_queue",
    "_gather_mission_costs",
    "_gather_mission_visual_qa",
]
