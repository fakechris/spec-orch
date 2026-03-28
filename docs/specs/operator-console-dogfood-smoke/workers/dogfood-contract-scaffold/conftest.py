"""Base test fixtures for SpecOrch Mission Dashboard integration tests."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# =============================================================================
# Test Data Factories
# =============================================================================


def create_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_uuid() -> str:
    return str(uuid.uuid4())


# =============================================================================
# Mission Fixtures
# =============================================================================


def create_mission_detail_fixture(
    mission_id: str = "test-mission-001",
    title: str = "Test Mission",
    status: str = "in_progress",
    round_id: int = 1,
) -> dict[str, Any]:
    return {
        "mission": {
            "mission_id": mission_id,
            "title": title,
            "status": status,
            "created_at": create_timestamp(),
            "approved_at": create_timestamp(),
            "completed_at": None,
            "acceptance_criteria": [
                "Test criterion 1",
                "Test criterion 2",
            ],
            "constraints": ["constraint-1", "constraint-2"],
            "spec_path": f"docs/specs/{mission_id}/spec.md",
        },
        "lifecycle": {
            "phase": status,
            "current_round": round_id,
            "issue_ids": ["issue-001", "issue-002"],
            "completed_issues": ["issue-001"],
            "updated_at": create_timestamp(),
        },
        "current_round": round_id,
        "rounds": [create_round_fixture(round_id=round_id)],
        "packets": [
            {
                "packet_id": "packet-001",
                "title": "Test Packet 1",
                "wave_id": 1,
                "run_class": "feature",
                "linear_issue_id": "ISSUE-001",
                "depends_on": [],
                "files_in_scope": ["src/test.py"],
            },
            {
                "packet_id": "packet-002",
                "title": "Test Packet 2",
                "wave_id": 1,
                "run_class": "feature",
                "linear_issue_id": "ISSUE-002",
                "depends_on": ["packet-001"],
                "files_in_scope": ["src/test2.py"],
            },
        ],
        "actions": ["approve", "resume", "stop"],
        "approval_request": create_approval_request_fixture(round_id=round_id),
        "approval_history": [create_approval_history_entry_fixture()],
        "approval_state": {
            "status": "awaiting_human",
            "summary": "Awaiting operator decision",
            "latest_action": create_approval_history_entry_fixture(),
        },
        "visual_qa": create_visual_qa_fixture(mission_id),
        "costs": create_mission_costs_fixture(mission_id),
        "artifacts": {
            "spec": f"docs/specs/{mission_id}/spec.md",
            "plan": f"docs/specs/{mission_id}/plan.json",
            "rounds_dir": f"docs/specs/{mission_id}/rounds",
        },
    }


def create_mission_costs_fixture(
    mission_id: str = "test-mission-001",
    total_cost: float = 12.50,
    budget_status: str = "healthy",
) -> dict[str, Any]:
    return {
        "mission_id": mission_id,
        "summary": {
            "workers": 2,
            "input_tokens": 50000,
            "output_tokens": 25000,
            "cost_usd": total_cost,
            "budget_status": budget_status,
            "thresholds": {"warning_usd": 10.0, "critical_usd": 50.0},
            "incident_count": 0,
            "remaining_budget_usd": 37.5,
        },
        "review_route": f"/?mission={mission_id}&mode=missions&tab=costs",
        "focus_packet_id": "packet-002",
        "highest_cost_worker": {
            "packet_id": "packet-002",
            "cost_usd": 7.25,
            "report_path": f"docs/specs/{mission_id}/workers/packet-002/builder_report.json",
            "transcript_route": f"/?mission={mission_id}&mode=missions&tab=transcript&packet=packet-002",
        },
        "incidents": [],
        "workers": [
            {
                "packet_id": "packet-001",
                "report_path": f"docs/specs/{mission_id}/workers/packet-001/builder_report.json",
                "adapter": "codex_exec",
                "turn_status": "completed",
                "input_tokens": 20000,
                "output_tokens": 10000,
                "cost_usd": 5.25,
                "transcript_route": f"/?mission={mission_id}&mode=missions&tab=transcript&packet=packet-001",
            },
            {
                "packet_id": "packet-002",
                "report_path": f"docs/specs/{mission_id}/workers/packet-002/builder_report.json",
                "adapter": "codex_exec",
                "turn_status": "completed",
                "input_tokens": 30000,
                "output_tokens": 15000,
                "cost_usd": 7.25,
                "transcript_route": f"/?mission={mission_id}&mode=missions&tab=transcript&packet=packet-002",
            },
        ],
    }


# =============================================================================
# Round Fixtures
# =============================================================================


def create_round_fixture(round_id: int = 1, wave_id: int = 1) -> dict[str, Any]:
    return {
        "round_id": round_id,
        "wave_id": wave_id,
        "status": "completed",
        "started_at": create_timestamp(),
        "completed_at": create_timestamp(),
        "worker_results": [
            {
                "packet_id": "packet-001",
                "exit_code": 0,
                "stdout": "Build successful",
                "stderr": "",
            },
        ],
        "decision": create_round_decision_fixture(),
        "paths": {
            "round_dir": f"docs/specs/test-mission-001/rounds/round-{round_id}",
            "review_memo": f"docs/specs/test-mission-001/rounds/round-{round_id}/supervisor_review.md",
            "visual_evaluation": f"docs/specs/test-mission-001/rounds/round-{round_id}/visual_evaluation.json",
        },
    }


def create_round_decision_fixture(
    action: str = "ask_human",
    summary: str = "Human approval required for this round",
) -> dict[str, Any]:
    return {
        "action": action,
        "reason_code": "HUMAN_REVIEW_REQUIRED",
        "summary": summary,
        "confidence": 0.95,
        "affected_workers": ["packet-001"],
        "artifacts": {
            "review_memo": "docs/specs/test-mission-001/rounds/round-1/supervisor_review.md",
        },
        "session_ops": {
            "reuse": ["packet-001"],
            "spawn": [],
            "cancel": [],
        },
        "blocking_questions": ["Should we proceed with this implementation approach?"],
    }


# =============================================================================
# Approval Fixtures
# =============================================================================


def create_approval_request_fixture(round_id: int = 1) -> dict[str, Any]:
    return {
        "round_id": round_id,
        "timestamp": create_timestamp(),
        "summary": "Human approval required for this round.",
        "blocking_question": "Should we proceed with this implementation approach?",
        "decision_action": "ask_human",
        "review_route": f"/?mission=test-mission-001&mode=missions&tab=approvals&round={round_id}",
        "actions": [
            {
                "key": "approve",
                "label": "Approve",
                "message": "@approve Should we proceed with this implementation approach?",
            },
            {
                "key": "request_revision",
                "label": "Request revision",
                "message": "@request-revision Please revise this round before rollout.",
            },
            {
                "key": "ask_followup",
                "label": "Ask follow-up",
                "message": "@follow-up I need more detail before approving this round.",
            },
        ],
    }


def create_approval_history_entry_fixture(
    action_key: str = "approve",
    status: str = "applied",
) -> dict[str, Any]:
    return {
        "timestamp": create_timestamp(),
        "action_key": action_key,
        "label": "Approve",
        "message": "@approve Should we proceed with this implementation approach?",
        "channel": "web-dashboard",
        "status": status,
        "effect": "approval_granted" if action_key == "approve" else "guidance_sent",
    }


# =============================================================================
# Visual QA Fixtures
# =============================================================================


def create_visual_qa_fixture(mission_id: str = "test-mission-001") -> dict[str, Any]:
    return {
        "mission_id": mission_id,
        "summary": {
            "total_rounds": 1,
            "blocking_findings": 0,
            "warning_findings": 1,
            "latest_confidence": 0.85,
            "blocking_rounds": [],
            "gallery_items": 2,
            "diff_items": 1,
            "comparison_rounds": 1,
            "focus_transcript_route": f"/?mission={mission_id}&mode=missions&tab=transcript&packet=packet-001",
        },
        "review_route": f"/?mission={mission_id}&mode=missions&tab=visual",
        "rounds": [
            {
                "round_id": 1,
                "summary": "Visual inspection passed with minor warnings",
                "confidence": 0.85,
                "status": "warning",
                "artifact_path": f"docs/specs/{mission_id}/rounds/round-1/visual_evaluation.json",
                "findings": [
                    {
                        "severity": "warning",
                        "description": "Minor layout shift detected on mobile viewport",
                        "file_path": "src/styles.css",
                        "line": 42,
                        "suggested_action": "Review responsive breakpoints",
                    },
                ],
                "artifacts": {
                    "desktop_diff": f"docs/specs/{mission_id}/rounds/round-1/screenshots/desktop-diff.png",
                    "mobile_screenshot": f"docs/specs/{mission_id}/rounds/round-1/screenshots/mobile.png",
                },
                "gallery": [
                    {
                        "label": "Desktop Diff",
                        "path": f"docs/specs/{mission_id}/rounds/round-1/screenshots/desktop-diff.png",
                        "kind": "diff",
                    },
                    {
                        "label": "Mobile Screenshot",
                        "path": f"docs/specs/{mission_id}/rounds/round-1/screenshots/mobile.png",
                        "kind": "image",
                    },
                ],
                "primary_artifact": f"docs/specs/{mission_id}/rounds/round-1/screenshots/desktop-diff.png",
                "comparison": {
                    "mode": "diff-first",
                    "primary": {
                        "label": "Desktop Diff",
                        "path": f"docs/specs/{mission_id}/rounds/round-1/screenshots/desktop-diff.png",
                        "kind": "diff",
                    },
                    "related": [
                        {
                            "label": "Mobile Screenshot",
                            "path": f"docs/specs/{mission_id}/rounds/round-1/screenshots/mobile.png",
                            "kind": "image",
                        },
                    ],
                },
                "transcript_routes": [
                    f"/?mission={mission_id}&mode=missions&tab=transcript&packet=packet-001",
                ],
                "review_route": f"/?mission={mission_id}&mode=missions&tab=visual&round=1",
            },
        ],
    }


# =============================================================================
# Transcript Fixtures
# =============================================================================


def create_transcript_fixture(
    mission_id: str = "test-mission-001",
    packet_id: str = "packet-001",
) -> dict[str, Any]:
    return {
        "mission_id": mission_id,
        "packet_id": packet_id,
        "entries": [
            {
                "kind": "activity",
                "timestamp": "2026-03-27T10:00:00+00:00",
                "message": "Started packet packet-001",
                "raw": "2026-03-27T10:00:00+00:00 Started packet packet-001",
                "source_path": f"docs/specs/{mission_id}/workers/{packet_id}/telemetry/activity.log",
            },
            {
                "kind": "event",
                "timestamp": "2026-03-27T10:00:01+00:00",
                "message": "event:initialize",
                "event_type": "initialize",
                "raw": {
                    "timestamp": "2026-03-27T10:00:01+00:00",
                    "event_type": "initialize",
                    "component": "builder",
                },
                "source_path": f"docs/specs/{mission_id}/workers/{packet_id}/telemetry/events.jsonl",
            },
            {
                "kind": "event",
                "timestamp": "2026-03-27T10:00:05+00:00",
                "message": "mission_packet_started",
                "event_type": "mission_packet_started",
                "raw": {
                    "timestamp": "2026-03-27T10:00:05+00:00",
                    "event_type": "mission_packet_started",
                    "component": "mission_worker",
                    "data": {
                        "mission_id": mission_id,
                        "round_id": 1,
                        "packet_id": packet_id,
                    },
                },
                "source_path": f"docs/specs/{mission_id}/workers/{packet_id}/telemetry/events.jsonl",
            },
        ],
        "summary": {
            "entry_count": 3,
            "kind_counts": {"activity": 1, "event": 2},
            "block_counts": {"milestone": 1, "event": 2},
            "latest_timestamp": "2026-03-27T10:00:05+00:00",
            "operator_readout": "1 milestones, 0 tool blocks, 0 alerts, latest signal at 2026-03-27T10:00:05+00:00",
        },
        "milestones": [
            {
                "timestamp": "2026-03-27T10:00:05+00:00",
                "event_type": "mission_packet_started",
                "message": "mission_packet_started",
            },
        ],
        "blocks": [
            {
                "block_type": "activity",
                "emphasis": "log",
                "timestamp": "2026-03-27T10:00:00+00:00",
                "title": "Started packet packet-001",
                "body": "2026-03-27T10:00:00+00:00 Started packet packet-001",
                "source_path": f"docs/specs/{mission_id}/workers/{packet_id}/telemetry/activity.log",
                "jump_targets": [
                    {
                        "kind": "source",
                        "label": "Activity log",
                        "path": f"docs/specs/{mission_id}/workers/{packet_id}/telemetry/activity.log",
                        "href": f"/artifacts/docs/specs/{mission_id}/workers/{packet_id}/telemetry/activity.log",
                    },
                ],
            },
            {
                "block_type": "milestone",
                "emphasis": "milestone",
                "timestamp": "2026-03-27T10:00:05+00:00",
                "title": "mission_packet_started",
                "body": "mission_packet_started",
                "source_path": f"docs/specs/{mission_id}/workers/{packet_id}/telemetry/events.jsonl",
                "details": {
                    "data": {
                        "mission_id": mission_id,
                        "round_id": 1,
                        "packet_id": packet_id,
                    },
                },
                "jump_targets": [
                    {
                        "kind": "source",
                        "label": "Events stream",
                        "path": f"docs/specs/{mission_id}/workers/{packet_id}/telemetry/events.jsonl",
                        "href": f"/artifacts/docs/specs/{mission_id}/workers/{packet_id}/telemetry/events.jsonl",
                    },
                ],
            },
        ],
        "telemetry": {
            "activity_log": f"docs/specs/{mission_id}/workers/{packet_id}/telemetry/activity.log",
            "events": f"docs/specs/{mission_id}/workers/{packet_id}/telemetry/events.jsonl",
            "incoming": f"docs/specs/{mission_id}/workers/{packet_id}/telemetry/incoming_events.jsonl",
        },
    }


# =============================================================================
# HumanInterventionRequest Fixtures
# =============================================================================


def create_human_intervention_fixture(
    mission_id: str = "test-mission-001",
    round_id: int = 1,
    intervention_id: str | None = None,
) -> dict[str, Any]:
    if intervention_id is None:
        intervention_id = create_uuid()

    return {
        "intervention_id": intervention_id,
        "mission_id": mission_id,
        "round_id": round_id,
        "intervention_type": "ask_human",
        "timestamp": create_timestamp(),
        "summary": "Human approval required for this round.",
        "blocking_question": "Should we proceed with this implementation approach?",
        "context": {
            "current_round": round_id,
            "wave_id": 1,
            "packet_id": "packet-001",
        },
        "available_actions": [
            {
                "key": "approve",
                "label": "Approve",
                "message": "@approve Should we proceed with this implementation approach?",
            },
            {
                "key": "request_revision",
                "label": "Request revision",
                "message": "@request-revision Please revise this round before rollout.",
            },
            {
                "key": "ask_followup",
                "label": "Ask follow-up",
                "message": "@follow-up I need more detail before approving this round.",
            },
        ],
        "status": "pending",
    }


# =============================================================================
# Daemon Pickup Fixtures
# =============================================================================


def create_daemon_pickup_result_fixture(
    issue_id: str = "ISSUE-001",
    success: bool = True,
    mission_id: str | None = "test-mission-001",
) -> dict[str, Any]:
    return {
        "success": success,
        "issue_id": issue_id,
        "mission_id": mission_id,
        "is_hotfix": False,
        "error": None,
        "claim": {
            "issue_id": issue_id,
            "claimed_at": create_timestamp(),
            "lockfile_path": f".spec_orch_locks/{issue_id}.lock",
        },
    }


# =============================================================================
# Test Helper Functions
# =============================================================================


def write_test_mission_files(repo_root: Path, mission_id: str) -> None:
    mission_dir = repo_root / "docs" / "specs" / mission_id
    rounds_dir = mission_dir / "rounds"
    workers_dir = mission_dir / "workers"

    mission_dir.mkdir(parents=True, exist_ok=True)
    rounds_dir.mkdir(parents=True, exist_ok=True)
    workers_dir.mkdir(parents=True, exist_ok=True)

    spec_path = mission_dir / "spec.md"
    if not spec_path.exists():
        spec_path.write_text(f"# {mission_id}\n\n## Intent\nTest mission.\n")

    round_dir = rounds_dir / "round-1"
    round_dir.mkdir(parents=True, exist_ok=True)

    round_summary = round_dir / "round_summary.json"
    if not round_summary.exists():
        round_summary.write_text(json.dumps(create_round_fixture(), indent=2))

    review_memo = round_dir / "supervisor_review.md"
    if not review_memo.exists():
        review_memo.write_text("# Supervisor Review\n\nHuman approval required.\n")

    visual_eval = round_dir / "visual_evaluation.json"
    if not visual_eval.exists():
        visual_eval.write_text(json.dumps(create_visual_qa_fixture(mission_id), indent=2))

    operator_dir = mission_dir / "operator"
    operator_dir.mkdir(parents=True, exist_ok=True)

    approval_actions = operator_dir / "approval_actions.jsonl"
    if not approval_actions.exists():
        approval_actions.write_text(json.dumps(create_approval_history_entry_fixture()) + "\n")

    packet_dir = workers_dir / "packet-001"
    packet_dir.mkdir(parents=True, exist_ok=True)

    telemetry_dir = packet_dir / "telemetry"
    telemetry_dir.mkdir(parents=True, exist_ok=True)

    activity_log = telemetry_dir / "activity.log"
    if not activity_log.exists():
        activity_log.write_text("2026-03-27T10:00:00+00:00 Started packet packet-001\n")

    events_jsonl = telemetry_dir / "events.jsonl"
    if not events_jsonl.exists():
        events_jsonl.write_text(
            json.dumps(
                {
                    "timestamp": "2026-03-27T10:00:01+00:00",
                    "event_type": "initialize",
                    "component": "builder",
                }
            )
            + "\n"
        )

    builder_report = packet_dir / "builder_report.json"
    if not builder_report.exists():
        builder_report.write_text(
            json.dumps(
                {
                    "metadata": {
                        "usage": {
                            "input_tokens": 20000,
                            "output_tokens": 10000,
                        },
                        "cost_usd": 5.25,
                        "turn_status": "completed",
                        "adapter": "codex_exec",
                    },
                },
                indent=2,
            )
        )


def compare_dictionaries(
    actual: dict[str, Any],
    expected: dict[str, Any],
    path: str = "",
) -> list[str]:
    differences = []

    all_keys = set(actual.keys()) | set(expected.keys())

    for key in all_keys:
        current_path = f"{path}.{key}" if path else key

        if key not in actual:
            differences.append(f"Missing key in actual: {current_path}")
            continue

        if key not in expected:
            differences.append(f"Extra key in actual: {current_path}")
            continue

        actual_val = actual[key]
        expected_val = expected[key]

        if isinstance(expected_val, dict) and isinstance(actual_val, dict):
            differences.extend(compare_dictionaries(actual_val, expected_val, current_path))
        elif isinstance(expected_val, list) and isinstance(actual_val, list):
            if len(expected_val) != len(actual_val):
                differences.append(
                    f"List length mismatch at {current_path}: "
                    f"expected {len(expected_val)}, got {len(actual_val)}"
                )
            else:
                for i, (a_item, e_item) in enumerate(zip(actual_val, expected_val)):
                    if isinstance(e_item, dict) and isinstance(a_item, dict):
                        differences.extend(
                            compare_dictionaries(a_item, e_item, f"{current_path}[{i}]")
                        )
                    elif a_item != e_item:
                        differences.append(
                            f"Value mismatch at {current_path}[{i}]: expected {e_item}, got {a_item}"
                        )
        elif actual_val != expected_val:
            differences.append(
                f"Value mismatch at {current_path}: expected {expected_val}, got {actual_val}"
            )

    return differences
