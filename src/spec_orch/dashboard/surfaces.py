from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from spec_orch.domain.models import VisualEvaluationResult


def _gather_approval_queue(repo_root: Path) -> dict[str, Any]:
    from .missions import _gather_inbox

    inbox = _gather_inbox(repo_root)
    approval_items = []
    for item in inbox.get("items", []):
        if item.get("kind") != "approval":
            continue
        approval_items.append(
            {
                **item,
                "recommended_action": "Approve",
            }
        )

    return {
        "counts": {
            "pending": len(approval_items),
            "missions": len({item["mission_id"] for item in approval_items}),
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
    return {
        "mission_id": mission_id,
        "summary": {
            "total_rounds": len(visual_rounds),
            "blocking_findings": blocking_findings,
            "warning_findings": warning_findings,
            "latest_confidence": latest_confidence,
        },
        "rounds": visual_rounds,
    }


def _gather_mission_costs(repo_root: Path, mission_id: str) -> dict[str, Any]:
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
            },
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

    return {
        "mission_id": mission_id,
        "summary": {
            "workers": len(worker_rows),
            "input_tokens": total_input,
            "output_tokens": total_output,
            "cost_usd": total_cost,
            "budget_status": "unconfigured",
        },
        "workers": worker_rows,
    }


__all__ = [
    "_gather_approval_queue",
    "_gather_mission_costs",
    "_gather_mission_visual_qa",
]
