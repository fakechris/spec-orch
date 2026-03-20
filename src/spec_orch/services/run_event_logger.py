"""Extracted event-logging and telemetry concerns from RunController."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import IO, Any

from spec_orch.domain.models import (
    BuilderResult,
    GateVerdict,
    VerificationSummary,
)
from spec_orch.services.activity_logger import ActivityLogger
from spec_orch.services.telemetry_service import TelemetryService
from spec_orch.services.trace_sampler import TraceSampler

logger = logging.getLogger(__name__)


class RunEventLogger:
    """Encapsulates all event-emission, telemetry, and eval-sampling logic."""

    def __init__(
        self,
        telemetry_service: TelemetryService,
        live_stream: IO[str] | None = None,
        trace_sampler: TraceSampler | None = None,
    ) -> None:
        self._telemetry = telemetry_service
        self._live_stream = live_stream
        self._trace_sampler = trace_sampler or TraceSampler()

    def open_activity_logger(self, workspace: Path) -> ActivityLogger:
        return ActivityLogger(
            ActivityLogger.activity_log_path(workspace),
            live_stream=self._live_stream,
        )

    def make_event_logger(
        self,
        *,
        workspace: Path,
        run_id: str,
        issue_id: str,
        activity_logger: ActivityLogger | None = None,
    ) -> Callable[[dict[str, Any]], None]:
        def _log(event: dict[str, Any]) -> None:
            ev_type = event.get("event_type") or event.get("type") or event.get("method", "unknown")
            msg = event.get("message") or event.get("text", "")
            if not msg:
                params = event.get("params", {})
                msg = params.get("text", "") if isinstance(params, dict) else ""
            self._telemetry.log_event(
                workspace=workspace,
                run_id=run_id,
                issue_id=issue_id,
                component=event.get("component", "builder"),
                event_type=str(ev_type),
                severity=event.get("severity", "info"),
                message=str(msg) if msg else f"event:{ev_type}",
                adapter=event.get("adapter"),
                agent=event.get("agent"),
                data=event.get("data"),
            )
            if activity_logger:
                activity_logger.log(event.get("data", event))

        return _log

    def log_and_emit(
        self,
        *,
        activity_logger: ActivityLogger | None = None,
        workspace: Path,
        run_id: str,
        issue_id: str,
        component: str,
        event_type: str,
        severity: str = "info",
        message: str,
        adapter: str | None = None,
        agent: str | None = None,
        data: dict | None = None,
    ) -> None:
        """Log to telemetry and forward to the activity logger."""
        self._telemetry.log_event(
            workspace=workspace,
            run_id=run_id,
            issue_id=issue_id,
            component=component,
            event_type=event_type,
            severity=severity,
            message=message,
            adapter=adapter,
            agent=agent,
            data=data,
        )
        if activity_logger:
            activity_logger.log(
                {
                    "event_type": event_type,
                    "component": component,
                    "message": message,
                    "data": data or {},
                }
            )

    def log_verification_events(
        self,
        *,
        workspace: Path,
        issue_id: str,
        run_id: str,
        verification: VerificationSummary,
        activity_logger: ActivityLogger | None = None,
    ) -> None:
        for step_name, detail in verification.details.items():
            self.log_and_emit(
                activity_logger=activity_logger,
                workspace=workspace,
                run_id=run_id,
                issue_id=issue_id,
                component="verification",
                event_type="verification_step_completed",
                severity="info" if detail.exit_code == 0 else "error",
                message=f"Verification step completed: {step_name}",
                data={
                    "step": step_name,
                    "exit_code": detail.exit_code,
                    "command": detail.command,
                },
            )

        self.log_and_emit(
            activity_logger=activity_logger,
            workspace=workspace,
            run_id=run_id,
            issue_id=issue_id,
            component="verification",
            event_type="verification_completed",
            severity="info" if verification.all_passed else "warning",
            message="Completed verification steps.",
            data={"all_passed": verification.all_passed},
        )

    def log_gate_event(
        self,
        *,
        workspace: Path,
        issue_id: str,
        run_id: str,
        gate: GateVerdict,
        activity_logger: ActivityLogger | None = None,
    ) -> None:
        self.log_and_emit(
            activity_logger=activity_logger,
            workspace=workspace,
            run_id=run_id,
            issue_id=issue_id,
            component="gate",
            event_type="gate_evaluated",
            severity="info" if gate.mergeable else "warning",
            message="Evaluated gate verdict.",
            data={
                "mergeable": gate.mergeable,
                "failed_conditions": gate.failed_conditions,
            },
        )

    def maybe_sample_for_eval(
        self,
        *,
        run_id: str,
        gate: GateVerdict,
        builder: BuilderResult,
        issue_id: str,
    ) -> None:
        """Use TraceSampler to decide if this run should be queued for eval."""
        token_count = builder.metadata.get("token_count", 0)
        has_negative = not gate.mergeable
        should, reason = self._trace_sampler.should_sample(
            run_id=run_id,
            token_count=token_count,
            has_negative_feedback=has_negative,
            verdict="pass" if gate.mergeable else "fail",
        )
        if should:
            logger.info("Run %s sampled for eval: %s", run_id, reason)
            try:
                from spec_orch.services.event_bus import get_event_bus

                get_event_bus().emit_eval_sample(run_id=run_id, reason=reason, issue_id=issue_id)
            except Exception:
                logger.debug("Failed to emit eval sample event", exc_info=True)

    @staticmethod
    def emit_fallback(
        component: str,
        primary: str,
        fallback: str,
        reason: str,
        issue_id: str = "",
    ) -> None:
        from spec_orch.services.event_bus import emit_fallback_safe

        emit_fallback_safe(
            component=component,
            primary=primary,
            fallback=fallback,
            reason=reason,
            issue_id=issue_id,
        )
