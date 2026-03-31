from __future__ import annotations

from pathlib import Path
from typing import Any

from spec_orch.runtime_core.compaction.models import CompactionTelemetryEvent
from spec_orch.runtime_core.compaction.store import append_compaction_event


def emit_compaction_started(root: Path, *, reason: str, details: dict[str, Any]) -> None:
    append_compaction_event(
        root,
        CompactionTelemetryEvent(phase="started", reason=reason, details=details),
    )


def emit_compaction_retry(root: Path, *, reason: str, details: dict[str, Any]) -> None:
    append_compaction_event(
        root,
        CompactionTelemetryEvent(phase="retrying", reason=reason, details=details),
    )


def emit_compaction_failed(root: Path, *, reason: str, details: dict[str, Any]) -> None:
    append_compaction_event(
        root,
        CompactionTelemetryEvent(phase="failed", reason=reason, details=details),
    )


def emit_compaction_completed(root: Path, *, reason: str, details: dict[str, Any]) -> None:
    append_compaction_event(
        root,
        CompactionTelemetryEvent(phase="completed", reason=reason, details=details),
    )


__all__ = [
    "emit_compaction_completed",
    "emit_compaction_failed",
    "emit_compaction_retry",
    "emit_compaction_started",
]
