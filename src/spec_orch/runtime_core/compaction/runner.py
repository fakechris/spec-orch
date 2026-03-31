from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from spec_orch.runtime_core.compaction.models import (
    CompactionBoundary,
    CompactionInputSlice,
    CompactionRestoreBundle,
    CompactionResult,
    CompactionTriggerDecision,
)
from spec_orch.runtime_core.compaction.store import (
    append_compaction_boundary,
    write_last_compaction,
)
from spec_orch.runtime_core.compaction.telemetry import (
    emit_compaction_completed,
    emit_compaction_failed,
    emit_compaction_retry,
    emit_compaction_started,
)
from spec_orch.runtime_core.compaction.triggers import evaluate_compaction_policy


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


def evaluate_compaction_input(
    *,
    effective_context_window: int,
    reserved_output_budget: int,
    transcript_size: int,
    recent_growth: int = 0,
    posture: str = "standard",
    threshold: int | None = None,
) -> CompactionTriggerDecision:
    return evaluate_compaction_policy(
        CompactionInputSlice(
            effective_context_window=effective_context_window,
            reserved_output_budget=reserved_output_budget,
            transcript_size=transcript_size,
            recent_growth=recent_growth,
            posture=posture,
        ),
        threshold=threshold,
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
    max_retries: int = 1,
) -> dict[str, Any]:
    if not trigger.trigger:
        return {"triggered": False, "stats": {}}

    with _compaction_guard(root):
        emit_compaction_started(
            root,
            reason=trigger.reason,
            details={
                "threshold": trigger.threshold,
                "observed_count": trigger.observed_count,
                "posture": trigger.posture,
                "source_size": trigger.source_size,
                "effective_budget": trigger.effective_budget,
            },
        )
        boundary = CompactionBoundary(
            boundary_id=f"compact-{uuid.uuid4().hex[:12]}",
            trigger_reason=trigger.reason,
            restore_bundle=restore_bundle.to_dict(),
        )
        append_compaction_boundary(root, boundary)
        retries_used = 0
        fallback_used = ""
        compact_planner_config = dict(planner_config or {})
        compact_summarize = summarize
        while True:
            try:
                stats = memory_service.compact(
                    max_age_days=max_age_days,
                    summarize=compact_summarize,
                    planner_config=compact_planner_config or None,
                )
                break
            except Exception as exc:
                if retries_used < max_retries and _is_prompt_too_long(exc):
                    retries_used += 1
                    fallback_used = "smaller_source_slice"
                    compact_summarize = False
                    compact_planner_config["compaction_fallback"] = fallback_used
                    emit_compaction_retry(
                        root,
                        reason=trigger.reason,
                        details={
                            "error": str(exc),
                            "retries_used": retries_used,
                            "fallback_used": fallback_used,
                            "boundary": boundary.to_dict(),
                        },
                    )
                    continue
                failure = CompactionResult(
                    triggered=True,
                    boundary=boundary.to_dict(),
                    stats={},
                    restore_bundle=restore_bundle.to_dict(),
                    retries_used=retries_used,
                    fallback_used=fallback_used,
                    guard_state="failed",
                ).to_dict()
                failure["error"] = str(exc)
                write_last_compaction(root, failure)
                emit_compaction_failed(root, reason=trigger.reason, details=failure)
                raise
        payload = CompactionResult(
            triggered=True,
            boundary=boundary.to_dict(),
            stats=stats,
            restore_bundle=restore_bundle.to_dict(),
            retries_used=retries_used,
            fallback_used=fallback_used,
            guard_state="released",
        ).to_dict()
        write_last_compaction(root, payload)
        emit_compaction_completed(root, reason=trigger.reason, details=payload)
        return payload


@contextmanager
def _compaction_guard(root: Path):
    guard_path = Path(root) / "compaction.lock"
    guard_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with guard_path.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps({"created_at": uuid.uuid4().hex}, ensure_ascii=False))
            handle.flush()
    except FileExistsError as exc:
        raise RuntimeError("compaction recursion guard active") from exc
    try:
        yield
    finally:
        guard_path.unlink(missing_ok=True)


def _is_prompt_too_long(exc: Exception) -> bool:
    lowered = str(exc).lower()
    return "prompt too long" in lowered or "context length" in lowered
