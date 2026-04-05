from __future__ import annotations

from typing import Any

from spec_orch.services.linear_client import LinearClient
from spec_orch.services.run_controller import RunController


class DaemonExecutor:
    """Runs admitted work after daemon polling/triage has selected an issue."""

    def dispatch(
        self,
        *,
        host: Any,
        issue_id: str,
        raw_issue: dict[str, Any],
        client: LinearClient,
        controller: RunController,
        is_hotfix: bool,
    ) -> None:
        mission_id = host._detect_mission(issue_id, raw_issue)
        if mission_id:
            host._execute_mission(
                issue_id,
                mission_id,
                raw_issue,
                client,
            )
            return
        host._execute_single(
            issue_id,
            raw_issue,
            client,
            controller,
            is_hotfix=is_hotfix,
        )
