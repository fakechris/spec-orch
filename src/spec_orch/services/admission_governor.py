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

_BUDGET_KEY = "daemon:max_concurrent"
_QUEUE_NAME = "daemon_admission"


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
    def __init__(self, repo_root: Path, *, max_concurrent: int) -> None:
        self.repo_root = Path(repo_root)
        self.max_concurrent = max(1, int(max_concurrent))
        self._decisions_path = self.repo_root / ".spec_orch" / "admission" / "decisions.jsonl"

    def evaluate_issue(
        self,
        issue_id: str,
        *,
        in_progress_count: int,
        is_hotfix: bool,
        recorded_at: str,
    ) -> dict[str, Any]:
        current_in_progress = max(0, int(in_progress_count))
        decision = "admit"
        granted_budgets = [_BUDGET_KEY]
        queue_position: int | None = None
        pressure_reason = ""
        if not is_hotfix and current_in_progress >= self.max_concurrent:
            decision = "defer"
            granted_budgets = []
            queue_position = current_in_progress + 1
            pressure_reason = "max_concurrent_limit"
        return {
            "admission_decision_id": f"{issue_id}:{_QUEUE_NAME}:{recorded_at}",
            "workspace_id": issue_id,
            "subject_id": issue_id,
            "subject_kind": "issue",
            "decision": decision,
            "required_budgets": [_BUDGET_KEY],
            "granted_budgets": granted_budgets,
            "queue_position": queue_position,
            "pressure_reason": pressure_reason,
            "degrade_reason": "",
            "recorded_at": recorded_at,
            "queue_name": _QUEUE_NAME,
            "max_concurrent": self.max_concurrent,
            "in_progress_count": current_in_progress,
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
        workspace_id = str(row.get("workspace_id", "")).strip() or str(
            row.get("subject_id", "")
        ).strip()
        subject_id = str(row.get("subject_id", "")).strip() or workspace_id
        subject_kind = str(row.get("subject_kind", "")).strip() or "issue"
        decision = str(row.get("decision", "")).strip() or "admit"
        required_budgets = [
            str(item).strip()
            for item in row.get("required_budgets", [])
            if str(item).strip()
        ]
        granted_budgets = [
            str(item).strip()
            for item in row.get("granted_budgets", [])
            if str(item).strip()
        ]
        queue_position_raw = row.get("queue_position")
        queue_position = int(queue_position_raw) if isinstance(queue_position_raw, int) else None
        recorded_at = str(row.get("recorded_at", "")).strip()
        pressure_reason = str(row.get("pressure_reason", "")).strip()
        degrade_reason = str(row.get("degrade_reason", "")).strip()
        budget_key = required_budgets[0] if required_budgets else _BUDGET_KEY
        max_concurrent = max(1, int(row.get("max_concurrent", 1) or 1))
        in_progress_count = max(0, int(row.get("in_progress_count", 0) or 0))
        budget_state = "saturated" if decision in {"defer", "reject"} else "healthy"
        budget = ResourceBudget(
            budget_id=f"{workspace_id}:{budget_key}",
            workspace_id=workspace_id,
            subject_id=subject_id,
            subject_kind="daemon",
            budget_key=budget_key,
            budget_state=budget_state,
            remaining_steps=max(max_concurrent - in_progress_count, 0),
            remaining_loop_budget=max(max_concurrent - in_progress_count, 0),
            continuation_count=0,
            recent_token_growth=0,
            justified=decision == "admit",
            recorded_at=recorded_at,
        )
        resource_budgets.append(budget.to_dict())
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
        if decision in {"defer", "reject"}:
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
            pressure_signals.append(
                PressureSignal(
                    pressure_signal_id=f"{workspace_id}:{budget_key}",
                    workspace_id=workspace_id,
                    subject_id=subject_id,
                    subject_kind=subject_kind,
                    budget_key=budget_key,
                    pressure_kind="concurrency",
                    severity="high",
                    reason=pressure_reason or decision,
                    details={
                        "max_concurrent": max_concurrent,
                        "in_progress_count": in_progress_count,
                    },
                    recorded_at=recorded_at,
                ).to_dict()
            )

    return {
        "queue": queue,
        "resource_budgets": resource_budgets,
        "pressure_signals": pressure_signals,
        "admission_decisions": admission_decisions,
    }


__all__ = ["AdmissionGovernor", "load_admission_governor_snapshot"]
