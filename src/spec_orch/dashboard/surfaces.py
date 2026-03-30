from __future__ import annotations

import json
import logging
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spec_orch.acceptance_core.calibration import dashboard_surface_pack_v1
from spec_orch.acceptance_core.disposition import AcceptanceDisposition
from spec_orch.acceptance_core.models import build_acceptance_judgments
from spec_orch.domain.models import AcceptanceReviewResult, VisualEvaluationResult
from spec_orch.runtime_core.readers import (
    read_round_supervision_cycle,
    read_worker_execution_attempt,
)

logger = logging.getLogger(__name__)


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
    for key, value in (("warning_usd", warning), ("critical_usd", critical)):
        if value is None:
            continue
        try:
            thresholds[key] = float(value)
        except (TypeError, ValueError):
            logger.warning("Ignoring invalid dashboard cost threshold %s=%r", key, value)
    return thresholds or None


def _safe_int(value: Any, *, context: str) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        logger.warning("Ignoring invalid integer value for %s: %r", context, value)
        return 0


def _safe_float(value: Any, *, context: str) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        logger.warning("Ignoring invalid float value for %s: %r", context, value)
        return 0.0


def _extract_visual_gallery(artifacts: dict[str, Any]) -> list[dict[str, str]]:
    image_suffixes = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg")
    gallery: list[dict[str, str]] = []
    for label, value in artifacts.items():
        if not isinstance(value, str):
            continue
        lowered = value.lower()
        if not lowered.endswith(image_suffixes):
            continue
        basename = Path(value).name.lower()
        kind = "diff" if "diff" in label.lower() or "diff" in basename else "image"
        gallery.append(
            {
                "label": str(label),
                "path": value,
                "kind": kind,
            }
        )
    return gallery


def _visual_comparison_from_gallery(
    gallery: list[dict[str, str]],
) -> dict[str, Any] | None:
    if not gallery:
        return None
    primary = next((item for item in gallery if item.get("kind") == "diff"), None)
    if primary is None:
        return None
    related = [
        {
            "label": str(item.get("label", "")),
            "path": str(item.get("path", "")),
            "kind": str(item.get("kind", "image")),
        }
        for item in gallery
        if item is not primary
    ]
    return {
        "mode": "diff-first",
        "primary": {
            "label": str(primary.get("label", "")),
            "path": str(primary.get("path", "")),
            "kind": str(primary.get("kind", "diff")),
        },
        "related": related,
    }


def _budget_guidance(severity: str) -> tuple[str, str]:
    if severity == "critical":
        return (
            "Critical budget threshold exceeded",
            "Pause new work, review packet cost hotspots, "
            "and decide whether to cut scope or raise the budget.",
        )
    return (
        "Warning budget threshold reached",
        "Review recent worker spend and decide whether this mission should continue unchanged.",
    )


def _gather_approval_queue(repo_root: Path) -> dict[str, Any]:
    from .missions import _gather_inbox

    inbox = _gather_inbox(repo_root)
    approval_items = []
    for item in inbox.get("items", []):
        if item.get("kind") != "approval":
            continue
        updated_at = _parse_timestamp(str(item.get("updated_at") or ""))
        request_ts = _parse_timestamp(
            str(item.get("approval_request", {}).get("timestamp") or item.get("updated_at") or "")
        )
        wait_minutes = 0
        if request_ts is not None:
            now = datetime.now(UTC)
            wait_minutes = max(0, int((now - request_ts).total_seconds() // 60))
        elif updated_at is not None:
            now = datetime.now(UTC)
            wait_minutes = max(0, int((now - updated_at).total_seconds() // 60))

        approval_state = item.get("approval_state", {})
        urgency = "pending"
        if approval_state.get("status") == "followup_requested":
            urgency = "followup"
        elif wait_minutes >= 60:
            urgency = "stale"
        age_bucket = "fresh"
        if wait_minutes >= 180:
            age_bucket = "aged"
        elif wait_minutes >= 60:
            age_bucket = "stale"

        approval_items.append(
            {
                **item,
                "recommended_action": "Approve",
                "wait_minutes": wait_minutes,
                "urgency": urgency,
                "age_bucket": age_bucket,
                "review_route": f"/?mission={item['mission_id']}&mode=missions&tab=approvals",
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
            "stale": sum(1 for item in approval_items if item.get("age_bucket") == "stale"),
            "aged": sum(1 for item in approval_items if item.get("age_bucket") == "aged"),
            "failed_actions": sum(
                1
                for item in approval_items
                if (item.get("latest_operator_action") or {}).get("status") == "failed"
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
                "blocking_rounds": [],
                "gallery_items": 0,
                "diff_items": 0,
                "comparison_rounds": 0,
                "focus_transcript_route": None,
            },
            "review_route": f"/?mission={mission_id}&mode=missions&tab=visual",
            "rounds": [],
        }

    visual_rounds: list[dict[str, Any]] = []
    for round_dir in sorted(rounds_dir.glob("round-*")):
        normalized = read_round_supervision_cycle(round_dir)
        if normalized is not None:
            summary_payload = normalized.get("summary", {})
            if not isinstance(summary_payload, dict):
                summary_payload = {}
            visual_artifact = normalized.get("artifacts", {}).get("visual_report")
            if visual_artifact is None:
                continue
            visual_path = Path(visual_artifact.path)
            try:
                round_id = int(summary_payload.get("round_id") or round_dir.name.split("-")[-1])
            except (TypeError, ValueError, IndexError):
                logger.warning(
                    "Skipping visual QA directory with invalid round suffix: %s",
                    round_dir,
                )
                continue
            worker_results = summary_payload.get("worker_results", [])
            transcript_routes = [
                f"/?mission={mission_id}&mode=missions&tab=transcript&packet={packet_id}"
                for item in worker_results
                if isinstance(item, dict)
                for packet_id in [item.get("packet_id")]
                if isinstance(packet_id, str) and packet_id
            ]
            try:
                payload = json.loads(visual_path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    logger.warning("Ignoring malformed visual evaluation payload: %s", visual_path)
                    continue
                visual = VisualEvaluationResult.from_dict(payload)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
        else:
            visual_path = round_dir / "visual_evaluation.json"
            if not visual_path.exists():
                continue
            try:
                round_id = int(round_dir.name.split("-")[-1])
            except (TypeError, ValueError, IndexError):
                logger.warning(
                    "Skipping visual QA directory with invalid round suffix: %s",
                    round_dir,
                )
                continue
            transcript_routes = []
            summary_path = round_dir / "round_summary.json"
            if summary_path.exists():
                try:
                    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
                except (OSError, ValueError, json.JSONDecodeError):
                    summary_payload = {}
                if not isinstance(summary_payload, dict):
                    logger.warning(
                        "Ignoring malformed round summary for visual QA: %s",
                        summary_path,
                    )
                    summary_payload = {}
                worker_results = summary_payload.get("worker_results", [])
                if isinstance(worker_results, list):
                    transcript_routes = [
                        f"/?mission={mission_id}&mode=missions&tab=transcript&packet={packet_id}"
                        for item in worker_results
                        if isinstance(item, dict)
                        for packet_id in [item.get("packet_id")]
                        if isinstance(packet_id, str) and packet_id
                    ]
            try:
                payload = json.loads(visual_path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    logger.warning("Ignoring malformed visual evaluation payload: %s", visual_path)
                    continue
                visual = VisualEvaluationResult.from_dict(payload)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
        findings = [finding for finding in (visual.findings or []) if isinstance(finding, dict)]
        artifacts = visual.artifacts if isinstance(visual.artifacts, dict) else {}
        severities = {str(finding.get("severity", "")).lower() for finding in findings}
        if "blocking" in severities:
            status = "blocking"
        elif "warning" in severities:
            status = "warning"
        else:
            status = "pass"
        gallery = _extract_visual_gallery(artifacts)
        comparison = _visual_comparison_from_gallery(gallery)
        visual_rounds.append(
            {
                "round_id": round_id,
                "summary": visual.summary,
                "confidence": visual.confidence,
                "status": status,
                "artifact_path": str(visual_path.relative_to(repo_root)),
                "findings": findings,
                "artifacts": artifacts,
                "gallery": gallery,
                "primary_artifact": (gallery[0]["path"] if gallery else None),
                "comparison": comparison,
                "transcript_routes": transcript_routes,
                "review_route": f"/?mission={mission_id}&mode=missions&tab=visual&round={round_id}",
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
    diff_items = sum(
        1
        for item in visual_rounds
        for gallery_item in item.get("gallery", [])
        if gallery_item.get("kind") == "diff"
    )
    comparison_rounds = sum(1 for item in visual_rounds if item.get("comparison") is not None)
    focus_transcript_route = next(
        (
            route
            for item in visual_rounds
            if item.get("status") == "blocking"
            for route in item.get("transcript_routes", [])
        ),
        None,
    )
    return {
        "mission_id": mission_id,
        "summary": {
            "total_rounds": len(visual_rounds),
            "blocking_findings": blocking_findings,
            "warning_findings": warning_findings,
            "latest_confidence": latest_confidence,
            "blocking_rounds": blocking_rounds,
            "gallery_items": gallery_items,
            "diff_items": diff_items,
            "comparison_rounds": comparison_rounds,
            "focus_transcript_route": focus_transcript_route,
        },
        "review_route": f"/?mission={mission_id}&mode=missions&tab=visual",
        "rounds": visual_rounds,
    }


def _gather_mission_acceptance_review(repo_root: Path, mission_id: str) -> dict[str, Any]:
    rounds_dir = repo_root / "docs" / "specs" / mission_id / "rounds"
    review_route = f"/?mission={mission_id}&mode=missions&tab=acceptance"
    if not rounds_dir.exists():
        return {
            "mission_id": mission_id,
            "summary": {
                "total_reviews": 0,
                "passes": 0,
                "warnings": 0,
                "failures": 0,
                "filed_issues": 0,
                "latest_confidence": 0.0,
            },
            "review_route": review_route,
            "latest_review": None,
            "reviews": [],
        }

    reviews: list[dict[str, Any]] = []
    round_dirs: list[tuple[int, Path]] = []
    for round_dir in rounds_dir.glob("round-*"):
        try:
            round_id = int(round_dir.name.split("-")[-1])
        except (TypeError, ValueError, IndexError):
            logger.warning("Skipping acceptance directory with invalid round suffix: %s", round_dir)
            continue
        round_dirs.append((round_id, round_dir))

    for round_id, round_dir in sorted(round_dirs, key=lambda item: item[0]):
        review_path = round_dir / "acceptance_review.json"
        if not review_path.exists():
            continue
        try:
            payload = json.loads(review_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                logger.warning("Ignoring malformed acceptance review payload: %s", review_path)
                continue
            review = AcceptanceReviewResult.from_dict(payload)
        except (OSError, ValueError, json.JSONDecodeError):
            continue

        review_data = review.to_dict()
        judgments = [judgment.to_dict() for judgment in build_acceptance_judgments(review)]
        surface_pack = dashboard_surface_pack_v1(mission_id).to_dict()
        review_data.update(
            {
                "round_id": round_id,
                "artifact_path": str(review_path.relative_to(repo_root)),
                "judgments": judgments,
                "surface_pack": surface_pack,
                "candidate_findings": [
                    judgment
                    for judgment in judgments
                    if judgment.get("judgment_class") == "candidate_finding"
                ],
                "filed_issues": [
                    proposal.to_dict()
                    for proposal in review.issue_proposals
                    if proposal.linear_issue_id or proposal.filing_status == "filed"
                ],
                "disposition_vocab": [item.value for item in AcceptanceDisposition],
                "review_route": (
                    f"/?mission={mission_id}&mode=missions&tab=acceptance&round={round_id}"
                ),
            }
        )
        reviews.append(review_data)

    summary = {
        "total_reviews": len(reviews),
        "passes": sum(1 for review in reviews if review.get("status") == "pass"),
        "warnings": sum(1 for review in reviews if review.get("status") == "warn"),
        "failures": sum(1 for review in reviews if review.get("status") == "fail"),
        "filed_issues": sum(len(review.get("filed_issues", [])) for review in reviews),
        "latest_confidence": float(reviews[-1].get("confidence", 0.0)) if reviews else 0.0,
    }
    return {
        "mission_id": mission_id,
        "summary": summary,
        "review_route": review_route,
        "latest_review": reviews[-1] if reviews else None,
        "reviews": reviews,
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
                "incident_count": 0,
                "remaining_budget_usd": None,
            },
            "review_route": f"/?mission={mission_id}&mode=missions&tab=costs",
            "focus_packet_id": None,
            "highest_cost_worker": None,
            "incidents": [],
            "workers": [],
        }

    worker_rows: list[dict[str, Any]] = []
    total_input = 0
    total_output = 0
    total_cost = 0.0
    for worker_dir in sorted(path for path in workers_dir.iterdir() if path.is_dir()):
        normalized = read_worker_execution_attempt(
            worker_dir,
            mission_id=mission_id,
            packet_id=worker_dir.name,
        )
        if normalized is not None:
            payload = normalized.outcome.build or {}
            report_artifact = normalized.outcome.artifacts.get("builder_report")
            report_path = (
                Path(report_artifact.path)
                if report_artifact is not None
                else (worker_dir / "builder_report.json")
            )
            if not isinstance(payload, dict):
                continue
        else:
            report_path = worker_dir / "builder_report.json"
            if not report_path.exists():
                continue
            try:
                payload = json.loads(report_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                logger.warning("Ignoring malformed builder report payload: %s", report_path)
                continue
        metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}
        usage = metadata.get("usage", {}) if isinstance(metadata, dict) else {}
        input_tokens = _safe_int(
            usage.get("input_tokens", 0),
            context=f"{worker_dir.name}.input_tokens",
        )
        output_tokens = _safe_int(
            usage.get("output_tokens", 0),
            context=f"{worker_dir.name}.output_tokens",
        )
        cost_usd = _safe_float(
            metadata.get("cost_usd", 0.0),
            context=f"{worker_dir.name}.cost_usd",
        )
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
                "transcript_route": (
                    f"/?mission={mission_id}&mode=missions&tab=transcript&packet={worker_dir.name}"
                ),
            }
        )

    highest_cost_worker = None
    focus_packet_id = None
    if worker_rows:
        highest_cost_worker = max(worker_rows, key=lambda item: float(item.get("cost_usd", 0.0)))
        focus_packet_id = str(highest_cost_worker.get("packet_id") or "") or None

    budget_status = "unconfigured"
    incidents: list[dict[str, Any]] = []
    remaining_budget_usd: float | None = None
    if thresholds:
        warning = thresholds.get("warning_usd")
        critical = thresholds.get("critical_usd")
        if critical is not None:
            remaining_budget_usd = round(critical - total_cost, 4)
        if critical is not None and total_cost >= critical:
            budget_status = "critical"
            status_copy, operator_guidance = _budget_guidance("critical")
            incidents.append(
                {
                    "severity": "critical",
                    "message": "Mission cost exceeded critical budget threshold.",
                    "status_copy": status_copy,
                    "recommended_action": operator_guidance,
                    "operator_guidance": (
                        "Open the mission, inspect the most expensive packets, "
                        "and either reduce scope or explicitly continue at higher spend."
                    ),
                    "suggested_action": {
                        "label": "Open mission costs",
                        "route": f"/?mission={mission_id}&mode=missions&tab=costs",
                    },
                    "transcript_route": (
                        f"/?mission={mission_id}&mode=missions&tab=transcript&packet={focus_packet_id}"
                        if focus_packet_id
                        else None
                    ),
                    "actual_cost_usd": round(total_cost, 4),
                    "threshold_usd": critical,
                }
            )
        elif warning is not None and total_cost >= warning:
            budget_status = "warning"
            status_copy, operator_guidance = _budget_guidance("warning")
            incidents.append(
                {
                    "severity": "warning",
                    "message": "Mission cost exceeded warning budget threshold.",
                    "status_copy": status_copy,
                    "recommended_action": operator_guidance,
                    "operator_guidance": (
                        "Open the mission, inspect the highest-cost packets, "
                        "and decide whether to keep spending at the current pace."
                    ),
                    "suggested_action": {
                        "label": "Open mission costs",
                        "route": f"/?mission={mission_id}&mode=missions&tab=costs",
                    },
                    "transcript_route": (
                        f"/?mission={mission_id}&mode=missions&tab=transcript&packet={focus_packet_id}"
                        if focus_packet_id
                        else None
                    ),
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
            "incident_count": len(incidents),
            "remaining_budget_usd": remaining_budget_usd,
        },
        "review_route": f"/?mission={mission_id}&mode=missions&tab=costs",
        "focus_packet_id": focus_packet_id,
        "highest_cost_worker": (
            {
                "packet_id": highest_cost_worker["packet_id"],
                "cost_usd": highest_cost_worker["cost_usd"],
                "report_path": highest_cost_worker["report_path"],
                "transcript_route": highest_cost_worker["transcript_route"],
            }
            if highest_cost_worker
            else None
        ),
        "incidents": incidents,
        "workers": worker_rows,
    }


__all__ = [
    "_gather_approval_queue",
    "_gather_mission_acceptance_review",
    "_gather_mission_costs",
    "_gather_mission_visual_qa",
]
