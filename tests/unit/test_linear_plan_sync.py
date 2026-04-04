from __future__ import annotations

import json
from pathlib import Path


def test_build_linear_plan_sync_reads_compact_plan_snapshot(tmp_path: Path) -> None:
    from spec_orch.dashboard.launcher import _create_mission_draft
    from spec_orch.services.linear_plan_sync import build_linear_plan_sync

    _create_mission_draft(
        tmp_path,
        {
            "title": "Plan Sync",
            "mission_id": "plan-sync",
            "problem": "Linear drifts from local execution state.",
            "goal": "Mirror compact plan state into Linear.",
            "intent": "Sync plan state.",
            "acceptance_criteria": ["Linear shows a compact plan snapshot."],
            "constraints": [],
            "evidence_expectations": ["plan snapshot"],
        },
    )

    (tmp_path / "docs" / "specs" / "plan-sync" / "plan.json").write_text(
        json.dumps(
            {
                "plan_id": "plan-1",
                "mission_id": "plan-sync",
                "status": "draft",
                "waves": [
                    {
                        "wave_number": 0,
                        "description": "Scaffold contracts",
                        "work_packets": [
                            {
                                "packet_id": "pkt-1",
                                "title": "Contract A",
                                "linear_issue_id": "SON-1",
                            },
                            {"packet_id": "pkt-2", "title": "Contract B", "linear_issue_id": None},
                        ],
                    },
                    {
                        "wave_number": 1,
                        "description": "Execution workbench",
                        "work_packets": [
                            {
                                "packet_id": "pkt-3",
                                "title": "Workbench",
                                "linear_issue_id": "SON-3",
                            },
                        ],
                    },
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "specs" / "plan-sync" / "operator" / "launch.json").write_text(
        json.dumps({"metadata": {"launcher_path": "create_linear_issue_then_launch"}}, indent=2)
        + "\n",
        encoding="utf-8",
    )

    snapshot = build_linear_plan_sync(tmp_path, "plan-sync")

    assert snapshot["plan_state"] == "draft"
    assert snapshot["plan_id"] == "plan-1"
    assert snapshot["wave_count"] == 2
    assert snapshot["packet_count"] == 3
    assert snapshot["linked_packet_count"] == 2
    assert snapshot["launcher_path"] == "create_linear_issue_then_launch"
    assert snapshot["plan_summary"] == [
        "Plan status: draft.",
        "Waves: 2; packets: 3; Linear-linked packets: 2.",
        "Current focus: W0 - Scaffold contracts.",
        "Launcher path: create_linear_issue_then_launch.",
    ]


def test_build_linear_mirror_for_mission_projects_plan_sync_into_mirror(tmp_path: Path) -> None:
    from spec_orch.dashboard.launcher import _create_mission_draft
    from spec_orch.services.linear_plan_sync import build_linear_mirror_for_mission

    _create_mission_draft(
        tmp_path,
        {
            "title": "Plan Sync",
            "mission_id": "plan-sync",
            "problem": "Linear drifts from local execution state.",
            "goal": "Mirror compact plan state into Linear.",
            "intent": "Sync plan state.",
            "acceptance_criteria": ["Linear shows a compact plan snapshot."],
            "constraints": [],
            "evidence_expectations": ["plan snapshot"],
        },
    )
    (tmp_path / "docs" / "specs" / "plan-sync" / "plan.json").write_text(
        json.dumps(
            {
                "plan_id": "plan-1",
                "mission_id": "plan-sync",
                "status": "draft",
                "waves": [
                    {"wave_number": 0, "description": "Scaffold contracts", "work_packets": []}
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    mirror = build_linear_mirror_for_mission(tmp_path, "plan-sync")

    assert mirror is not None
    assert mirror["next_action"] == "review_plan"
    assert mirror["plan_sync"]["plan_state"] == "draft"
    assert mirror["plan_summary"][0] == "Plan status: draft."
