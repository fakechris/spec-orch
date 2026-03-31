from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from spec_orch.runtime_core.compaction.models import (
    CompactionBoundary,
    CompactionTelemetryEvent,
)
from spec_orch.services.io import atomic_write_json

COMPACTION_EVENTS_FILENAME = "compaction_events.jsonl"
COMPACTION_BOUNDARIES_FILENAME = "compaction_boundaries.jsonl"
LAST_COMPACTION_FILENAME = "last_compaction.json"


def append_compaction_event(root: Path, event: CompactionTelemetryEvent) -> Path:
    path = Path(root) / COMPACTION_EVENTS_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
    return path


def read_compaction_events(root: Path) -> list[CompactionTelemetryEvent]:
    path = Path(root) / COMPACTION_EVENTS_FILENAME
    if not path.exists():
        return []
    rows: list[CompactionTelemetryEvent] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(CompactionTelemetryEvent.from_dict(payload))
    return rows


def append_compaction_boundary(root: Path, boundary: CompactionBoundary) -> Path:
    path = Path(root) / COMPACTION_BOUNDARIES_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(boundary.to_dict(), ensure_ascii=False) + "\n")
    return path


def read_compaction_boundaries(root: Path) -> list[CompactionBoundary]:
    path = Path(root) / COMPACTION_BOUNDARIES_FILENAME
    if not path.exists():
        return []
    rows: list[CompactionBoundary] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(CompactionBoundary.from_dict(payload))
    return rows


def write_last_compaction(root: Path, payload: dict[str, Any]) -> Path:
    path = Path(root) / LAST_COMPACTION_FILENAME
    atomic_write_json(path, payload)
    return path


def read_last_compaction(root: Path) -> dict[str, Any] | None:
    path = Path(root) / LAST_COMPACTION_FILENAME
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None
