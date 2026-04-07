from __future__ import annotations

import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import TYPE_CHECKING, Any

from spec_orch.services.admission_governor import AdmissionGovernor
from spec_orch.services.daemon_executor import DaemonExecutor
from spec_orch.services.daemon_state_store import DaemonStateStore
from spec_orch.services.linear_client import LinearClient
from spec_orch.services.run_controller import RunController

if TYPE_CHECKING:
    from spec_orch.services.daemon import _DaemonSharedState


class DaemonIssueDispatcher:
    """Owns issue polling, filtering, hotfix prioritization, enqueue, and drain logic.

    Manages the ThreadPoolExecutor submission and future tracking that were
    previously inline in SpecOrchDaemon.
    """

    def __init__(
        self,
        *,
        config: Any,
        state_store: DaemonStateStore,
        admission_governor: AdmissionGovernor,
        daemon_executor: DaemonExecutor,
        executor_pool: ThreadPoolExecutor,
        state_lock: threading.Lock,
        shared_state: _DaemonSharedState,
        # Host reference for callbacks the executor needs
        host: Any,
        process_lock_owner: str,
    ) -> None:
        self._config = config
        self._state_store = state_store
        self._admission_governor = admission_governor
        self._daemon_executor = daemon_executor
        self._executor_pool = executor_pool
        self._state_lock = state_lock
        self._shared = shared_state
        self._host = host
        self._process_lock_owner = process_lock_owner
        self._execution_futures: dict[str, Future[None]] = {}

    # -- public API called from daemon.run() --

    def poll_and_dispatch(self, client: LinearClient, controller: RunController) -> None:
        """Poll for new issues and dispatch them to the executor pool."""
        self._poll_and_enqueue(client, controller)
        self._drain_execution_queue(client, controller)

    def reap_completed_futures(self) -> None:
        """Harvest finished execution futures and log any unhandled errors."""
        done_ids = [issue_id for issue_id, fut in self._execution_futures.items() if fut.done()]
        for issue_id in done_ids:
            fut = self._execution_futures.pop(issue_id)
            exc = fut.exception()
            with self._state_lock:
                self._shared.in_progress.discard(issue_id)
            if exc is not None:
                print(f"[daemon] executor future for {issue_id} raised: {exc}")
                self._host._emit_error_event(
                    "daemon.executor_future_error",
                    str(exc),
                    issue_id=issue_id,
                )

    # -- internal --

    def _poll_and_enqueue(self, client: LinearClient, controller: RunController) -> None:
        try:
            issues = client.list_issues(
                team_key=self._config.team_key,
                assigned_to_me=self._config.issue_filter == "assigned_to_me",
                filter_state=self._config.consume_state,
                filter_labels=self._config.require_labels or None,
                exclude_labels=self._config.exclude_labels or None,
                exclude_parents=self._config.skip_parents,
            )
        except Exception as exc:
            print(f"[daemon] poll error: {exc}")
            return

        sorted_issues = sorted(
            issues,
            key=lambda i: 0 if self._is_hotfix(i) else 1,
        )
        projected_in_progress = len(self._shared.in_progress) + len(
            self._state_store.list_execution_intents()
        )
        for raw_issue in sorted_issues:
            issue_id = raw_issue.get("identifier", "")
            linear_uid = raw_issue.get("id", "")
            if not issue_id or issue_id in self._shared.processed:
                continue
            if issue_id in self._shared.dead_letter:
                continue
            if self._is_locked(issue_id):
                continue
            if self._should_backoff(issue_id):
                continue

            is_hotfix = self._is_hotfix(raw_issue)
            admission_decision = self._admission_governor.evaluate_issue(
                issue_id,
                in_progress_count=projected_in_progress,
                is_hotfix=is_hotfix,
                recorded_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            )
            self._admission_governor.record_decision(admission_decision)
            if admission_decision["decision"] != "admit":
                continue

            try:
                self._claim(issue_id)
            except RuntimeError:
                continue

            if not is_hotfix and not self._host._triage_issue(client, raw_issue, controller):
                self._release(issue_id)
                continue

            if linear_uid:
                try:
                    client.update_issue_state(linear_uid, "In Progress")
                except Exception as exc:
                    print(f"[daemon] state->InProgress failed: {exc}")

            self._enqueue_execution_intent(
                issue_id=issue_id,
                raw_issue=raw_issue,
                is_hotfix=is_hotfix,
            )
            projected_in_progress += 1

    def _enqueue_execution_intent(
        self,
        *,
        issue_id: str,
        raw_issue: dict[str, Any],
        is_hotfix: bool,
    ) -> None:
        self._state_store.enqueue_execution_intent(
            issue_id=issue_id,
            raw_issue=raw_issue,
            is_hotfix=is_hotfix,
        )

    def _drain_execution_queue(self, client: LinearClient, controller: RunController) -> None:
        """Pop all admitted intents and submit to the thread pool."""
        while True:
            intent = self._state_store.pop_next_execution_intent()
            if intent is None:
                break
            issue_id = str(intent.get("issue_id", "")).strip()
            raw_issue = intent.get("raw_issue")
            if not issue_id or not isinstance(raw_issue, dict):
                continue
            with self._state_lock:
                self._shared.in_progress.add(issue_id)
            try:
                future = self._executor_pool.submit(
                    self._daemon_executor.dispatch,
                    host=self._host,
                    issue_id=issue_id,
                    raw_issue=raw_issue,
                    client=client,
                    controller=controller,
                    is_hotfix=bool(intent.get("is_hotfix", False)),
                )
                self._execution_futures[issue_id] = future
            except Exception as exc:
                print(f"[daemon] submit failed for {issue_id}: {exc}")
                with self._state_lock:
                    self._shared.in_progress.discard(issue_id)
                self._host._emit_error_event(
                    "daemon.submit_failed",
                    str(exc),
                    issue_id=issue_id,
                )

    def _is_hotfix(self, raw_issue: dict[str, Any]) -> bool:
        labels = raw_issue.get("labels", {}).get("nodes", [])
        issue_labels = {lbl.get("name", "").lower() for lbl in labels}
        return bool(issue_labels & {h.lower() for h in self._config.hotfix_labels})

    def _should_backoff(self, issue_id: str) -> bool:
        count = self._shared.retry_counts.get(issue_id, 0)
        if count == 0:
            return False
        retry_at = self._shared.retry_at.get(issue_id)
        if retry_at is None:
            return False
        return time.time() < retry_at

    def _is_locked(self, issue_id: str) -> bool:
        return self._state_store.issue_is_claimed(issue_id)

    def _claim(self, issue_id: str) -> None:
        from spec_orch.services.daemon import SpecOrchDaemon

        claimed = self._state_store.try_claim_issue(
            issue_id,
            owner=self._process_lock_owner,
            lease_seconds=SpecOrchDaemon.ISSUE_CLAIM_LEASE_SECONDS,
        )
        if not claimed:
            raise RuntimeError(f"issue already claimed: {issue_id}")

    def _release(self, issue_id: str) -> None:
        self._state_store.release_issue_claim(issue_id)
