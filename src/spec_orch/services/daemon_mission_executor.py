from __future__ import annotations

from typing import Any

from spec_orch.services.linear_client import LinearClient


class DaemonMissionExecutor:
    """Executes a mission-backed issue after daemon polling has admitted it."""

    def execute(
        self,
        *,
        host: Any,
        issue_id: str,
        mission_id: str,
        raw_issue: dict[str, Any],
        client: LinearClient,
    ) -> None:
        from spec_orch.services.parallel_run_controller import ParallelRunController

        linear_uid = raw_issue.get("id", "")
        print(f"[daemon] processing {issue_id} (mission: {mission_id})")
        host._event_bus.emit_issue_state(issue_id, "building")

        try:
            host._sync_linear_mirror_for_mission(
                client=client,
                raw_issue=raw_issue,
                mission_id=mission_id,
            )
            try:
                plan = ParallelRunController.load_plan(mission_id, host.repo_root)
            except Exception as exc:
                plan = None
                print(f"[daemon] {issue_id}: wave preview unavailable: {exc}")

            if plan is not None:
                for wave in plan.waves:
                    if linear_uid:
                        try:
                            wave_msg = (
                                f"🔄 Wave {wave.wave_number}: "
                                f"{len(wave.work_packets)} packets — {wave.description}"
                            )
                            client.add_comment(linear_uid, wave_msg)
                        except Exception as exc:
                            print(f"[daemon] wave comment failed: {exc}")

            execution_result = host._get_mission_execution_service().execute_mission(
                mission_id=mission_id,
                initial_round=0,
                plan=plan,
            )
            summary = execution_result.summary_markdown
            succeeded = execution_result.completed

            if execution_result.paused:
                host._event_bus.emit_issue_state(issue_id, "paused", mergeable=False)
                print(f"[daemon] {issue_id}: mission paused for human input")
                if linear_uid:
                    try:
                        client.add_comment(
                            linear_uid,
                            "Mission execution paused. Review the latest "
                            "`round_decision.json` and `supervisor_review.md` before resuming.",
                        )
                    except Exception as exc:
                        print(f"[daemon] pause comment failed: {exc}")
                return

            if linear_uid:
                try:
                    client.add_comment(linear_uid, summary)
                except Exception as exc:
                    print(f"[daemon] summary comment failed: {exc}")

            if succeeded:
                host._event_bus.emit_issue_state(issue_id, "completed", mergeable=True)
                print(f"[daemon] {issue_id}: mission succeeded")
                if linear_uid:
                    try:
                        client.update_issue_state(linear_uid, "In Review")
                    except Exception as exc:
                        print(f"[daemon] state update failed: {exc}")
                host._processed.add(issue_id)
            else:
                host._event_bus.emit_issue_state(issue_id, "completed", mergeable=False)
                print(f"[daemon] {issue_id}: mission failed")
                if linear_uid:
                    try:
                        client.update_issue_state(linear_uid, "Ready")
                        print(f"[daemon] {issue_id} → Ready (for retry)")
                    except Exception as exc:
                        print(f"[daemon] state reset failed: {exc}")
                host._release(issue_id)

        except FileNotFoundError as exc:
            print(f"[daemon] {issue_id}: plan not found: {exc}")
            host._event_bus.emit_issue_state(issue_id, "completed", mergeable=False)
            if linear_uid:
                try:
                    client.update_issue_state(linear_uid, "Ready")
                except Exception as state_exc:
                    print(f"[daemon] state reset failed: {state_exc}")
            host._release(issue_id)
        except Exception as exc:
            print(f"[daemon] {issue_id}: mission execution failed: {exc}")
            host._event_bus.emit_issue_state(issue_id, "completed", mergeable=False)
            if linear_uid:
                try:
                    client.update_issue_state(linear_uid, "Ready")
                except Exception as state_exc:
                    print(f"[daemon] state reset failed: {state_exc}")
            host._release(issue_id)
