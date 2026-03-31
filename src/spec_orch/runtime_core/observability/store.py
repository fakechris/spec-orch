from __future__ import annotations

import json
from pathlib import Path

from spec_orch.runtime_core.observability.models import (
    RuntimeBatchSummary,
    RuntimeLiveSummary,
    RuntimeProgressEvent,
    RuntimeRecap,
    RuntimeStepSummary,
)
from spec_orch.services.io import atomic_write_json

PROGRESS_EVENTS_FILENAME = "progress_events.jsonl"
LIVE_SUMMARY_FILENAME = "live_summary.json"
RECAPS_FILENAME = "recaps.jsonl"
STEP_SUMMARIES_FILENAME = "step_summaries.jsonl"
BATCH_SUMMARIES_FILENAME = "batch_summaries.jsonl"


def append_progress_event(root: Path, event: RuntimeProgressEvent) -> Path:
    path = Path(root) / PROGRESS_EVENTS_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
    return path


def read_progress_events(root: Path) -> list[RuntimeProgressEvent]:
    path = Path(root) / PROGRESS_EVENTS_FILENAME
    if not path.exists():
        return []
    events: list[RuntimeProgressEvent] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            events.append(RuntimeProgressEvent.from_dict(payload))
    return events


def write_live_summary(root: Path, summary: RuntimeLiveSummary) -> Path:
    path = Path(root) / LIVE_SUMMARY_FILENAME
    atomic_write_json(path, summary.to_dict())
    return path


def read_live_summary(root: Path) -> RuntimeLiveSummary | None:
    path = Path(root) / LIVE_SUMMARY_FILENAME
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    return RuntimeLiveSummary.from_dict(payload)


def append_recap(root: Path, recap: RuntimeRecap) -> Path:
    path = Path(root) / RECAPS_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(recap.to_dict(), ensure_ascii=False) + "\n")
    return path


def append_step_summary(root: Path, summary: RuntimeStepSummary) -> Path:
    path = Path(root) / STEP_SUMMARIES_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(summary.to_dict(), ensure_ascii=False) + "\n")
    return path


def read_step_summaries(root: Path) -> list[RuntimeStepSummary]:
    path = Path(root) / STEP_SUMMARIES_FILENAME
    if not path.exists():
        return []
    rows: list[RuntimeStepSummary] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(RuntimeStepSummary.from_dict(payload))
    return rows


def append_batch_summary(root: Path, summary: RuntimeBatchSummary) -> Path:
    path = Path(root) / BATCH_SUMMARIES_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(summary.to_dict(), ensure_ascii=False) + "\n")
    return path


def read_batch_summaries(root: Path) -> list[RuntimeBatchSummary]:
    path = Path(root) / BATCH_SUMMARIES_FILENAME
    if not path.exists():
        return []
    rows: list[RuntimeBatchSummary] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(RuntimeBatchSummary.from_dict(payload))
    return rows


def read_recaps(root: Path) -> list[RuntimeRecap]:
    path = Path(root) / RECAPS_FILENAME
    if not path.exists():
        return []
    recaps: list[RuntimeRecap] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            recaps.append(RuntimeRecap.from_dict(payload))
    return recaps


__all__ = [
    "LIVE_SUMMARY_FILENAME",
    "PROGRESS_EVENTS_FILENAME",
    "RECAPS_FILENAME",
    "STEP_SUMMARIES_FILENAME",
    "BATCH_SUMMARIES_FILENAME",
    "append_batch_summary",
    "append_progress_event",
    "append_recap",
    "append_step_summary",
    "read_batch_summaries",
    "read_live_summary",
    "read_progress_events",
    "read_recaps",
    "read_step_summaries",
    "write_live_summary",
]
