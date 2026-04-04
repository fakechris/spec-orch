from __future__ import annotations

import json
from pathlib import Path


def test_mission_available_actions_supports_in_progress_status() -> None:
    from spec_orch.dashboard.missions import _mission_available_actions

    actions = _mission_available_actions("in_progress", None)

    assert actions == ["inject_guidance", "rerun", "resume", "stop"]


def test_mission_evidence_counts_prefers_decision_core_approval_history(tmp_path: Path) -> None:
    from spec_orch.dashboard.missions import _mission_evidence_counts

    repo_root = tmp_path
    specs_dir = repo_root / "docs" / "specs" / "mission-evidence"
    rounds_dir = specs_dir / "rounds"
    operator_dir = specs_dir / "operator"
    (rounds_dir / "round-01").mkdir(parents=True)
    operator_dir.mkdir(parents=True)

    (rounds_dir / "round-01" / "round_summary.json").write_text("{}", encoding="utf-8")
    (operator_dir / "intervention_responses.jsonl").write_text(
        json.dumps(
            {
                "timestamp": "2026-03-30T02:00:00+00:00",
                "intervention_id": "int-1",
                "decision_record_id": "mission-evidence-round-1-review",
                "action_key": "approve",
                "label": "Approve",
                "message": "@approve Approve this round.",
                "channel": "web-dashboard",
                "status": "applied",
                "effect": "approval_granted",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    counts = _mission_evidence_counts(repo_root, specs_dir)

    assert counts == {
        "round_count": 1,
        "visual_round_count": 0,
        "approval_action_count": 1,
    }


def test_gather_mission_detail_surfaces_failed_round_diagnostics(tmp_path: Path) -> None:
    from spec_orch.dashboard.missions import _gather_mission_detail

    repo_root = tmp_path
    mission_id = "mission-failure-detail"
    specs_dir = repo_root / "docs" / "specs" / mission_id
    round_dir = specs_dir / "rounds" / "round-02"
    specs_dir.mkdir(parents=True)
    round_dir.mkdir(parents=True)

    (specs_dir / "mission.json").write_text(
        json.dumps(
            {
                "mission_id": mission_id,
                "title": "Mission Failure Detail",
                "status": "approved",
                "spec_path": f"docs/specs/{mission_id}/spec.md",
                "acceptance_criteria": ["Surface failure state"],
                "constraints": ["Keep diagnostics visible"],
                "interface_contracts": [],
                "created_at": "2026-04-04T12:00:00+00:00",
                "approved_at": "2026-04-04T12:05:00+00:00",
                "completed_at": None,
            }
        ),
        encoding="utf-8",
    )
    (specs_dir / "spec.md").write_text("# Mission Failure Detail\n", encoding="utf-8")
    (round_dir / "round_summary.json").write_text(
        json.dumps(
            {
                "round_id": 2,
                "wave_id": 0,
                "status": "decided",
                "started_at": "2026-04-04T12:10:00+00:00",
                "completed_at": "2026-04-04T12:20:00+00:00",
                "worker_results": [
                    {
                        "packet_id": "pkt-a",
                        "title": "Scaffold mission types",
                        "report_path": f"docs/specs/{mission_id}/workers/pkt-a/builder_report.json",
                        "events_path": f"docs/specs/{mission_id}/workers/pkt-a/telemetry/events.jsonl",
                        "activity_log_path": (
                            f"docs/specs/{mission_id}/workers/pkt-a/telemetry/activity.log"
                        ),
                        "succeeded": False,
                    },
                    {
                        "packet_id": "pkt-b",
                        "title": "Scaffold artifact types",
                        "report_path": f"docs/specs/{mission_id}/workers/pkt-b/builder_report.json",
                        "events_path": f"docs/specs/{mission_id}/workers/pkt-b/telemetry/events.jsonl",
                        "activity_log_path": (
                            f"docs/specs/{mission_id}/workers/pkt-b/telemetry/activity.log"
                        ),
                        "succeeded": False,
                    },
                ],
                "decision": {
                    "action": "ask_human",
                    "reason_code": "missing_builder_diagnostics",
                    "summary": "Both builders failed twice. Inspect diagnostics before retrying.",
                    "confidence": "medium",
                    "affected_workers": [],
                    "artifacts": {},
                    "session_ops": {"reuse": [], "spawn": [], "cancel": []},
                    "blocking_questions": [
                        "What error did the builders report?",
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    (round_dir / "supervisor_review.md").write_text(
        "Investigate builder failures.\n", encoding="utf-8"
    )

    detail = _gather_mission_detail(repo_root, mission_id)

    assert detail is not None
    latest_round = detail["rounds"][-1]
    assert latest_round["failure_state"] == {
        "status": "attention_required",
        "decision_action": "ask_human",
        "reason_code": "missing_builder_diagnostics",
        "failed_worker_count": 2,
        "total_worker_count": 2,
        "summary": "Both builders failed twice. Inspect diagnostics before retrying.",
    }
    assert [item["label"] for item in latest_round["diagnostic_artifacts"]] == [
        "Builder report",
        "Telemetry events",
        "Activity log",
        "Builder report",
        "Telemetry events",
        "Activity log",
        "Supervisor review",
    ]
    assert detail["mission_health"] == {
        "status": "attention_required",
        "summary": "2 of 2 builders failed; inspect diagnostics before retrying.",
        "decision_action": "ask_human",
        "reason_code": "missing_builder_diagnostics",
        "failed_worker_count": 2,
        "total_worker_count": 2,
        "diagnostic_artifact_count": 7,
    }
