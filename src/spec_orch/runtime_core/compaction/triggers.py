from __future__ import annotations

from spec_orch.runtime_core.compaction.models import (
    CompactionInputSlice,
    CompactionTriggerDecision,
)


def evaluate_compaction_policy(
    slice_: CompactionInputSlice,
    *,
    threshold: int | None = None,
) -> CompactionTriggerDecision:
    effective_budget = max(
        0,
        slice_.effective_context_window - slice_.reserved_output_budget,
    )
    trigger_threshold = threshold if threshold is not None else max(1, int(effective_budget * 0.8))
    should_trigger = slice_.transcript_size >= trigger_threshold or slice_.recent_growth >= max(
        1, int(trigger_threshold * 0.15)
    )
    reason = "budget_pressure" if should_trigger else "below_threshold"
    if should_trigger and slice_.recent_growth >= max(1, int(trigger_threshold * 0.15)):
        reason = "growth_pressure"
    return CompactionTriggerDecision(
        trigger=should_trigger,
        reason=reason,
        threshold=trigger_threshold,
        observed_count=slice_.transcript_size,
        posture=slice_.posture,
        source_size=slice_.transcript_size,
        effective_budget=effective_budget,
    )


__all__ = ["evaluate_compaction_policy"]
