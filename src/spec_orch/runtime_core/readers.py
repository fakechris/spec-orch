from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from spec_orch.runtime_core.models import (
    ArtifactCarrierKind,
    ArtifactRef,
    ArtifactScope,
    ContinuityKind,
    ExecutionAttempt,
    ExecutionAttemptState,
    ExecutionOutcome,
    ExecutionOwnerKind,
    ExecutionStatus,
    ExecutionUnitKind,
    SubjectKind,
    SupervisionCycle,
)
from spec_orch.runtime_core.paths import (
    normalized_issue_conclusion_path,
    normalized_issue_live_path,
    normalized_issue_manifest_path,
    normalized_issue_root,
    normalized_round_decision_path,
    normalized_round_summary_path,
    normalized_round_root,
    normalized_worker_builder_report_path,
)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def _artifact(
    *,
    key: str,
    scope: ArtifactScope,
    producer_kind: str,
    subject_kind: SubjectKind,
    carrier_kind: ArtifactCarrierKind,
    path: Path,
) -> ArtifactRef:
    return ArtifactRef(
        key=key,
        scope=scope,
        producer_kind=producer_kind,
        subject_kind=subject_kind,
        carrier_kind=carrier_kind,
        path=str(path),
    )


def _issue_status(data: dict[str, Any], live: dict[str, Any]) -> ExecutionStatus:
    state = str(data.get("state") or live.get("state") or "").lower()
    if state == "failed":
        return ExecutionStatus.FAILED

    verdict = str(data.get("verdict") or "").lower()
    if verdict == "pass":
        return ExecutionStatus.SUCCEEDED
    if verdict == "fail":
        return ExecutionStatus.FAILED

    mergeable = data.get("mergeable")
    if mergeable is True:
        return ExecutionStatus.SUCCEEDED
    if mergeable is False:
        return ExecutionStatus.FAILED

    builder = live.get("builder")
    if isinstance(builder, dict):
        if builder.get("succeeded") is True:
            return ExecutionStatus.SUCCEEDED
        if builder.get("succeeded") is False:
            return ExecutionStatus.FAILED

    return ExecutionStatus.PARTIAL


def _worker_status(builder_report: dict[str, Any]) -> ExecutionStatus:
    if builder_report.get("succeeded") is True or builder_report.get("success") is True:
        return ExecutionStatus.SUCCEEDED
    if builder_report.get("succeeded") is False or builder_report.get("success") is False:
        return ExecutionStatus.FAILED
    exit_code = builder_report.get("exit_code")
    if isinstance(exit_code, int):
        return ExecutionStatus.SUCCEEDED if exit_code == 0 else ExecutionStatus.FAILED
    return ExecutionStatus.PARTIAL


def _mission_id_from_round_dir(round_dir: Path) -> str:
    parts = round_dir.parts
    if "rounds" in parts:
        idx = parts.index("rounds")
        if idx >= 1:
            return parts[idx - 1]
    return round_dir.parent.parent.name


def read_issue_artifacts(workspace: Path) -> dict[str, ArtifactRef]:
    artifacts: dict[str, ArtifactRef] = {
        "workspace_root": _artifact(
            key="workspace_root",
            scope=ArtifactScope.LEAF,
            producer_kind="workspace_service",
            subject_kind=SubjectKind.ISSUE,
            carrier_kind=ArtifactCarrierKind.DIRECTORY,
            path=workspace,
        )
    }

    manifest_path = normalized_issue_manifest_path(workspace)
    legacy_manifest_path = workspace / "artifact_manifest.json"
    manifest_data = _read_json(manifest_path) or _read_json(legacy_manifest_path) or {}
    manifest_artifacts = manifest_data.get("artifacts", {})
    if manifest_path.exists():
        artifacts["manifest"] = _artifact(
            key="manifest",
            scope=ArtifactScope.LEAF,
            producer_kind="run_artifact_service",
            subject_kind=SubjectKind.ISSUE,
            carrier_kind=ArtifactCarrierKind.JSON,
            path=manifest_path,
        )
    elif legacy_manifest_path.exists():
        artifacts["manifest"] = _artifact(
            key="manifest",
            scope=ArtifactScope.LEAF,
            producer_kind="run_report_writer",
            subject_kind=SubjectKind.ISSUE,
            carrier_kind=ArtifactCarrierKind.JSON,
            path=legacy_manifest_path,
        )

    builder_path = manifest_artifacts.get("builder_report")
    builder_report_path = Path(builder_path) if isinstance(builder_path, str) else workspace / "builder_report.json"
    if builder_report_path.exists():
        artifacts["builder_report"] = _artifact(
            key="builder_report",
            scope=ArtifactScope.LEAF,
            producer_kind="builder_adapter",
            subject_kind=SubjectKind.ISSUE,
            carrier_kind=ArtifactCarrierKind.JSON,
            path=builder_report_path,
        )

    for candidate in (
        normalized_issue_root(workspace) / "events.jsonl",
        workspace / "telemetry" / "incoming_events.jsonl",
        workspace / "telemetry" / "activity.log",
    ):
        if candidate.exists():
            artifacts["event_log"] = _artifact(
                key="event_log",
                scope=ArtifactScope.LEAF,
                producer_kind="activity_logger",
                subject_kind=SubjectKind.ISSUE,
                carrier_kind=ArtifactCarrierKind.JSONL if candidate.suffix == ".jsonl" else ArtifactCarrierKind.FILE,
                path=candidate,
            )
            break

    review_path = workspace / "review_report.json"
    if review_path.exists():
        artifacts["review_report"] = _artifact(
            key="review_report",
            scope=ArtifactScope.LEAF,
            producer_kind="review_adapter",
            subject_kind=SubjectKind.ISSUE,
            carrier_kind=ArtifactCarrierKind.JSON,
            path=review_path,
        )

    acceptance_path = workspace / "acceptance.json"
    if acceptance_path.exists():
        artifacts["acceptance_report"] = _artifact(
            key="acceptance_report",
            scope=ArtifactScope.LEAF,
            producer_kind="artifact_service",
            subject_kind=SubjectKind.ISSUE,
            carrier_kind=ArtifactCarrierKind.JSON,
            path=acceptance_path,
        )

    conclusion_path = normalized_issue_conclusion_path(workspace)
    if conclusion_path.exists():
        artifacts["gate_report"] = _artifact(
            key="gate_report",
            scope=ArtifactScope.LEAF,
            producer_kind="run_artifact_service",
            subject_kind=SubjectKind.ISSUE,
            carrier_kind=ArtifactCarrierKind.JSON,
            path=conclusion_path,
        )

    live_path = normalized_issue_live_path(workspace)
    if live_path.exists():
        live = _read_json(live_path) or {}
        if live.get("verification"):
            artifacts["verification_report"] = _artifact(
                key="verification_report",
                scope=ArtifactScope.LEAF,
                producer_kind="run_artifact_service",
                subject_kind=SubjectKind.ISSUE,
                carrier_kind=ArtifactCarrierKind.JSON,
                path=live_path,
            )
        if "review_report" not in artifacts and live.get("review"):
            artifacts["review_report"] = _artifact(
                key="review_report",
                scope=ArtifactScope.LEAF,
                producer_kind="run_artifact_service",
                subject_kind=SubjectKind.ISSUE,
                carrier_kind=ArtifactCarrierKind.JSON,
                path=live_path,
            )

    return artifacts


def read_issue_execution_attempt(workspace: Path) -> ExecutionAttempt | None:
    live = _read_json(normalized_issue_live_path(workspace)) or {}
    conclusion = _read_json(normalized_issue_conclusion_path(workspace))
    report = _read_json(workspace / "report.json")
    data = conclusion or report
    if data is None:
        return None

    live_data = live or report or {}
    unit_id = str(data.get("issue_id") or live_data.get("issue_id") or workspace.name)
    attempt_id = str(data.get("run_id") or live_data.get("run_id") or workspace.name)
    outcome = ExecutionOutcome(
        unit_kind=ExecutionUnitKind.ISSUE,
        owner_kind=ExecutionOwnerKind.RUN_CONTROLLER,
        status=_issue_status(data, live_data),
        build=live_data.get("builder"),
        verification=live_data.get("verification"),
        review=live_data.get("review"),
        gate={
            "state": data.get("state"),
            "verdict": data.get("verdict"),
            "mergeable": data.get("mergeable"),
            "failed_conditions": data.get("failed_conditions", []),
        },
        artifacts=read_issue_artifacts(workspace),
    )
    return ExecutionAttempt(
        attempt_id=attempt_id,
        unit_kind=ExecutionUnitKind.ISSUE,
        unit_id=unit_id,
        owner_kind=ExecutionOwnerKind.RUN_CONTROLLER,
        continuity_kind=ContinuityKind.FILE_BACKED_RUN,
        continuity_id=attempt_id,
        workspace_root=str(workspace),
        attempt_state=ExecutionAttemptState.COMPLETED,
        started_at=str(live_data.get("started_at") or data.get("started_at") or ""),
        completed_at=data.get("completed_at"),
        outcome=outcome,
    )


def read_worker_execution_attempt(
    worker_dir: Path,
    *,
    mission_id: str,
    packet_id: str,
) -> ExecutionAttempt | None:
    builder_report_path = normalized_worker_builder_report_path(worker_dir)
    builder_report = _read_json(builder_report_path)
    if builder_report is None:
        return None

    session_name = builder_report.get("session_name")
    continuity_kind = ContinuityKind.WORKER_SESSION if session_name else ContinuityKind.ONESHOT_WORKER

    artifacts: dict[str, ArtifactRef] = {
        "workspace_root": _artifact(
            key="workspace_root",
            scope=ArtifactScope.LEAF,
            producer_kind="worker_factory",
            subject_kind=SubjectKind.WORK_PACKET,
            carrier_kind=ArtifactCarrierKind.DIRECTORY,
            path=worker_dir,
        ),
        "builder_report": _artifact(
            key="builder_report",
            scope=ArtifactScope.LEAF,
            producer_kind="worker_handle",
            subject_kind=SubjectKind.WORK_PACKET,
            carrier_kind=ArtifactCarrierKind.JSON,
            path=builder_report_path,
        ),
    }
    for candidate in (
        worker_dir / "telemetry" / "incoming_events.jsonl",
        worker_dir / "telemetry" / "activity.log",
    ):
        if candidate.exists():
            artifacts["event_log"] = _artifact(
                key="event_log",
                scope=ArtifactScope.LEAF,
                producer_kind="worker_handle",
                subject_kind=SubjectKind.WORK_PACKET,
                carrier_kind=ArtifactCarrierKind.JSONL if candidate.suffix == ".jsonl" else ArtifactCarrierKind.FILE,
                path=candidate,
            )
            break

    attempt_id = str(builder_report.get("run_id") or session_name or f"{mission_id}:{packet_id}")
    outcome = ExecutionOutcome(
        unit_kind=ExecutionUnitKind.WORK_PACKET,
        owner_kind=ExecutionOwnerKind.ROUND_WORKER,
        status=_worker_status(builder_report),
        build=builder_report,
        artifacts=artifacts,
    )
    return ExecutionAttempt(
        attempt_id=attempt_id,
        unit_kind=ExecutionUnitKind.WORK_PACKET,
        unit_id=packet_id,
        owner_kind=ExecutionOwnerKind.ROUND_WORKER,
        continuity_kind=continuity_kind,
        continuity_id=str(session_name) if session_name else None,
        workspace_root=str(worker_dir),
        attempt_state=ExecutionAttemptState.COMPLETED,
        started_at=str(builder_report.get("started_at") or ""),
        completed_at=builder_report.get("completed_at"),
        outcome=outcome,
    )


def read_round_supervision_cycle(round_dir: Path) -> dict[str, Any] | None:
    summary_path = normalized_round_summary_path(round_dir)
    summary = _read_json(summary_path)
    if summary is None:
        return None

    decision = _read_json(normalized_round_decision_path(round_dir))
    if decision is None:
        embedded_decision = summary.get("decision")
        if isinstance(embedded_decision, dict):
            decision = embedded_decision
    mission_id = _mission_id_from_round_dir(round_dir)
    packet_ids = [
        str(item.get("packet_id"))
        for item in summary.get("worker_results", [])
        if isinstance(item, dict) and item.get("packet_id")
    ]
    cycle = SupervisionCycle(
        cycle_id=f"{mission_id}:{round_dir.name}",
        mission_id=mission_id,
        round_id=round_dir.name,
        packet_ids=packet_ids,
    )

    artifacts: dict[str, ArtifactRef] = {
        "workspace_root": _artifact(
            key="workspace_root",
            scope=ArtifactScope.ROUND,
            producer_kind="round_orchestrator",
            subject_kind=SubjectKind.ROUND,
            carrier_kind=ArtifactCarrierKind.DIRECTORY,
            path=normalized_round_root(round_dir),
        )
    }
    review_path = round_dir / "supervisor_review.md"
    if review_path.exists():
        artifacts["review_report"] = _artifact(
            key="review_report",
            scope=ArtifactScope.ROUND,
            producer_kind="supervisor_adapter",
            subject_kind=SubjectKind.ROUND,
            carrier_kind=ArtifactCarrierKind.MARKDOWN,
            path=review_path,
        )

    acceptance_path = round_dir / "acceptance_review.json"
    acceptance_review = _read_json(acceptance_path)
    if acceptance_path.exists():
        artifacts["acceptance_report"] = _artifact(
            key="acceptance_report",
            scope=ArtifactScope.ROUND,
            producer_kind="acceptance_evaluator",
            subject_kind=SubjectKind.ROUND,
            carrier_kind=ArtifactCarrierKind.JSON,
            path=acceptance_path,
        )
        if isinstance(acceptance_review, dict) and acceptance_review.get("browser_evidence"):
            artifacts["browser_evidence"] = _artifact(
                key="browser_evidence",
                scope=ArtifactScope.ROUND,
                producer_kind="acceptance_evaluator",
                subject_kind=SubjectKind.ROUND,
                carrier_kind=ArtifactCarrierKind.JSON,
                path=acceptance_path,
            )

    visual_path = round_dir / "visual_evaluation.json"
    if visual_path.exists():
        artifacts["visual_report"] = _artifact(
            key="visual_report",
            scope=ArtifactScope.ROUND,
            producer_kind="visual_evaluator",
            subject_kind=SubjectKind.ROUND,
            carrier_kind=ArtifactCarrierKind.JSON,
            path=visual_path,
        )

    if summary.get("verification_outputs"):
        artifacts["verification_report"] = _artifact(
            key="verification_report",
            scope=ArtifactScope.ROUND,
            producer_kind="round_orchestrator",
            subject_kind=SubjectKind.ROUND,
            carrier_kind=ArtifactCarrierKind.JSON,
            path=summary_path,
        )
    if summary.get("gate_verdicts"):
        artifacts["gate_report"] = _artifact(
            key="gate_report",
            scope=ArtifactScope.ROUND,
            producer_kind="round_orchestrator",
            subject_kind=SubjectKind.ROUND,
            carrier_kind=ArtifactCarrierKind.JSON,
            path=summary_path,
        )

    return {
        "cycle": cycle,
        "summary": summary,
        "decision": decision,
        "artifacts": artifacts,
    }


__all__ = [
    "read_issue_artifacts",
    "read_issue_execution_attempt",
    "read_round_supervision_cycle",
    "read_worker_execution_attempt",
]
