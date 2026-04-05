from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from spec_orch.services.activity_logger import ActivityLogger
from spec_orch.services.telemetry_service import TelemetryService


class RuntimeEventPublisher:
    def __init__(self, telemetry_service: TelemetryService) -> None:
        self._telemetry = telemetry_service

    def make_callback(
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
            self.publish(
                activity_logger=None,
                workspace=workspace,
                run_id=run_id,
                issue_id=issue_id,
                component=str(event.get("component", "builder")),
                event_type=str(ev_type),
                severity=str(event.get("severity", "info")),
                message=str(msg) if msg else f"event:{ev_type}",
                adapter=event.get("adapter"),
                agent=event.get("agent"),
                data=event.get("data"),
            )
            if activity_logger:
                activity_logger.log(event.get("data", event))

        return _log

    def publish(
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
        data: dict[str, Any] | None = None,
    ) -> None:
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
