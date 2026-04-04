from __future__ import annotations

import json
from pathlib import Path

from spec_orch.runtime_chain.models import (
    ChainPhase,
    RuntimeChainEvent,
    RuntimeChainStatus,
    RuntimeSubjectKind,
)
from spec_orch.runtime_chain.store import append_chain_event, write_chain_status
from spec_orch.runtime_core.observability.models import (
    RuntimeBudgetVisibility,
    RuntimeLiveSummary,
    RuntimeStallSignal,
)
from spec_orch.runtime_core.observability.store import write_live_summary


def test_build_execution_substrate_snapshot_collects_issue_and_mission_active_work(
    tmp_path: Path,
) -> None:
    from spec_orch.services.execution_substrate import build_execution_substrate_snapshot

    mission_chain_root = tmp_path / "docs" / "specs" / "mission-1" / "operator" / "runtime_chain"
    mission_chain_root.mkdir(parents=True)
    write_chain_status(
        mission_chain_root,
        RuntimeChainStatus(
            chain_id="chain-mission-1",
            active_span_id="chain-mission-1:acceptance",
            subject_kind=RuntimeSubjectKind.ACCEPTANCE,
            subject_id="mission-1",
            phase=ChainPhase.HEARTBEAT,
            status_reason="acceptance_waiting_on_model",
            updated_at="2026-04-02T16:00:00+00:00",
        ),
    )

    issue_chain_root = tmp_path / ".worktrees" / "SPC-1" / "telemetry" / "runtime_chain"
    issue_chain_root.mkdir(parents=True)
    write_chain_status(
        issue_chain_root,
        RuntimeChainStatus(
            chain_id="run-spc-1",
            active_span_id="run-spc-1:issue:gate",
            subject_kind=RuntimeSubjectKind.ISSUE,
            subject_id="SPC-1",
            phase=ChainPhase.DEGRADED,
            status_reason="gate_blocked",
            updated_at="2026-04-02T16:05:00+00:00",
        ),
    )

    snapshot = build_execution_substrate_snapshot(tmp_path)

    assert snapshot["summary"]["active_work_count"] == 2
    assert snapshot["summary"]["degraded_count"] == 1
    assert snapshot["summary"]["intervention_needed_count"] == 1
    assert snapshot["queue"] == []
    assert snapshot["interventions"] == []
    assert any(item["workspace_id"] == "mission-1" for item in snapshot["active_work"])
    assert any(item["workspace_id"] == "SPC-1" for item in snapshot["active_work"])
    assert any(item["agent_id"] == "acceptance_evaluator" for item in snapshot["agents"])
    assert any(item["agent_id"] == "run_controller" for item in snapshot["agents"])
    assert snapshot["runtimes"][0]["runtime_id"] == "runtime:local"


def test_build_execution_substrate_snapshot_serializes_to_json_cleanly(tmp_path: Path) -> None:
    from spec_orch.services.execution_substrate import build_execution_substrate_snapshot

    chain_root = tmp_path / "docs" / "specs" / "mission-2" / "operator" / "runtime_chain"
    chain_root.mkdir(parents=True)
    write_chain_status(
        chain_root,
        RuntimeChainStatus(
            chain_id="chain-mission-2",
            active_span_id="chain-mission-2:mission",
            subject_kind=RuntimeSubjectKind.MISSION,
            subject_id="mission-2",
            phase=ChainPhase.STARTED,
            status_reason="mission_supervision_started",
            updated_at="2026-04-02T16:10:00+00:00",
        ),
    )

    snapshot = build_execution_substrate_snapshot(tmp_path)

    json.dumps(snapshot)
    assert snapshot["summary"]["runtime_count"] == 1
    assert snapshot["summary"]["agent_count"] == 1


def test_build_execution_substrate_snapshot_surfaces_queue_pressure_and_interventions(
    tmp_path: Path,
) -> None:
    from spec_orch.services.execution_substrate import build_execution_substrate_snapshot

    mission_id = "mission-queue"
    mission_chain_root = tmp_path / "docs" / "specs" / mission_id / "operator" / "runtime_chain"
    mission_chain_root.mkdir(parents=True)
    write_chain_status(
        mission_chain_root,
        RuntimeChainStatus(
            chain_id="chain-mission-queue",
            active_span_id="chain-mission-queue:acceptance",
            subject_kind=RuntimeSubjectKind.ACCEPTANCE,
            subject_id=mission_id,
            phase=ChainPhase.HEARTBEAT,
            status_reason="acceptance_waiting_on_model",
            updated_at="2026-04-02T16:25:00+00:00",
        ),
    )
    append_chain_event(
        mission_chain_root,
        RuntimeChainEvent(
            chain_id="chain-mission-queue",
            span_id="chain-mission-queue:acceptance:start",
            parent_span_id=None,
            subject_kind=RuntimeSubjectKind.ACCEPTANCE,
            subject_id=mission_id,
            phase=ChainPhase.STARTED,
            status_reason="acceptance_started",
            artifact_refs={"log": "docs/specs/mission-queue/operator/logs/acceptance.log"},
            updated_at="2026-04-02T16:24:00+00:00",
        ),
    )
    append_chain_event(
        mission_chain_root,
        RuntimeChainEvent(
            chain_id="chain-mission-queue",
            span_id="chain-mission-queue:acceptance:heartbeat",
            parent_span_id="chain-mission-queue:acceptance:start",
            subject_kind=RuntimeSubjectKind.ACCEPTANCE,
            subject_id=mission_id,
            phase=ChainPhase.HEARTBEAT,
            status_reason="acceptance_waiting_on_model",
            session_refs={"runtime_id": "runtime:local", "agent_id": "acceptance_evaluator"},
            artifact_refs={
                "summary": "docs/specs/mission-queue/operator/runtime_chain/chain_status.json"
            },
            updated_at="2026-04-02T16:25:00+00:00",
        ),
    )

    operator_dir = tmp_path / "docs" / "specs" / mission_id / "operator"
    with (operator_dir / "interventions.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "intervention_id": "intervention-1",
                    "point_key": "scope_gate",
                    "summary": "Review the scope gate mismatch.",
                    "questions": ["Should the round continue?"],
                    "status": "open",
                    "created_at": "2026-04-02T16:24:30+00:00",
                    "decision_record_id": "decision-1",
                    "mission_id": mission_id,
                    "round_id": 1,
                    "review_route": f"/?mission={mission_id}&mode=missions&tab=approvals&round=1",
                }
            )
            + "\n"
        )

    observability_root = operator_dir / "observability" / "round-01-acceptance-graph"
    write_live_summary(
        observability_root,
        RuntimeLiveSummary(
            subject_key=f"{mission_id}:round-1:acceptance-graph",
            phase="running",
            status_reason="waiting_for_operator_review",
            current_step_key="candidate_review",
            budget=RuntimeBudgetVisibility(
                budget_key="verify_contract_graph",
                planned_steps=4,
                completed_steps=2,
                remaining_steps=2,
                loop_budget=1,
                remaining_loop_budget=0,
                continuation_count=1,
                recent_token_growth=1200,
                justified=False,
            ),
            stall_signal=RuntimeStallSignal(
                stalled=True,
                idle_seconds=18,
                reason="operator_wait",
                diminishing_returns=True,
                repeated_steps=2,
            ),
            updated_at="2026-04-02T16:25:30+00:00",
        ),
    )

    snapshot = build_execution_substrate_snapshot(tmp_path)

    assert snapshot["summary"]["queued_count"] == 1
    assert snapshot["summary"]["open_intervention_count"] == 1
    assert snapshot["summary"]["pressure_signal_count"] == 1
    assert snapshot["summary"]["admission_decision_counts"] == {
        "admit": 1,
        "defer": 1,
        "reject": 0,
        "degrade": 0,
    }
    assert len(snapshot["execution_sessions"]) == 1
    assert snapshot["execution_sessions"][0]["queue_state"] == "running"
    assert snapshot["execution_sessions"][0]["runtime_id"] == "runtime:local"
    assert snapshot["execution_sessions"][0]["agent_id"] == "acceptance_evaluator"
    assert len(snapshot["execution_events"]) == 2
    assert snapshot["execution_events"][-1]["event_type"] == "heartbeat"
    assert snapshot["execution_events"][-1]["event_source"] == "runtime_chain"
    assert snapshot["execution_events"][-1]["event_summary"] == "acceptance_waiting_on_model"
    assert snapshot["resource_budgets"][0]["budget_key"] == "verify_contract_graph"
    assert snapshot["resource_budgets"][0]["budget_state"] == "saturated"
    assert snapshot["pressure_signals"][0]["pressure_kind"] == "stall"
    assert snapshot["pressure_signals"][0]["budget_key"] == "verify_contract_graph"
    assert snapshot["admission_decisions"] == [
        {
            "admission_decision_id": "mission-queue:chain-mission-queue:acceptance",
            "workspace_id": "mission-queue",
            "subject_id": "mission-queue",
            "subject_kind": "acceptance",
            "decision": "admit",
            "required_budgets": ["verify_contract_graph"],
            "granted_budgets": ["verify_contract_graph"],
            "queue_position": None,
            "pressure_reason": "waiting_for_operator_review",
            "degrade_reason": "",
            "recorded_at": "2026-04-02T16:25:00+00:00",
        },
        {
            "admission_decision_id": "mission-queue:intervention-1",
            "workspace_id": "mission-queue",
            "subject_id": "mission-queue:round-1",
            "subject_kind": "round",
            "decision": "defer",
            "required_budgets": ["operator_intervention"],
            "granted_budgets": [],
            "queue_position": 1,
            "pressure_reason": "waiting_for_operator_review",
            "degrade_reason": "",
            "recorded_at": "2026-04-02T16:24:30+00:00",
        },
    ]
    assert snapshot["queue"][0]["queue_name"] == "operator_intervention"
    assert snapshot["queue"][0]["queue_state"] == "defer"
    assert snapshot["interventions"][0]["action"] == "scope_gate"
    assert snapshot["interventions"][0]["outcome"] == "open"
    runtime = snapshot["runtimes"][0]
    assert runtime["usage_summary"]["queued_sessions"] == 1
    assert runtime["usage_summary"]["open_interventions"] == 1
    assert runtime["activity_summary"]["budget_keys"] == ["verify_contract_graph"]
    assert runtime["activity_summary"]["stalled_workspace_ids"] == [mission_id]
    assert runtime["activity_summary"]["pressure_signals"][0]["status_reason"] == (
        "waiting_for_operator_review"
    )


def test_build_execution_substrate_snapshot_includes_governor_backed_admission_state(
    tmp_path: Path,
) -> None:
    from spec_orch.services.admission_governor import AdmissionGovernor
    from spec_orch.services.execution_substrate import build_execution_substrate_snapshot

    governor = AdmissionGovernor(tmp_path, max_concurrent=1)
    governor.record_decision(
        governor.evaluate_issue(
            "SPC-412",
            in_progress_count=1,
            is_hotfix=False,
            recorded_at="2026-04-03T10:05:00+00:00",
        )
    )

    snapshot = build_execution_substrate_snapshot(tmp_path)

    assert snapshot["summary"]["queued_count"] == 1
    assert snapshot["summary"]["pressure_signal_count"] == 1
    assert snapshot["summary"]["admission_decision_counts"] == {
        "admit": 0,
        "defer": 1,
        "reject": 0,
        "degrade": 0,
    }
    assert snapshot["summary"]["budget_scope_counts"]["daemon"]["saturated"] == 1
    assert snapshot["summary"]["pressure_by_role"]["daemon"] == 1
    assert snapshot["queue"][0]["queue_name"] == "daemon_admission"
    assert snapshot["queue"][0]["queue_state"] == "defer"
    assert snapshot["resource_budgets"][0]["budget_key"] == "daemon:max_concurrent"
    assert snapshot["resource_budgets"][0]["budget_state"] == "saturated"
    assert snapshot["resource_budgets"][0]["subject_kind"] == "daemon"
    assert snapshot["pressure_signals"][0]["pressure_kind"] == "concurrency"
    assert snapshot["pressure_signals"][0]["subject_kind"] == "daemon"
    assert snapshot["admission_decisions"][0]["decision"] == "defer"


def test_build_execution_substrate_snapshot_tracks_worker_and_verifier_budget_scopes(
    tmp_path: Path,
) -> None:
    from spec_orch.services.admission_governor import AdmissionGovernor
    from spec_orch.services.execution_substrate import build_execution_substrate_snapshot

    governor = AdmissionGovernor(
        tmp_path,
        max_concurrent=3,
        worker_max_concurrent=1,
        verifier_max_concurrent=1,
    )
    governor.record_decision(
        governor.evaluate_issue(
            "mission-412",
            workspace_id="mission-412",
            in_progress_count=0,
            mission_in_progress_count=0,
            worker_in_progress_count=0,
            verifier_in_progress_count=1,
            is_hotfix=False,
            recorded_at="2026-04-03T10:10:00+00:00",
        )
    )
    governor.record_decision(
        governor.evaluate_issue(
            "mission-413",
            workspace_id="mission-413",
            in_progress_count=0,
            mission_in_progress_count=0,
            worker_in_progress_count=1,
            verifier_in_progress_count=0,
            is_hotfix=False,
            recorded_at="2026-04-03T10:11:00+00:00",
        )
    )

    snapshot = build_execution_substrate_snapshot(tmp_path)

    assert snapshot["summary"]["admission_decision_counts"]["degrade"] == 1
    assert snapshot["summary"]["admission_decision_counts"]["reject"] == 1
    assert snapshot["summary"]["budget_scope_counts"]["verifier"]["saturated"] == 1
    assert snapshot["summary"]["budget_scope_counts"]["worker"]["saturated"] == 1
    assert snapshot["summary"]["pressure_by_role"]["verifier"] == 1
    assert snapshot["summary"]["pressure_by_role"]["worker"] == 1
    assert {
        item["subject_kind"]
        for item in snapshot["resource_budgets"]
        if item["budget_state"] == "saturated"
    } >= {"worker", "verifier"}
