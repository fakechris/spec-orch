from __future__ import annotations

from typing import Any

from spec_orch.services.daemon_mission_executor import DaemonMissionExecutor
from spec_orch.services.daemon_single_issue_executor import DaemonSingleIssueExecutor
from spec_orch.services.linear_client import LinearClient
from spec_orch.services.run_controller import RunController


class DaemonExecutor:
    """Runs admitted work after daemon polling/triage has selected an issue."""

    def __init__(self) -> None:
        self._single_issue_executor = DaemonSingleIssueExecutor()
        self._mission_executor = DaemonMissionExecutor()

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
            self._mission_executor.execute(
                host=host,
                issue_id=issue_id,
                mission_id=mission_id,
                raw_issue=raw_issue,
                client=client,
            )
            return
        self._single_issue_executor.execute(
            host=host,
            issue_id=issue_id,
            raw_issue=raw_issue,
            client=client,
            controller=controller,
            is_hotfix=is_hotfix,
        )
