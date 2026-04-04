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


def test_build_linear_mirror_for_mission_projects_governance_sync(tmp_path: Path) -> None:
    from spec_orch.dashboard.launcher import _create_mission_draft
    from spec_orch.services.linear_plan_sync import build_linear_mirror_for_mission

    _create_mission_draft(
        tmp_path,
        {
            "title": "Governance Sync",
            "mission_id": "governance-sync",
            "problem": "Linear needs current governance state.",
            "goal": "Project acceptance, archive, and bottleneck into the mirror.",
            "intent": "Mirror governance state.",
            "acceptance_criteria": ["Linear shows the compact governance sync block."],
            "constraints": [],
            "evidence_expectations": ["governance sync"],
        },
    )
    (tmp_path / ".spec_orch" / "acceptance").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".spec_orch" / "acceptance" / "stability_acceptance_status.json").write_text(
        json.dumps({"summary": {"overall_status": "pass"}}, indent=2) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "acceptance-history").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "acceptance-history" / "index.json").write_text(
        json.dumps(
            {
                "releases": [
                    {
                        "release_id": "dogfood-wave-0",
                        "bundle_path": "docs/acceptance-history/releases/dogfood-wave-0",
                        "overall_status": "pass",
                    }
                ]
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "specs" / "governance-sync" / "plan.json").write_text(
        json.dumps(
            {
                "plan_id": "plan-1",
                "mission_id": "governance-sync",
                "status": "draft",
                "waves": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "specs" / "governance-sync" / "operator" / "launch.json").write_text(
        json.dumps(
            {
                "metadata": {"next_bottleneck": "Lifecycle"},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    mirror = build_linear_mirror_for_mission(tmp_path, "governance-sync")

    assert mirror is not None
    assert mirror["governance_sync"] == {
        "latest_acceptance_status": "pass",
        "latest_release_id": "dogfood-wave-0",
        "latest_release_bundle_path": "docs/acceptance-history/releases/dogfood-wave-0",
        "next_bottleneck": "Lifecycle",
    }


def test_collect_linear_mission_mirror_drifts_classifies_missing_and_stale_states(
    tmp_path: Path,
) -> None:
    from spec_orch.dashboard.launcher import _create_mission_draft
    from spec_orch.services.linear_mirror import render_linear_mirror_section
    from spec_orch.services.linear_plan_sync import (
        build_linear_mirror_for_mission,
        collect_linear_mission_mirror_drifts,
    )

    def _seed_bound_mission(mission_id: str, *, linear_issue_id: str) -> None:
        _create_mission_draft(
            tmp_path,
            {
                "title": mission_id,
                "mission_id": mission_id,
                "problem": "Mirror drift exists.",
                "goal": "Classify drift before updating Linear.",
                "intent": "Backfill drift safely.",
                "acceptance_criteria": ["Drift gets classified."],
                "constraints": [],
                "evidence_expectations": ["mirror diff"],
            },
        )
        (tmp_path / "docs" / "specs" / mission_id / "plan.json").write_text(
            json.dumps(
                {
                    "plan_id": f"plan-{mission_id}",
                    "mission_id": mission_id,
                    "status": "draft",
                    "waves": [{"wave_number": 0, "description": "Wave 0", "work_packets": []}],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (tmp_path / "docs" / "specs" / mission_id / "operator" / "launch.json").write_text(
            json.dumps(
                {
                    "linear_issue": {
                        "id": linear_issue_id,
                        "identifier": mission_id.upper(),
                        "title": mission_id,
                    }
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    _seed_bound_mission("missing-mirror", linear_issue_id="issue-missing")
    _seed_bound_mission("stale-plan", linear_issue_id="issue-stale")

    stale_mirror = build_linear_mirror_for_mission(tmp_path, "stale-plan")
    assert stale_mirror is not None
    stale_mirror["plan_sync"]["plan_state"] = "approved"
    stale_mirror["next_action"] = "launch_mission"

    class FakeLinearClient:
        def query(self, graphql: str, variables: dict | None = None) -> dict:
            if "query($id: String!)" not in graphql:
                raise AssertionError(graphql)
            issue_id = str((variables or {}).get("id", ""))
            if issue_id == "issue-missing":
                return {"issue": {"id": issue_id, "description": "mission: missing-mirror"}}
            if issue_id == "issue-stale":
                return {
                    "issue": {
                        "id": issue_id,
                        "description": render_linear_mirror_section(stale_mirror),
                    }
                }
            raise AssertionError(issue_id)

    drifts = collect_linear_mission_mirror_drifts(tmp_path, client=FakeLinearClient())

    assert [item["status"] for item in drifts] == ["missing_mirror", "stale_plan_sync"]
    assert drifts[0]["mission_id"] == "missing-mirror"
    assert drifts[0]["reasons"] == ["mirror block missing from Linear description"]
    assert drifts[1]["mission_id"] == "stale-plan"
    assert "plan_sync.plan_state differs" in drifts[1]["reasons"]
