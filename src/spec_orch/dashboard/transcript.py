from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from spec_orch.services.execution_semantics_reader import read_round_supervision_cycle

logger = logging.getLogger(__name__)


def _artifact_href(path: str) -> str:
    return f"/artifacts/{path}"


def _mission_route(
    mission_id: str,
    *,
    tab: str,
    round_id: int | None = None,
    packet_id: str | None = None,
) -> str:
    route = f"/?mission={mission_id}&mode=missions&tab={tab}"
    if round_id is not None:
        route += f"&round={round_id}"
    if packet_id:
        route += f"&packet={packet_id}"
    return route


def _source_label(path: str) -> str:
    suffix = Path(path).name
    if suffix == "activity.log":
        return "Activity log"
    if suffix == "events.jsonl":
        return "Events stream"
    if suffix == "incoming_events.jsonl":
        return "Incoming events"
    return suffix


def _artifact_label(path: str) -> str:
    suffix = Path(path).name
    if suffix == "supervisor_review.md":
        return "Supervisor review"
    if suffix == "visual_evaluation.json":
        return "Visual evaluation"
    return suffix


def _jump_targets_for_block(
    *,
    source_path: str | None = None,
    artifact_path: str | None = None,
    details: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    targets: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add_target(kind: str, label: str, path: str) -> None:
        key = (kind, path)
        if key in seen:
            return
        seen.add(key)
        targets.append(
            {
                "kind": kind,
                "label": label,
                "path": path,
                "href": _artifact_href(path),
            }
        )

    if source_path:
        add_target("source", _source_label(source_path), source_path)
    if artifact_path:
        add_target("artifact", _artifact_label(artifact_path), artifact_path)
    artifacts = details.get("artifacts") if isinstance(details, dict) else None
    if isinstance(artifacts, dict):
        for label, value in artifacts.items():
            if isinstance(value, str) and value:
                add_target("artifact", str(label), value)
    return targets


def _block_emphasis(
    block_type: str,
    event_type: str = "",
    details: dict[str, Any] | None = None,
) -> str:
    if block_type == "activity":
        return "log"
    if block_type == "message":
        return "narrative"
    if block_type == "tool":
        return "tool"
    if block_type == "command_burst":
        return "burst"
    if block_type == "supervisor":
        return "decision"
    if block_type == "visual_finding":
        return "alert"
    if block_type == "milestone":
        lowered = event_type.lower()
        if any(token in lowered for token in ("failed", "blocked", "paused", "cancel")):
            return "critical"
        return "milestone"
    if block_type == "event":
        return "event"
    return "neutral"


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
    milestone_count = 0
    tool_count = 0
    alert_count = 0
    for block in blocks:
        block_type = str(block.get("block_type", "event"))
        block_counts[block_type] = block_counts.get(block_type, 0) + 1
        if block_type == "milestone":
            milestone_count += 1
        if block_type in {"tool", "command_burst"}:
            tool_count += 1
        if block.get("emphasis") in {"alert", "critical"}:
            alert_count += 1

    operator_readout = (
        f"{milestone_count} milestones, {tool_count} tool blocks, "
        f"{alert_count} alerts, latest signal at {latest_timestamp or '—'}"
    )

    return {
        "mission_id": mission_id,
        "packet_id": packet_id,
        "entries": entries,
        "summary": {
            "entry_count": len(entries),
            "kind_counts": kind_counts,
            "block_counts": block_counts,
            "latest_timestamp": latest_timestamp,
            "operator_readout": operator_readout,
        },
        "milestones": milestones,
        "blocks": blocks,
        "telemetry": {
            "activity_log": (
                str(activity_path.relative_to(repo_root)) if activity_path.exists() else None
            ),
            "events": str(events_path.relative_to(repo_root)) if events_path.exists() else None,
            "incoming": (
                str(incoming_path.relative_to(repo_root)) if incoming_path.exists() else None
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
        source_path = entry.get("source_path")
        return {
            "block_type": "activity",
            "emphasis": _block_emphasis("activity"),
            "timestamp": str(entry.get("timestamp", "")),
            "title": message,
            "body": body,
            "source_path": source_path,
            "jump_targets": _jump_targets_for_block(source_path=source_path),
        }

    if kind == "incoming":
        source_path = entry.get("source_path")
        block = {
            "block_type": "message",
            "emphasis": _block_emphasis("message"),
            "timestamp": str(entry.get("timestamp", "")),
            "title": message,
            "body": event_type or kind,
            "source_path": source_path,
        }
        if details is not None:
            block["details"] = details
        block["jump_targets"] = _jump_targets_for_block(
            source_path=source_path,
            details=details,
        )
        return block

    if event_type.startswith("mission_packet_"):
        source_path = entry.get("source_path")
        block = {
            "block_type": "milestone",
            "emphasis": _block_emphasis("milestone", event_type, details),
            "timestamp": str(entry.get("timestamp", "")),
            "title": message,
            "body": event_type,
            "source_path": source_path,
        }
        if details is not None:
            block["details"] = details
        block["jump_targets"] = _jump_targets_for_block(
            source_path=source_path,
            details=details,
        )
        return block

    if "tool_call" in event_type:
        source_path = entry.get("source_path")
        block = {
            "block_type": "tool",
            "emphasis": _block_emphasis("tool"),
            "timestamp": str(entry.get("timestamp", "")),
            "title": message,
            "body": event_type,
            "source_path": source_path,
        }
        if details is not None:
            block["details"] = details
        block["jump_targets"] = _jump_targets_for_block(
            source_path=source_path,
            details=details,
        )
        return block

    source_path = entry.get("source_path")
    block = {
        "block_type": "event",
        "emphasis": _block_emphasis("event", event_type, details),
        "timestamp": str(entry.get("timestamp", "")),
        "title": message,
        "body": event_type or kind,
        "source_path": source_path,
    }
    if details is not None:
        block["details"] = details
    block["jump_targets"] = _jump_targets_for_block(
        source_path=source_path,
        details=details,
    )
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
                    "emphasis": _block_emphasis("command_burst"),
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
                    "jump_targets": _jump_targets_for_block(
                        source_path=current_tool_burst[0].get("source_path"),
                        details={
                            "artifacts": {
                                item.get("title", f"tool-{index}"): target.get("path")
                                for index, item in enumerate(current_tool_burst, start=1)
                                for target in item.get("jump_targets", [])
                                if target.get("kind") == "artifact" and target.get("path")
                            }
                        },
                    ),
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

    blocks: list[dict[str, Any]] = []
    for round_dir in sorted(rounds_dir.glob("round-*")):
        normalized = read_round_supervision_cycle(round_dir)
        if normalized is not None:
            summary = normalized.get("summary", {})
            if not isinstance(summary, dict):
                continue
            worker_results = summary.get("worker_results", [])
            if not isinstance(worker_results, list):
                worker_results = []
            if not any(
                isinstance(result, dict) and result.get("packet_id") == packet_id
                for result in worker_results
            ):
                continue
            decision = normalized.get("decision", {})
            if not isinstance(decision, dict):
                decision = {}
            artifacts = normalized.get("artifacts", {})

            timestamp = str(summary.get("completed_at") or summary.get("started_at") or "")
            if decision:
                review_artifact = artifacts.get("review_report")
                artifact_path = (
                    str(Path(review_artifact.path).relative_to(repo_root))
                    if review_artifact is not None
                    else str((round_dir / "supervisor_review.md").relative_to(repo_root))
                )
                round_id = summary.get("round_id")
                blocks.append(
                    {
                        "block_type": "supervisor",
                        "emphasis": _block_emphasis("supervisor"),
                        "timestamp": timestamp,
                        "title": decision.get("summary") or "Supervisor decision",
                        "body": decision.get("action", ""),
                        "artifact_path": artifact_path,
                        "review_route": _mission_route(
                            mission_id,
                            tab="approvals",
                            round_id=round_id if isinstance(round_id, int) else None,
                        ),
                        "details": {
                            "reason_code": decision.get("reason_code"),
                            "confidence": decision.get("confidence"),
                            "blocking_questions": decision.get("blocking_questions", []),
                        },
                        "jump_targets": _jump_targets_for_block(
                            artifact_path=artifact_path,
                        ),
                    }
                )

            visual_artifact = artifacts.get("visual_report")
            if visual_artifact is not None:
                visual_path = Path(visual_artifact.path)
                try:
                    payload = json.loads(visual_path.read_text(encoding="utf-8"))
                except (OSError, ValueError, json.JSONDecodeError):
                    continue
                if not isinstance(payload, dict):
                    continue
                round_id = summary.get("round_id")
                blocks.append(
                    {
                        "block_type": "visual_finding",
                        "emphasis": _block_emphasis("visual_finding"),
                        "timestamp": timestamp,
                        "title": payload.get("summary") or "Visual evaluation result",
                        "body": payload.get("evaluator", ""),
                        "artifact_path": str(visual_path.relative_to(repo_root)),
                        "review_route": _mission_route(
                            mission_id,
                            tab="visual",
                            round_id=round_id if isinstance(round_id, int) else None,
                        ),
                        "details": {
                            "confidence": payload.get("confidence"),
                            "findings": payload.get("findings"),
                            "artifacts": payload.get("artifacts"),
                        },
                        "jump_targets": _jump_targets_for_block(
                            artifact_path=str(visual_path.relative_to(repo_root)),
                            details={"artifacts": payload.get("artifacts")},
                        ),
                    }
                )
            continue

        from spec_orch.domain.models import RoundSummary, VisualEvaluationResult

        summary_path = round_dir / "round_summary.json"
        if not summary_path.exists():
            continue
        try:
            legacy_summary = RoundSummary.from_dict(json.loads(summary_path.read_text(encoding="utf-8")))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not any(result.get("packet_id") == packet_id for result in legacy_summary.worker_results):
            continue

        timestamp = legacy_summary.completed_at or legacy_summary.started_at or ""
        if legacy_summary.decision is not None:
            blocks.append(
                {
                    "block_type": "supervisor",
                    "emphasis": _block_emphasis("supervisor"),
                    "timestamp": timestamp,
                    "title": legacy_summary.decision.summary or "Supervisor decision",
                    "body": legacy_summary.decision.action.value,
                    "artifact_path": str(
                        (round_dir / "supervisor_review.md").relative_to(repo_root)
                    ),
                    "review_route": _mission_route(
                        mission_id,
                        tab="approvals",
                        round_id=legacy_summary.round_id,
                    ),
                    "details": {
                        "reason_code": legacy_summary.decision.reason_code,
                        "confidence": legacy_summary.decision.confidence,
                        "blocking_questions": legacy_summary.decision.blocking_questions,
                    },
                    "jump_targets": _jump_targets_for_block(
                        artifact_path=str(
                            (round_dir / "supervisor_review.md").relative_to(repo_root)
                        ),
                    ),
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
                    "emphasis": _block_emphasis("visual_finding"),
                    "timestamp": timestamp,
                    "title": visual.summary or "Visual evaluation result",
                    "body": visual.evaluator,
                    "artifact_path": str(visual_path.relative_to(repo_root)),
                    "review_route": _mission_route(
                        mission_id,
                        tab="visual",
                        round_id=legacy_summary.round_id,
                    ),
                    "details": {
                        "confidence": visual.confidence,
                        "findings": visual.findings,
                        "artifacts": visual.artifacts,
                    },
                    "jump_targets": _jump_targets_for_block(
                        artifact_path=str(visual_path.relative_to(repo_root)),
                        details={"artifacts": visual.artifacts},
                    ),
                }
            )

    return blocks


__all__ = [
    "_gather_packet_transcript",
    "_transcript_block_from_entry",
    "_group_transcript_blocks",
    "_gather_round_evidence_blocks",
]
