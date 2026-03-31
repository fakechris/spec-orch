from __future__ import annotations

from spec_orch.runtime_core.observability.models import (
    RuntimeBatchSummary,
    RuntimeStallSignal,
    RuntimeStepSummary,
)


def derive_stall_signal(
    *,
    repeated_steps: int,
    idle_seconds: int,
    low_yield: bool = False,
) -> RuntimeStallSignal:
    stalled = idle_seconds >= 60 or repeated_steps >= 3
    diminishing = low_yield or repeated_steps >= 2
    reason = ""
    if idle_seconds >= 60:
        reason = "idle_timeout"
    elif repeated_steps >= 3:
        reason = "repeated_step_loop"
    elif diminishing:
        reason = "diminishing_returns"
    return RuntimeStallSignal(
        stalled=stalled,
        idle_seconds=idle_seconds,
        reason=reason,
        diminishing_returns=diminishing,
        repeated_steps=repeated_steps,
    )


def build_step_summary(
    *,
    subject_key: str,
    step_key: str,
    summary: str,
    artifact_refs: dict[str, str] | None = None,
    updated_at: str = "",
) -> RuntimeStepSummary:
    return RuntimeStepSummary(
        subject_key=subject_key,
        step_key=step_key,
        summary=summary,
        artifact_refs=dict(artifact_refs or {}),
        updated_at=updated_at,
    )


def build_batch_summary(
    *,
    subject_key: str,
    batch_key: str,
    steps: list[str],
    summary: str,
    artifact_refs: dict[str, str] | None = None,
    updated_at: str = "",
) -> RuntimeBatchSummary:
    return RuntimeBatchSummary(
        subject_key=subject_key,
        batch_key=batch_key,
        steps=list(steps),
        summary=summary,
        artifact_refs=dict(artifact_refs or {}),
        updated_at=updated_at,
    )


__all__ = ["build_batch_summary", "build_step_summary", "derive_stall_signal"]
