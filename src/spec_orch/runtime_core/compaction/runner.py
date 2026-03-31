from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from spec_orch.runtime_core.compaction.models import (
    CompactionBoundary,
    CompactionRestoreBundle,
    CompactionTelemetryEvent,
    CompactionTriggerDecision,
)
from spec_orch.runtime_core.compaction.store import (
    append_compaction_boundary,
    append_compaction_event,
    write_last_compaction,
)


def evaluate_compaction_trigger(
    *,
    observed_count: int,
    threshold: int,
    posture: str = "standard",
) -> CompactionTriggerDecision:
    return CompactionTriggerDecision(
        trigger=observed_count >= threshold,
        reason="run_threshold_reached" if observed_count >= threshold else "below_threshold",
        threshold=threshold,
        observed_count=observed_count,
        posture=posture,
    )


def run_memory_compaction(
    *,
    root: Path,
    memory_service: Any,
    trigger: CompactionTriggerDecision,
    restore_bundle: CompactionRestoreBundle,
    planner_config: dict[str, Any] | None = None,
    max_age_days: int = 30,
    summarize: bool = True,
) -> dict[str, Any]:
    if not trigger.trigger:
        return {"triggered": False, "stats": {}}

    append_compaction_event(
        root,
        CompactionTelemetryEvent(
            phase="started",
            reason=trigger.reason,
            details={
                "threshold": trigger.threshold,
                "observed_count": trigger.observed_count,
                "posture": trigger.posture,
            },
        ),
    )
    boundary = CompactionBoundary(
        boundary_id=f"compact-{uuid.uuid4().hex[:12]}",
        trigger_reason=trigger.reason,
        restore_bundle=restore_bundle.to_dict(),
    )
    append_compaction_boundary(root, boundary)
    stats = memory_service.compact(
        max_age_days=max_age_days,
        summarize=summarize,
        planner_config=planner_config,
    )
    payload = {
        "triggered": True,
        "boundary": boundary.to_dict(),
        "stats": stats,
        "restore_bundle": restore_bundle.to_dict(),
    }
    write_last_compaction(root, payload)
    append_compaction_event(
        root,
        CompactionTelemetryEvent(
            phase="completed",
            reason=trigger.reason,
            details=payload,
        ),
    )
    return payload
