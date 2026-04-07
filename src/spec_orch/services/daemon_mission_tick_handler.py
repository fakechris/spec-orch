from __future__ import annotations

from typing import Any


class DaemonMissionTickHandler:
    """Advance mission lifecycles on each daemon tick.

    Owns _tick_missions(), _find_mission_for_issue(), and handle_btw().
    Takes a MissionLifecycleManager as its primary dependency.
    """

    def __init__(
        self,
        *,
        repo_root: Any,
        lifecycle_manager: Any,
    ) -> None:
        self._repo_root = repo_root
        self._lifecycle_manager = lifecycle_manager

    def tick(self) -> None:
        """Advance mission lifecycles on each daemon tick."""
        try:
            from spec_orch.services.mission_service import MissionService

            ms = MissionService(self._repo_root)
            missions = ms.list_missions()
        except Exception as exc:
            print(f"[daemon] mission tick error: {exc}")
            return

        for mission in missions:
            if mission.status.value not in ("approved", "in_progress"):
                continue

            state = self._lifecycle_manager.get_state(mission.mission_id)
            if state is None:
                print(f"[daemon] tracking mission {mission.mission_id}")
                self._lifecycle_manager.begin_tracking(mission.mission_id)

            try:
                self._lifecycle_manager.auto_advance(mission.mission_id)
            except Exception as exc:
                print(f"[daemon] mission {mission.mission_id} advance error: {exc}")

    def find_mission_for_issue(self, issue_id: str) -> str | None:
        """Return the mission_id that owns *issue_id*, if any."""
        for mid, state in self._lifecycle_manager.all_states().items():
            if issue_id in state.issue_ids and issue_id not in state.completed_issues:
                return str(mid)
        return None

    def handle_btw(self, issue_id: str, message: str, channel: str) -> bool:
        """Inject /btw context into a running issue via the lifecycle manager."""
        return bool(self._lifecycle_manager.inject_btw(issue_id, message, channel))
