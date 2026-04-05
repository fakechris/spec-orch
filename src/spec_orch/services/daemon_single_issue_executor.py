from __future__ import annotations

from typing import Any

from spec_orch.domain.models import TERMINAL_STATES, RunState
from spec_orch.services.linear_client import LinearClient
from spec_orch.services.run_controller import RunController


class DaemonSingleIssueExecutor:
    """Executes a single Linear issue through the standard pipeline."""

    def execute(
        self,
        *,
        host: Any,
        issue_id: str,
        raw_issue: dict[str, Any],
        client: LinearClient,
        controller: RunController,
        is_hotfix: bool,
    ) -> None:
        from spec_orch.domain.models import FlowType

        linear_uid = raw_issue.get("id", "")
        flow_type = FlowType.HOTFIX if is_hotfix else None
        label = "hotfix" if is_hotfix else "single issue"
        print(f"[daemon] processing {issue_id} ({label} pipeline)")
        host._in_progress.add(issue_id)
        host._save_state()
        host._event_bus.emit_issue_state(issue_id, "building")
        try:
            result = controller.advance_to_completion(issue_id, flow_type=flow_type)
            state = result.state
            mergeable = result.gate.mergeable
            blocked = ",".join(result.gate.failed_conditions) or "none"
            print(
                f"[daemon] {issue_id}: state={state.value} mergeable={mergeable} blocked={blocked}"
            )
            if state in TERMINAL_STATES or state == RunState.GATE_EVALUATED:
                host._event_bus.emit_issue_state(issue_id, "completed", mergeable=mergeable)
                mission_id = host._find_mission_for_issue(issue_id)
                if mission_id:
                    host._lifecycle_manager.mark_issue_done(mission_id, issue_id)

                host._notify(issue_id, mergeable)
                pr_created = host._auto_create_pr(issue_id, result)

                gate_policy = host._load_gate_policy_for("hotfix" if is_hotfix else "daemon")
                auto_merged = pr_created and gate_policy.auto_merge and mergeable

                if pr_created and linear_uid:
                    try:
                        target_state = "Done" if auto_merged else "In Review"
                        client.update_issue_state(linear_uid, target_state)
                        print(f"[daemon] {issue_id} → {target_state}")
                    except Exception as exc:
                        print(f"[daemon] state update failed: {exc}")
                host._write_back_result(raw_issue, result)
                host._processed.add(issue_id)
                host._in_progress.discard(issue_id)
                host._retry_counts.pop(issue_id, None)
            else:
                host._in_progress.discard(issue_id)
                host._release(issue_id)
        except Exception as exc:
            print(f"[daemon] {issue_id} failed: {exc}")
            host._in_progress.discard(issue_id)
            host._record_failure(issue_id, str(exc), client, linear_uid)
            host._release(issue_id)
