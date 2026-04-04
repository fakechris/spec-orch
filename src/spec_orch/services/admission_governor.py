from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from spec_orch.domain.operator_semantics import (
    AdmissionDecision,
    PressureSignal,
    QueueEntry,
    ResourceBudget,
)

_DAEMON_BUDGET_KEY = "daemon:max_concurrent"
_MISSION_BUDGET_KEY = "mission:max_concurrent"
_WORKER_BUDGET_KEY = "worker:max_concurrent"
_VERIFIER_BUDGET_KEY = "verifier:max_concurrent"
_QUEUE_NAME = "daemon_admission"


def _budget_state(*, current_count: int, limit: int) -> str:
    if current_count >= limit:
        return "saturated"
    if current_count + 1 >= limit:
        return "constrained"
    return "healthy"


def _budget_scope(
    *,
    runtime_role: str,
    budget_key: str,
    current_count: int,
    limit: int,
    reason: str = "",
) -> dict[str, Any]:
    safe_limit = max(1, int(limit))
    safe_count = max(0, int(current_count))
    return {
        "runtime_role": runtime_role,
        "budget_key": budget_key,
        "current_count": safe_count,
        "limit": safe_limit,
        "remaining": max(safe_limit - safe_count, 0),
        "budget_state": _budget_state(current_count=safe_count, limit=safe_limit),
        "reason": reason,
    }


def _read_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


class AdmissionGovernor:
    def __init__(
        self,
        repo_root: Path,
        *,
        max_concurrent: int,
        mission_max_concurrent: int | None = None,
        worker_max_concurrent: int | None = None,
        verifier_max_concurrent: int | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.max_concurrent = max(1, int(max_concurrent))
        self.mission_max_concurrent = max(
            1,
            int(mission_max_concurrent if mission_max_concurrent is not None else max_concurrent),
        )
        self.worker_max_concurrent = max(
            1,
            int(worker_max_concurrent if worker_max_concurrent is not None else max_concurrent),
        )
        self.verifier_max_concurrent = max(
            1,
            int(
                verifier_max_concurrent
                if verifier_max_concurrent is not None
                else max(1, self.max_concurrent - 1)
            ),
        )
        self._decisions_path = self.repo_root / ".spec_orch" / "admission" / "decisions.jsonl"

    def evaluate_issue(
        self,
        issue_id: str,
        *,
        workspace_id: str | None = None,
        in_progress_count: int,
        mission_in_progress_count: int | None = None,
        worker_in_progress_count: int | None = None,
        verifier_in_progress_count: int | None = None,
        is_hotfix: bool,
        recorded_at: str,
    ) -> dict[str, Any]:
        current_in_progress = max(0, int(in_progress_count))
        current_mission_count = max(
            0,
            int(
                mission_in_progress_count
                if mission_in_progress_count is not None
                else current_in_progress
            ),
        )
        current_worker_count = max(
            0,
            int(
                worker_in_progress_count
                if worker_in_progress_count is not None
                else current_in_progress
            ),
        )
        current_verifier_count = max(
            0,
            int(
                verifier_in_progress_count
                if verifier_in_progress_count is not None
                else current_in_progress
            ),
        )
        decision = "admit"
        granted_budgets = [
            _DAEMON_BUDGET_KEY,
            _MISSION_BUDGET_KEY,
            _WORKER_BUDGET_KEY,
            _VERIFIER_BUDGET_KEY,
        ]
        queue_position: int | None = None
        pressure_reason = ""
        degrade_reason = ""
        budget_scopes = [
            _budget_scope(
                runtime_role="daemon",
                budget_key=_DAEMON_BUDGET_KEY,
                current_count=current_in_progress,
                limit=self.max_concurrent,
            ),
            _budget_scope(
                runtime_role="mission",
                budget_key=_MISSION_BUDGET_KEY,
                current_count=current_mission_count,
                limit=self.mission_max_concurrent,
            ),
            _budget_scope(
                runtime_role="worker",
                budget_key=_WORKER_BUDGET_KEY,
                current_count=current_worker_count,
                limit=self.worker_max_concurrent,
            ),
            _budget_scope(
                runtime_role="verifier",
                budget_key=_VERIFIER_BUDGET_KEY,
                current_count=current_verifier_count,
                limit=self.verifier_max_concurrent,
            ),
        ]
        if not is_hotfix and current_in_progress >= self.max_concurrent:
            decision = "defer"
            granted_budgets = []
            queue_position = current_in_progress + 1
            pressure_reason = "daemon_concurrency_limit"
        elif not is_hotfix and current_mission_count >= self.mission_max_concurrent:
            decision = "defer"
            granted_budgets = []
            queue_position = current_mission_count + 1
            pressure_reason = "mission_capacity_limit"
        elif not is_hotfix and current_worker_count >= self.worker_max_concurrent:
            decision = "reject"
            granted_budgets = []
            pressure_reason = "worker_capacity_hard_limit"
        elif current_verifier_count >= self.verifier_max_concurrent:
            decision = "degrade"
            pressure_reason = "verifier_capacity_limit"
            degrade_reason = "verification_capacity_saturated"
            granted_budgets = [
                _DAEMON_BUDGET_KEY,
                _MISSION_BUDGET_KEY,
                _WORKER_BUDGET_KEY,
            ]
        if pressure_reason:
            for scope in budget_scopes:
                saturated = scope["budget_state"] == "saturated"
                runtime_role = str(scope.get("runtime_role", "")).strip()
                if (
                    saturated
                    and (
                        (
                            decision == "defer"
                            and pressure_reason == "daemon_concurrency_limit"
                            and runtime_role == "daemon"
                        )
                        or (
                            decision == "defer"
                            and pressure_reason == "mission_capacity_limit"
                            and runtime_role == "mission"
                        )
                        or (decision == "reject" and runtime_role == "worker")
                        or (decision == "degrade" and runtime_role == "verifier")
                    )
                ):
                    scope["reason"] = pressure_reason
        return {
            "admission_decision_id": f"{issue_id}:{_QUEUE_NAME}:{recorded_at}",
            "workspace_id": str(workspace_id or issue_id).strip() or issue_id,
            "subject_id": issue_id,
            "subject_kind": "issue",
            "decision": decision,
            "required_budgets": [
                _DAEMON_BUDGET_KEY,
                _MISSION_BUDGET_KEY,
                _WORKER_BUDGET_KEY,
                _VERIFIER_BUDGET_KEY,
            ],
            "granted_budgets": granted_budgets,
            "queue_position": queue_position,
            "pressure_reason": pressure_reason,
            "degrade_reason": degrade_reason,
            "recorded_at": recorded_at,
            "queue_name": _QUEUE_NAME,
            "max_concurrent": self.max_concurrent,
            "in_progress_count": current_in_progress,
            "budget_scopes": budget_scopes,
            "source": "daemon",
        }

    def record_decision(self, decision: dict[str, Any]) -> None:
        self._decisions_path.parent.mkdir(parents=True, exist_ok=True)
        with self._decisions_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(decision, sort_keys=True) + "\n")


def load_admission_governor_snapshot(repo_root: Path) -> dict[str, list[dict[str, Any]]]:
    decisions_path = Path(repo_root) / ".spec_orch" / "admission" / "decisions.jsonl"
    latest_by_subject: dict[str, dict[str, Any]] = {}
    for row in _read_jsonl_rows(decisions_path):
        subject_id = str(row.get("subject_id", "")).strip()
        if not subject_id:
            continue
        current = latest_by_subject.get(subject_id)
        row_ts = str(row.get("recorded_at", "")).strip()
        current_ts = str(current.get("recorded_at", "")).strip() if current else ""
        if current is None or row_ts >= current_ts:
            latest_by_subject[subject_id] = row

    admission_decisions: list[dict[str, Any]] = []
    queue: list[dict[str, Any]] = []
    resource_budgets: list[dict[str, Any]] = []
    pressure_signals: list[dict[str, Any]] = []

    for row in sorted(
        latest_by_subject.values(),
        key=lambda item: (
            str(item.get("recorded_at", "")).strip(),
            str(item.get("subject_id", "")).strip(),
        ),
    ):
        workspace_id = (
            str(row.get("workspace_id", "")).strip() or str(row.get("subject_id", "")).strip()
        )
        subject_id = str(row.get("subject_id", "")).strip() or workspace_id
        subject_kind = str(row.get("subject_kind", "")).strip() or "issue"
        decision = str(row.get("decision", "")).strip() or "admit"
        required_budgets = [
            str(item).strip() for item in row.get("required_budgets", []) if str(item).strip()
        ]
        granted_budgets = [
            str(item).strip() for item in row.get("granted_budgets", []) if str(item).strip()
        ]
        queue_position_raw = row.get("queue_position")
        queue_position = int(queue_position_raw) if isinstance(queue_position_raw, int) else None
        recorded_at = str(row.get("recorded_at", "")).strip()
        pressure_reason = str(row.get("pressure_reason", "")).strip()
        degrade_reason = str(row.get("degrade_reason", "")).strip()
        budget_scope_rows = row.get("budget_scopes")
        if not isinstance(budget_scope_rows, list) or not budget_scope_rows:
            max_concurrent = max(1, int(row.get("max_concurrent", 1) or 1))
            in_progress_count = max(0, int(row.get("in_progress_count", 0) or 0))
            budget_scope_rows = [
                _budget_scope(
                    runtime_role="daemon",
                    budget_key=required_budgets[0] if required_budgets else _DAEMON_BUDGET_KEY,
                    current_count=in_progress_count,
                    limit=max_concurrent,
                    reason=pressure_reason,
                )
            ]
        for scope in budget_scope_rows:
            if not isinstance(scope, dict):
                continue
            runtime_role = str(scope.get("runtime_role", "")).strip() or "daemon"
            budget_key = str(scope.get("budget_key", "")).strip() or _DAEMON_BUDGET_KEY
            budget_state = str(scope.get("budget_state", "")).strip() or "healthy"
            remaining = max(0, int(scope.get("remaining", 0) or 0))
            current_count = max(0, int(scope.get("current_count", 0) or 0))
            limit = max(1, int(scope.get("limit", 1) or 1))
            scope_reason = str(scope.get("reason", "")).strip()
            budget = ResourceBudget(
                budget_id=f"{workspace_id}:{runtime_role}:{budget_key}",
                workspace_id=workspace_id,
                subject_id=subject_id,
                subject_kind=runtime_role,
                budget_key=budget_key,
                budget_state=budget_state,
                remaining_steps=remaining,
                remaining_loop_budget=remaining,
                continuation_count=0,
                recent_token_growth=current_count,
                justified=budget_state != "saturated",
                recorded_at=recorded_at,
            )
            resource_budgets.append(budget.to_dict())
            if not scope_reason:
                continue
            pressure_signals.append(
                PressureSignal(
                    pressure_signal_id=f"{workspace_id}:{runtime_role}:{budget_key}",
                    workspace_id=workspace_id,
                    subject_id=subject_id,
                    subject_kind=runtime_role,
                    budget_key=budget_key,
                    pressure_kind="concurrency",
                    severity="high" if budget_state == "saturated" else "warning",
                    reason=scope_reason or pressure_reason or decision,
                    details={
                        "runtime_role": runtime_role,
                        "limit": limit,
                        "current_count": current_count,
                        "remaining": remaining,
                        "decision": decision,
                    },
                    recorded_at=recorded_at,
                ).to_dict()
            )
        admission_decisions.append(
            AdmissionDecision(
                admission_decision_id=(
                    str(row.get("admission_decision_id", "")).strip()
                    or f"{workspace_id}:{_QUEUE_NAME}:{recorded_at}"
                ),
                workspace_id=workspace_id,
                subject_id=subject_id,
                subject_kind=subject_kind,
                decision=decision,
                required_budgets=required_budgets,
                granted_budgets=granted_budgets,
                queue_position=queue_position,
                pressure_reason=pressure_reason,
                degrade_reason=degrade_reason,
                recorded_at=recorded_at,
            ).to_dict()
        )
        if decision == "defer":
            queue.append(
                QueueEntry(
                    queue_entry_id=f"{workspace_id}:{_QUEUE_NAME}",
                    workspace_id=workspace_id,
                    subject_id=subject_id,
                    queue_name=str(row.get("queue_name", "")).strip() or _QUEUE_NAME,
                    position=queue_position or 1,
                    queue_state=decision,
                    claimed_by_agent_id="daemon",
                    claimed_at=recorded_at,
                ).to_dict()
            )

    return {
        "queue": queue,
        "resource_budgets": resource_budgets,
        "pressure_signals": pressure_signals,
        "admission_decisions": admission_decisions,
    }


__all__ = ["AdmissionGovernor", "load_admission_governor_snapshot"]
