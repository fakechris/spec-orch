from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _gather_packet_transcript(
    repo_root: Path,
    mission_id: str,
    packet_id: str,
) -> dict[str, Any]:
    packet_root = repo_root / "docs" / "specs" / mission_id / "workers" / packet_id
    telemetry_root = packet_root / "telemetry"
    activity_path = telemetry_root / "activity.log"
    events_path = telemetry_root / "events.jsonl"
    incoming_path = telemetry_root / "incoming_events.jsonl"

    if not telemetry_root.exists():
        return {
            "mission_id": mission_id,
            "packet_id": packet_id,
            "entries": [],
            "summary": {
                "entry_count": 0,
                "kind_counts": {},
                "block_counts": {},
                "latest_timestamp": None,
            },
            "milestones": [],
            "blocks": [],
            "telemetry": {
                "activity_log": None,
                "events": None,
                "incoming": None,
            },
        }

    entries: list[dict[str, Any]] = []
    milestones: list[dict[str, Any]] = []
    if activity_path.exists():
        for line in activity_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            ts, _, message = line.partition(" ")
            entries.append(
                {
                    "kind": "activity",
                    "timestamp": ts if message else "",
                    "message": message or line,
                    "raw": line,
                    "source_path": str(activity_path.relative_to(repo_root)),
                }
            )

    if events_path.exists():
        for line in events_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            entries.append(
                {
                    "kind": "event",
                    "timestamp": payload.get("timestamp", ""),
                    "message": payload.get("message", payload.get("event_type", "event")),
                    "event_type": payload.get("event_type", ""),
                    "raw": payload,
                    "source_path": str(events_path.relative_to(repo_root)),
                }
            )
            event_type = payload.get("event_type", "")
            if isinstance(event_type, str) and event_type.startswith("mission_packet_"):
                milestones.append(
                    {
                        "timestamp": payload.get("timestamp", ""),
                        "event_type": event_type,
                        "message": payload.get("message", event_type),
                    }
                )

    if incoming_path.exists():
        for line in incoming_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            entries.append(
                {
                    "kind": "incoming",
                    "timestamp": payload.get("ts", payload.get("timestamp", "")),
                    "message": payload.get(
                        "excerpt",
                        payload.get("message", payload.get("kind", "")),
                    ),
                    "event_type": payload.get("kind", ""),
                    "raw": payload,
                    "source_path": str(incoming_path.relative_to(repo_root)),
                }
            )

    entries.sort(key=lambda entry: (entry.get("timestamp", ""), entry.get("kind", "")))
    kind_counts: dict[str, int] = {}
    latest_timestamp: str | None = None
    for entry in entries:
        kind = str(entry.get("kind", "event"))
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
        timestamp = entry.get("timestamp")
        if isinstance(timestamp, str) and timestamp:
            latest_timestamp = timestamp

    blocks = [_transcript_block_from_entry(entry) for entry in entries]
    blocks = _group_transcript_blocks(blocks)
    blocks.extend(_gather_round_evidence_blocks(repo_root, mission_id, packet_id))
    blocks.sort(key=lambda block: (block.get("timestamp", ""), block.get("block_type", "")))

    block_counts: dict[str, int] = {}
    for block in blocks:
        block_type = str(block.get("block_type", "event"))
        block_counts[block_type] = block_counts.get(block_type, 0) + 1

    return {
        "mission_id": mission_id,
        "packet_id": packet_id,
        "entries": entries,
        "summary": {
            "entry_count": len(entries),
            "kind_counts": kind_counts,
            "block_counts": block_counts,
            "latest_timestamp": latest_timestamp,
        },
        "milestones": milestones,
        "blocks": blocks,
        "telemetry": {
            "activity_log": (
                str(activity_path.relative_to(repo_root))
                if activity_path.exists()
                else None
            ),
            "events": str(events_path.relative_to(repo_root)) if events_path.exists() else None,
            "incoming": (
                str(incoming_path.relative_to(repo_root))
                if incoming_path.exists()
                else None
            ),
        },
    }


def _transcript_block_from_entry(entry: dict[str, Any]) -> dict[str, Any]:
    kind = str(entry.get("kind", "event"))
    event_type = str(entry.get("event_type", ""))
    message = str(entry.get("message", event_type or kind))
    raw = entry.get("raw")
    details = raw if isinstance(raw, dict) else None

    if kind == "activity":
        body = raw if isinstance(raw, str) else message
        return {
            "block_type": "activity",
            "timestamp": str(entry.get("timestamp", "")),
            "title": message,
            "body": body,
            "source_path": entry.get("source_path"),
        }

    if kind == "incoming":
        block = {
            "block_type": "message",
            "timestamp": str(entry.get("timestamp", "")),
            "title": message,
            "body": event_type or kind,
            "source_path": entry.get("source_path"),
        }
        if details is not None:
            block["details"] = details
        return block

    if event_type.startswith("mission_packet_"):
        block = {
            "block_type": "milestone",
            "timestamp": str(entry.get("timestamp", "")),
            "title": message,
            "body": event_type,
            "source_path": entry.get("source_path"),
        }
        if details is not None:
            block["details"] = details
        return block

    if "tool_call" in event_type:
        block = {
            "block_type": "tool",
            "timestamp": str(entry.get("timestamp", "")),
            "title": message,
            "body": event_type,
            "source_path": entry.get("source_path"),
        }
        if details is not None:
            block["details"] = details
        return block

    block = {
        "block_type": "event",
        "timestamp": str(entry.get("timestamp", "")),
        "title": message,
        "body": event_type or kind,
        "source_path": entry.get("source_path"),
    }
    if details is not None:
        block["details"] = details
    return block


def _group_transcript_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: list[dict[str, Any]] = []
    current_tool_burst: list[dict[str, Any]] = []

    def flush_tool_burst() -> None:
        nonlocal current_tool_burst
        if not current_tool_burst:
            return
        if len(current_tool_burst) == 1:
            grouped.extend(current_tool_burst)
        else:
            grouped.append(
                {
                    "block_type": "command_burst",
                    "timestamp": current_tool_burst[0].get("timestamp", ""),
                    "title": f"{len(current_tool_burst)} tool events",
                    "body": " • ".join(
                        str(item.get("title", item.get("body", "tool event")))
                        for item in current_tool_burst
                    ),
                    "source_path": current_tool_burst[0].get("source_path"),
                    "details": {
                        "item_count": len(current_tool_burst),
                        "event_types": [
                            str(item.get("body", item.get("block_type", "tool")))
                            for item in current_tool_burst
                        ],
                    },
                    "items": current_tool_burst,
                }
            )
        current_tool_burst = []

    for block in blocks:
        if block.get("block_type") == "tool":
            current_tool_burst.append(block)
            continue
        flush_tool_burst()
        grouped.append(block)

    flush_tool_burst()
    return grouped


def _gather_round_evidence_blocks(
    repo_root: Path,
    mission_id: str,
    packet_id: str,
) -> list[dict[str, Any]]:
    rounds_dir = repo_root / "docs" / "specs" / mission_id / "rounds"
    if not rounds_dir.exists():
        return []

    from spec_orch.domain.models import RoundSummary, VisualEvaluationResult

    blocks: list[dict[str, Any]] = []
    for round_dir in sorted(rounds_dir.glob("round-*")):
        summary_path = round_dir / "round_summary.json"
        if not summary_path.exists():
            continue
        try:
            summary = RoundSummary.from_dict(json.loads(summary_path.read_text(encoding="utf-8")))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not any(result.get("packet_id") == packet_id for result in summary.worker_results):
            continue

        timestamp = summary.completed_at or summary.started_at or ""
        if summary.decision is not None:
            blocks.append(
                {
                    "block_type": "supervisor",
                    "timestamp": timestamp,
                    "title": summary.decision.summary or "Supervisor decision",
                    "body": summary.decision.action.value,
                    "artifact_path": str(
                        (round_dir / "supervisor_review.md").relative_to(repo_root)
                    ),
                    "details": {
                        "reason_code": summary.decision.reason_code,
                        "confidence": summary.decision.confidence,
                        "blocking_questions": summary.decision.blocking_questions,
                    },
                }
            )

        visual_path = round_dir / "visual_evaluation.json"
        if visual_path.exists():
            try:
                visual = VisualEvaluationResult.from_dict(
                    json.loads(visual_path.read_text(encoding="utf-8"))
                )
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            blocks.append(
                {
                    "block_type": "visual_finding",
                    "timestamp": timestamp,
                    "title": visual.summary or "Visual evaluation result",
                    "body": visual.evaluator,
                    "artifact_path": str(visual_path.relative_to(repo_root)),
                    "details": {
                        "confidence": visual.confidence,
                        "findings": visual.findings,
                        "artifacts": visual.artifacts,
                    },
                }
            )

    return blocks


__all__ = [
    "_gather_packet_transcript",
    "_transcript_block_from_entry",
    "_group_transcript_blocks",
    "_gather_round_evidence_blocks",
]
