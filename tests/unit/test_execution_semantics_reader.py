from __future__ import annotations

import json
from pathlib import Path

from spec_orch.domain.execution_semantics import (
    ArtifactCarrierKind,
    ArtifactScope,
    ContinuityKind,
    ExecutionOwnerKind,
    ExecutionStatus,
    ExecutionUnitKind,
    SubjectKind,
)
from spec_orch.services.execution_semantics_reader import (
    read_issue_execution_attempt,
    read_round_supervision_cycle,
    read_worker_execution_attempt,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_read_issue_execution_attempt_prefers_unified_artifacts(tmp_path: Path) -> None:
    workspace = tmp_path / ".spec_orch_runs" / "run-123"
    _write_json(
        workspace / "run_artifact" / "live.json",
        {
            "run_id": "run-123",
            "issue_id": "ISSUE-123",
            "builder": {"succeeded": True, "adapter": "codex"},
            "verification": {"tests": {"exit_code": 0}},
            "review": {"verdict": "approved"},
        },
    )
    _write_json(
        workspace / "run_artifact" / "conclusion.json",
        {
            "run_id": "run-123",
            "issue_id": "ISSUE-123",
            "verdict": "pass",
            "mergeable": True,
            "completed_at": "2026-03-29T12:00:00+00:00",
        },
    )
    _write_json(
        workspace / "run_artifact" / "manifest.json",
        {
            "run_id": "run-123",
            "issue_id": "ISSUE-123",
            "artifacts": {
                "builder_report": str(workspace / "builder_report.json"),
            },
        },
    )
    (workspace / "run_artifact" / "events.jsonl").write_text(
        '{"type":"result"}\n', encoding="utf-8"
    )
    (workspace / "builder_report.json").write_text("{}", encoding="utf-8")
    (workspace / "review_report.json").write_text("{}", encoding="utf-8")
    (workspace / "acceptance.json").write_text("{}", encoding="utf-8")

    attempt = read_issue_execution_attempt(workspace)

    assert attempt is not None
    assert attempt.attempt_id == "run-123"
    assert attempt.unit_kind is ExecutionUnitKind.ISSUE
    assert attempt.unit_id == "ISSUE-123"
    assert attempt.owner_kind is ExecutionOwnerKind.RUN_CONTROLLER
    assert attempt.continuity_kind is ContinuityKind.FILE_BACKED_RUN
    assert attempt.outcome.status is ExecutionStatus.SUCCEEDED
    assert attempt.outcome.artifacts["builder_report"].path.endswith("builder_report.json")
    assert attempt.outcome.artifacts["event_log"].path.endswith("run_artifact/events.jsonl")
    assert attempt.outcome.artifacts["manifest"].path.endswith("run_artifact/manifest.json")
    assert attempt.outcome.artifacts["review_report"].path.endswith("review_report.json")
    assert attempt.outcome.artifacts["acceptance_report"].path.endswith("acceptance.json")
    assert attempt.outcome.artifacts["workspace_root"].carrier_kind is ArtifactCarrierKind.DIRECTORY


def test_read_worker_execution_attempt_normalizes_worker_session_artifacts(
    tmp_path: Path,
) -> None:
    worker_dir = tmp_path / "docs/specs/mission-1/workers/pkt-1"
    _write_json(
        worker_dir / "builder_report.json",
        {
            "succeeded": True,
            "session_name": "mission-m1-pkt1",
            "completed_at": "2026-03-29T12:10:00+00:00",
        },
    )
    (worker_dir / "telemetry").mkdir(parents=True, exist_ok=True)
    (worker_dir / "telemetry" / "incoming_events.jsonl").write_text(
        '{"type":"result"}\n',
        encoding="utf-8",
    )
    (worker_dir / "telemetry" / "activity.log").write_text("worker completed\n", encoding="utf-8")

    attempt = read_worker_execution_attempt(worker_dir, mission_id="mission-1", packet_id="pkt-1")

    assert attempt is not None
    assert attempt.unit_kind is ExecutionUnitKind.WORK_PACKET
    assert attempt.unit_id == "pkt-1"
    assert attempt.owner_kind is ExecutionOwnerKind.ROUND_WORKER
    assert attempt.continuity_kind is ContinuityKind.WORKER_SESSION
    assert attempt.continuity_id == "mission-m1-pkt1"
    assert attempt.outcome.status is ExecutionStatus.SUCCEEDED
    assert attempt.outcome.artifacts["builder_report"].scope is ArtifactScope.LEAF
    assert attempt.outcome.artifacts["builder_report"].subject_kind is SubjectKind.WORK_PACKET
    assert attempt.outcome.artifacts["event_log"].path.endswith("telemetry/incoming_events.jsonl")


def test_read_worker_execution_attempt_preserves_unknown_started_at_as_none(
    tmp_path: Path,
) -> None:
    worker_dir = tmp_path / "docs/specs/mission-1/workers/pkt-2"
    _write_json(
        worker_dir / "builder_report.json",
        {
            "succeeded": True,
            "session_name": "mission-m1-pkt2",
        },
    )

    attempt = read_worker_execution_attempt(worker_dir, mission_id="mission-1", packet_id="pkt-2")

    assert attempt is not None
    assert attempt.started_at is None


def test_read_round_supervision_cycle_keeps_round_separate_from_execution_attempt(
    tmp_path: Path,
) -> None:
    round_dir = tmp_path / "docs/specs/mission-1/rounds/round-03"
    _write_json(
        round_dir / "round_summary.json",
        {
            "round_id": 3,
            "worker_results": [
                {"packet_id": "pkt-1"},
                {"packet_id": "pkt-2"},
            ],
            "verification_outputs": [{"packet_id": "pkt-1"}],
            "gate_verdicts": [{"packet_id": "pkt-1", "verdict": "pass"}],
        },
    )
    _write_json(round_dir / "round_decision.json", {"action": "continue"})
    _write_json(round_dir / "acceptance_review.json", {"browser_evidence": [{"url": "/"}]})
    _write_json(round_dir / "visual_evaluation.json", {"status": "ok"})
    (round_dir / "supervisor_review.md").write_text("# Review\n", encoding="utf-8")

    payload = read_round_supervision_cycle(round_dir)

    assert payload is not None
    cycle = payload["cycle"]
    artifacts = payload["artifacts"]
    assert cycle.mission_id == "mission-1"
    assert cycle.round_id == "round-03"
    assert cycle.packet_ids == ["pkt-1", "pkt-2"]
    assert artifacts["review_report"].scope is ArtifactScope.ROUND
    assert artifacts["review_report"].path.endswith("supervisor_review.md")
    assert artifacts["acceptance_report"].path.endswith("acceptance_review.json")
    assert artifacts["visual_report"].path.endswith("visual_evaluation.json")
    assert artifacts["browser_evidence"].path.endswith("acceptance_review.json")
    assert artifacts["verification_report"].path.endswith("round_summary.json")
    assert artifacts["gate_report"].path.endswith("round_summary.json")


def test_read_round_supervision_cycle_falls_back_to_embedded_summary_decision(
    tmp_path: Path,
) -> None:
    round_dir = tmp_path / "docs/specs/mission-embedded/rounds/round-02"
    embedded_decision = {
        "action": "ask_human",
        "reason_code": "needs_review",
        "summary": "Need human approval before rollout.",
        "confidence": 0.74,
        "blocking_questions": ["Approve rollout?"],
    }
    _write_json(
        round_dir / "round_summary.json",
        {
            "round_id": 2,
            "worker_results": [{"packet_id": "pkt-1"}],
            "decision": embedded_decision,
        },
    )

    payload = read_round_supervision_cycle(round_dir)

    assert payload is not None
    assert payload["decision"] == embedded_decision
