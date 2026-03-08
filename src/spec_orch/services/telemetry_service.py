from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


class TelemetryService:
    def telemetry_dir(self, workspace: Path) -> Path:
        path = workspace / "telemetry"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def new_run_id(self, issue_id: str) -> str:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        suffix = uuid4().hex[:8]
        return f"run_{issue_id}_{timestamp}_{suffix}"

    def log_event(
        self,
        *,
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
    ) -> Path:
        events_path = self.telemetry_dir(workspace) / "events.jsonl"
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "run_id": run_id,
            "issue_id": issue_id,
            "workspace": str(workspace),
            "component": component,
            "event_type": event_type,
            "severity": severity,
            "message": message,
            "adapter": adapter,
            "agent": agent,
            "data": data or {},
        }
        with events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")
        return events_path
