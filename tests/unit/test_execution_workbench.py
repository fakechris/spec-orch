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


def test_build_mission_execution_workbench_surfaces_workspace_local_execution_state(
    tmp_path: Path,
) -> None:
    from spec_orch.services.execution_workbench import build_mission_execution_workbench

    mission_id = "mission-execution-workbench"
    specs_dir = tmp_path / "docs" / "specs" / mission_id
    operator_dir = specs_dir / "operator"
    chain_root = operator_dir / "runtime_chain"
    chain_root.mkdir(parents=True)

    write_chain_status(
        chain_root,
        RuntimeChainStatus(
            chain_id="chain-mission-execution-workbench",
            active_span_id="chain-mission-execution-workbench:acceptance",
            subject_kind=RuntimeSubjectKind.ACCEPTANCE,
            subject_id=mission_id,
            phase=ChainPhase.HEARTBEAT,
            status_reason="acceptance_waiting_on_model",
            updated_at="2026-04-03T00:10:00+00:00",
        ),
    )
    append_chain_event(
        chain_root,
        RuntimeChainEvent(
            chain_id="chain-mission-execution-workbench",
            span_id="chain-mission-execution-workbench:acceptance:start",
            parent_span_id=None,
            subject_kind=RuntimeSubjectKind.ACCEPTANCE,
            subject_id=mission_id,
            phase=ChainPhase.STARTED,
            status_reason="acceptance_started",
            updated_at="2026-04-03T00:09:00+00:00",
        ),
    )
    append_chain_event(
        chain_root,
        RuntimeChainEvent(
            chain_id="chain-mission-execution-workbench",
            span_id="chain-mission-execution-workbench:acceptance:heartbeat",
            parent_span_id="chain-mission-execution-workbench:acceptance:start",
            subject_kind=RuntimeSubjectKind.ACCEPTANCE,
            subject_id=mission_id,
            phase=ChainPhase.HEARTBEAT,
            status_reason="acceptance_waiting_on_model",
            session_refs={"runtime_id": "runtime:local", "agent_id": "acceptance_evaluator"},
            updated_at="2026-04-03T00:10:00+00:00",
        ),
    )

    with (operator_dir / "interventions.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "intervention_id": "intervention-execution-workbench",
                    "point_key": "scope_gate",
                    "summary": "Review the scope gate mismatch.",
                    "questions": ["Should the round continue?"],
                    "status": "open",
                    "created_at": "2026-04-03T00:09:30+00:00",
                    "decision_record_id": "decision-execution-workbench",
                    "mission_id": mission_id,
                    "round_id": 1,
                    "review_route": f"/?mission={mission_id}&mode=missions&tab=approvals&round=1",
                }
            )
            + "\n"
        )

    write_live_summary(
        operator_dir / "observability" / "round-01-acceptance-graph",
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
                recent_token_growth=900,
                justified=False,
            ),
            stall_signal=RuntimeStallSignal(
                stalled=True,
                idle_seconds=22,
                reason="operator_wait",
                diminishing_returns=True,
                repeated_steps=2,
            ),
            updated_at="2026-04-03T00:10:30+00:00",
        ),
    )
    round_dir = specs_dir / "rounds" / "round-01"
    round_dir.mkdir(parents=True)
    (round_dir / "browser_evidence.json").write_text(
        json.dumps(
            {
                "mission_id": mission_id,
                "round_id": 1,
                "tested_routes": ["/", f"/?mission={mission_id}&mode=missions&tab=execution"],
                "interactions": {
                    "/": [
                        {
                            "action": "click_selector",
                            "description": "Open the launcher.",
                            "status": "passed",
                        }
                    ]
                },
                "screenshots": {
                    "/": str(round_dir / "visual" / "root.png"),
                },
                "console_errors": [],
                "page_errors": [],
                "artifact_paths": {
                    "round_dir": str(round_dir),
                    "visual_dir": str(round_dir / "visual"),
                },
            }
        ),
        encoding="utf-8",
    )
    worker_dir = specs_dir / "workers" / "packet-one"
    telemetry_dir = worker_dir / "telemetry"
    telemetry_dir.mkdir(parents=True)
    (worker_dir / "builder_report.json").write_text(
        json.dumps(
            {
                "adapter": "acpx_worker",
                "agent": "opencode",
                "model": "minimax/MiniMax-M2.5",
                "succeeded": True,
                "exit_code": 0,
                "event_count": 3,
                "session_name": "worker-session-packet-one",
                "terminal_reason": "process_exit_success",
                "commands_completed": 2,
                "files_changed": [],
                "retry_count": 0,
                "session_reused": False,
                "session_recycled": False,
                "session_health": "healthy",
                "chain_id": "chain-mission-execution-workbench",
                "span_id": "chain-mission-execution-workbench:packet-one:worker",
                "parent_span_id": "chain-mission-execution-workbench:packet-one",
            }
        ),
        encoding="utf-8",
    )
    (telemetry_dir / "activity.log").write_text(
        "[00:09:00] MISSION_ Started packet packet-one\n"
        "[00:10:00] MISSION_ Completed packet packet-one\n",
        encoding="utf-8",
    )
    (telemetry_dir / "events.jsonl").write_text(
        json.dumps(
            {
                "timestamp": "2026-04-03T00:10:00+00:00",
                "component": "builder",
                "event_type": "session/update",
                "message": "event:session/update",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    payload = build_mission_execution_workbench(tmp_path, mission_id, ["resume", "stop", "rerun"])

    assert payload["overview"] == {
        "active_work_count": 1,
        "queued_count": 1,
        "open_intervention_count": 1,
        "runtime_count": 1,
        "agent_count": 1,
        "current_phase": "heartbeat",
        "current_health": "active",
        "last_event_summary": "acceptance_waiting_on_model",
    }
    assert payload["active_work"][0]["workspace_id"] == mission_id
    assert payload["active_work"][0]["phase"] == "heartbeat"
    assert payload["event_trail"][0]["event_type"] == "started"
    assert payload["event_trail"][-1]["event_summary"] == "acceptance_waiting_on_model"
    assert payload["queue"][0]["queue_name"] == "operator_intervention"
    assert payload["interventions"][0]["action"] == "scope_gate"
    assert payload["runtime"]["runtime_id"] == "runtime:local"
    assert payload["agents"][0]["agent_id"] == "acceptance_evaluator"
    assert payload["available_actions"] == ["resume", "stop", "rerun"]
    assert payload["browser_panel"]["status"] == "available"
    assert payload["browser_panel"]["tested_route_count"] == 2
    assert payload["browser_panel"]["recent_interactions"][0]["status"] == "passed"
    assert payload["terminal_panel"]["status"] == "available"
    assert payload["terminal_panel"]["session_count"] == 1
    assert payload["terminal_panel"]["sessions"][0]["packet_id"] == "packet-one"
    assert payload["terminal_panel"]["sessions"][0]["terminal_reason"] == "process_exit_success"
    assert payload["review_route"] == (
        f"/?mission={mission_id}&mode=missions&tab=execution"
    )


def test_build_execution_workbench_surfaces_global_active_work_agents_and_runtimes(
    tmp_path: Path,
) -> None:
    from spec_orch.services.execution_workbench import build_execution_workbench

    mission_id = "mission-global-execution"
    mission_operator_dir = tmp_path / "docs" / "specs" / mission_id / "operator"
    mission_chain_root = mission_operator_dir / "runtime_chain"
    mission_chain_root.mkdir(parents=True)
    write_chain_status(
        mission_chain_root,
        RuntimeChainStatus(
            chain_id="chain-global-execution",
            active_span_id="chain-global-execution:acceptance",
            subject_kind=RuntimeSubjectKind.ACCEPTANCE,
            subject_id=mission_id,
            phase=ChainPhase.HEARTBEAT,
            status_reason="acceptance_waiting_on_model",
            updated_at="2026-04-03T01:10:00+00:00",
        ),
    )
    append_chain_event(
        mission_chain_root,
        RuntimeChainEvent(
            chain_id="chain-global-execution",
            span_id="chain-global-execution:acceptance:start",
            parent_span_id=None,
            subject_kind=RuntimeSubjectKind.ACCEPTANCE,
            subject_id=mission_id,
            phase=ChainPhase.STARTED,
            status_reason="acceptance_started",
            updated_at="2026-04-03T01:09:00+00:00",
        ),
    )
    append_chain_event(
        mission_chain_root,
        RuntimeChainEvent(
            chain_id="chain-global-execution",
            span_id="chain-global-execution:acceptance:heartbeat",
            parent_span_id="chain-global-execution:acceptance:start",
            subject_kind=RuntimeSubjectKind.ACCEPTANCE,
            subject_id=mission_id,
            phase=ChainPhase.HEARTBEAT,
            status_reason="acceptance_waiting_on_model",
            session_refs={"runtime_id": "runtime:local", "agent_id": "acceptance_evaluator"},
            updated_at="2026-04-03T01:10:00+00:00",
        ),
    )

    issue_chain_root = tmp_path / ".worktrees" / "SPC-384" / "telemetry" / "runtime_chain"
    issue_chain_root.mkdir(parents=True)
    write_chain_status(
        issue_chain_root,
        RuntimeChainStatus(
            chain_id="chain-spc-384",
            active_span_id="chain-spc-384:issue:gate",
            subject_kind=RuntimeSubjectKind.ISSUE,
            subject_id="SPC-384",
            phase=ChainPhase.DEGRADED,
            status_reason="gate_blocked",
            updated_at="2026-04-03T01:11:00+00:00",
        ),
    )

    with (mission_operator_dir / "interventions.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "intervention_id": "intervention-global-execution",
                    "point_key": "scope_gate",
                    "summary": "Review the scope gate mismatch.",
                    "questions": ["Should the round continue?"],
                    "status": "open",
                    "created_at": "2026-04-03T01:09:30+00:00",
                    "decision_record_id": "decision-global-execution",
                    "mission_id": mission_id,
                    "round_id": 1,
                    "review_route": f"/?mission={mission_id}&mode=missions&tab=approvals&round=1",
                }
            )
            + "\n"
        )

    write_live_summary(
        mission_operator_dir / "observability" / "round-01-acceptance-graph",
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
                recent_token_growth=900,
                justified=False,
            ),
            stall_signal=RuntimeStallSignal(
                stalled=True,
                idle_seconds=22,
                reason="operator_wait",
                diminishing_returns=True,
                repeated_steps=2,
            ),
            updated_at="2026-04-03T01:10:30+00:00",
        ),
    )
    round_dir = tmp_path / "docs" / "specs" / mission_id / "rounds" / "round-01"
    round_dir.mkdir(parents=True)
    (round_dir / "browser_evidence.json").write_text(
        json.dumps(
            {
                "mission_id": mission_id,
                "round_id": 1,
                "tested_routes": ["/"],
                "interactions": {"/": []},
                "screenshots": {"/": str(round_dir / "visual" / "root.png")},
                "console_errors": [],
                "page_errors": [],
                "artifact_paths": {
                    "round_dir": str(round_dir),
                    "visual_dir": str(round_dir / "visual"),
                },
            }
        ),
        encoding="utf-8",
    )
    worker_dir = tmp_path / "docs" / "specs" / mission_id / "workers" / "packet-global"
    telemetry_dir = worker_dir / "telemetry"
    telemetry_dir.mkdir(parents=True)
    (worker_dir / "builder_report.json").write_text(
        json.dumps(
            {
                "adapter": "acpx_worker",
                "agent": "opencode",
                "model": "minimax/MiniMax-M2.5",
                "succeeded": True,
                "exit_code": 0,
                "event_count": 3,
                "session_name": "worker-session-global",
                "terminal_reason": "process_exit_success",
                "commands_completed": 1,
                "files_changed": [],
                "retry_count": 0,
                "session_reused": False,
                "session_recycled": False,
                "session_health": "healthy",
                "chain_id": "chain-global-execution",
                "span_id": "chain-global-execution:packet-global:worker",
                "parent_span_id": "chain-global-execution:packet-global",
            }
        ),
        encoding="utf-8",
    )
    (telemetry_dir / "activity.log").write_text(
        "[01:09:00] MISSION_ Started packet packet-global\n",
        encoding="utf-8",
    )
    (telemetry_dir / "events.jsonl").write_text(
        json.dumps(
            {
                "timestamp": "2026-04-03T01:09:00+00:00",
                "component": "builder",
                "event_type": "session/prompt",
                "message": "event:session/prompt",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    payload = build_execution_workbench(tmp_path)

    assert payload["summary"] == {
        "running_count": 1,
        "queued_count": 1,
        "stalled_count": 1,
        "degraded_runtime_count": 1,
        "intervention_needed_count": 2,
    }
    assert len(payload["active_work"]) == 2
    assert any(item["workspace_id"] == mission_id for item in payload["active_work"])
    assert any(item["workspace_id"] == "SPC-384" for item in payload["active_work"])
    assert {item["agent_id"] for item in payload["agents"]} == {
        "acceptance_evaluator",
        "run_controller",
    }
    assert payload["runtimes"][0]["runtime_id"] == "runtime:local"
    assert payload["queue"][0]["queue_name"] == "operator_intervention"
    assert payload["interventions"][0]["action"] == "scope_gate"
    assert payload["pressure_signals"][0]["pressure_kind"] == "stall"
    assert payload["browser_surfaces"][0]["workspace_id"] == mission_id
    assert payload["browser_surfaces"][0]["tested_route_count"] == 1
    assert payload["terminal_surfaces"][0]["workspace_id"] == mission_id
    assert payload["terminal_surfaces"][0]["session_count"] == 1
    assert payload["review_route"] == "/?mode=execution"
