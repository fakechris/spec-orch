from __future__ import annotations

import json
from pathlib import Path


def test_build_mission_judgment_substrate_surfaces_canonical_review_models(
    tmp_path: Path,
) -> None:
    from spec_orch.services.judgment_substrate import build_mission_judgment_substrate

    mission_id = "mission-judgment"
    round_dir = tmp_path / "docs" / "specs" / mission_id / "rounds" / "round-02"
    round_dir.mkdir(parents=True)
    (round_dir / "acceptance_review.json").write_text(
        json.dumps(
            {
                "status": "warn",
                "summary": "Transcript continuity needs operator confirmation.",
                "confidence": 0.72,
                "evaluator": "acceptance_llm",
                "acceptance_mode": "exploratory",
                "coverage_status": "partial",
                "untested_expected_routes": ["/settings"],
                "recommended_next_step": "Run compare replay on the transcript path.",
                "issue_proposals": [
                    {
                        "title": "Clarify transcript handoff",
                        "summary": "Transcript continuity is credible but needs a stronger replay baseline.",
                        "severity": "medium",
                        "route": "/?mission=mission-judgment&mode=missions&tab=transcript",
                        "hold_reason": "Need compare replay before filing.",
                        "confidence": 0.64,
                        "critique_axis": "task_continuity",
                        "operator_task": "Inspect transcript and acceptance tabs together",
                        "why_it_matters": "Operators can miss whether the current round is complete.",
                        "artifact_paths": {
                            "review": "docs/specs/mission-judgment/rounds/round-02/acceptance_review.json"
                        },
                    }
                ],
                "artifacts": {
                    "acceptance_review": "docs/specs/mission-judgment/rounds/round-02/acceptance_review.json",
                    "graph_run": "docs/specs/mission-judgment/rounds/round-02/acceptance_graph_runs/agr-2/graph_run.json",
                    "graph_profile": "tuned_dashboard_compare_graph",
                    "compare_overlay": True,
                    "baseline_ref": "fixture:dashboard-transcript-regression",
                    "step_artifacts": [
                        "docs/specs/mission-judgment/rounds/round-02/acceptance_graph_runs/agr-2/steps/01-route_inventory.json",
                        "docs/specs/mission-judgment/rounds/round-02/acceptance_graph_runs/agr-2/steps/02-compare_replay.json",
                    ],
                    "graph_transitions": [
                        "select_routing",
                        "collect_evidence",
                        "candidate_review",
                        "summarize_judgment",
                    ],
                    "final_transition": "summarize_judgment",
                },
                "campaign": {
                    "mode": "exploratory",
                    "goal": "Inspect transcript continuity and review evidence discoverability.",
                    "primary_routes": ["/?mission=mission-judgment&mode=missions&tab=overview"],
                    "related_routes": [
                        "/?mission=mission-judgment&mode=missions&tab=transcript",
                        "/?mission=mission-judgment&mode=missions&tab=acceptance",
                    ],
                    "coverage_expectations": ["overview", "transcript", "acceptance"],
                    "filing_policy": "auto_file_broken_flows_only",
                    "exploration_budget": "bounded",
                },
            }
        ),
        encoding="utf-8",
    )

    payload = build_mission_judgment_substrate(tmp_path, mission_id)

    assert payload["summary"]["total_reviews"] == 1
    assert payload["overview"] == {
        "base_run_mode": "explore",
        "judgment_class": "candidate_finding",
        "review_state": "queued",
        "compare_state": "active",
        "candidate_finding_count": 1,
        "confirmed_issue_count": 0,
        "observation_count": 0,
        "recommended_next_step": "Run compare replay on the transcript path.",
        "evidence_summary": "Transcript continuity needs operator confirmation.",
    }
    latest = payload["latest_review"]
    assert latest["shared_judgments"][0]["judgment_class"] == "candidate_finding"
    assert latest["evidence_bundle"]["bundle_kind"] == "acceptance_review"
    assert latest["evidence_bundle"]["route_refs"] == [
        "/?mission=mission-judgment&mode=missions&tab=overview",
        "/?mission=mission-judgment&mode=missions&tab=transcript",
        "/?mission=mission-judgment&mode=missions&tab=acceptance",
    ]
    assert latest["evidence_bundle"]["step_refs"] == [
        "docs/specs/mission-judgment/rounds/round-02/acceptance_graph_runs/agr-2/steps/01-route_inventory.json",
        "docs/specs/mission-judgment/rounds/round-02/acceptance_graph_runs/agr-2/steps/02-compare_replay.json",
    ]
    assert latest["compare_overlay"]["compare_state"] == "active"
    assert latest["compare_overlay"]["baseline_ref"] == "fixture:dashboard-transcript-regression"
    assert latest["compare_overlay"]["artifact_drift_refs"] == [
        "docs/specs/mission-judgment/rounds/round-02/acceptance_graph_runs/agr-2/steps/01-route_inventory.json",
        "docs/specs/mission-judgment/rounds/round-02/acceptance_graph_runs/agr-2/steps/02-compare_replay.json",
    ]
    assert latest["surface_pack"]["surface_name"] == "dashboard"
    assert latest["surface_pack"]["graph_profiles"] == ["tuned_dashboard_compare_graph"]
    assert latest["surface_pack"]["baseline_refs"] == ["fixture:dashboard-transcript-regression"]
    assert [item["event_type"] for item in latest["judgment_timeline"]] == [
        "routing_selected",
        "graph_profile_activated",
        "evidence_bundle_collected",
        "compare_overlay_active",
        "judgment_assigned",
        "review_state_changed",
    ]
    assert latest["judgment_timeline"][-1]["event_summary"] == "queued candidate_finding"
    assert latest["evidence_panel"] == {
        "bundle_kind": "acceptance_review",
        "route_count": 3,
        "step_count": 2,
        "artifact_count": 4,
        "coverage_status": "partial",
        "coverage_gaps": ["/settings"],
        "evidence_summary": "Transcript continuity needs operator confirmation.",
    }
    assert latest["candidate_queue"] == [
        {
            "candidate_finding_id": latest["candidate_findings"][0]["candidate_finding"][
                "candidate_finding_id"
            ],
            "claim": "Clarify transcript handoff",
            "surface": "dashboard",
            "route": "/?mission=mission-judgment&mode=missions&tab=transcript",
            "why_it_matters": "Operators can miss whether the current round is complete.",
            "confidence": 0.64,
            "impact_if_true": "medium",
            "repro_status": "needs_repro",
            "hold_reason": "Need compare replay before filing.",
            "promotion_test": "Promote once the recommended next step completes.",
            "recommended_next_step": "Run compare replay on the transcript path.",
        }
    ]
    assert latest["compare_view"] == {
        "compare_state": "active",
        "baseline_ref": "fixture:dashboard-transcript-regression",
        "drift_summary": "Baseline fixture:dashboard-transcript-regression compared against current review.",
        "artifact_drift_count": 2,
        "judgment_drift_summary": "Candidate findings were formed under compare overlay.",
    }
    assert latest["structural_judgment"] == {
        "structural_judgment_id": "mission-judgment:structural",
        "workspace_id": "mission-judgment",
        "quality_signal": "watch",
        "bottleneck": "candidate_repro_pending",
        "rule_violations": [
            {
                "rule_id": "coverage_incomplete",
                "severity": "medium",
                "summary": "Expected routes remain untested.",
                "details": {
                    "coverage_status": "partial",
                    "untested_route_count": 1,
                },
            },
            {
                "rule_id": "candidate_repro_pending",
                "severity": "medium",
                "summary": "Candidate findings still need repro before promotion.",
                "details": {
                    "pending_candidate_count": 1,
                },
            },
            {
                "rule_id": "baseline_drift_detected",
                "severity": "medium",
                "summary": "Compare overlay detected baseline drift artifacts.",
                "details": {
                    "artifact_drift_count": 2,
                    "baseline_ref": "fixture:dashboard-transcript-regression",
                },
            },
        ],
        "baseline_diff": {
            "compare_state": "active",
            "baseline_ref": "fixture:dashboard-transcript-regression",
            "artifact_drift_count": 2,
            "drift_status": "drift_detected",
        },
        "current_state": {
            "review_status": "warn",
            "coverage_status": "partial",
            "candidate_finding_count": 1,
            "confirmed_issue_count": 0,
            "observation_count": 0,
            "route_count": 3,
            "artifact_count": 4,
        },
    }
    assert latest["surface_pack_panel"] == {
        "surface_name": "dashboard",
        "active_axes": ["information_scent", "task_continuity", "feedback_clarity"],
        "known_routes": [
            "/",
            "/launcher",
            "/missions",
            "/missions?tab=transcript",
            "/missions?tab=judgment",
        ],
        "graph_profiles": ["tuned_dashboard_compare_graph"],
        "baseline_refs": ["fixture:dashboard-transcript-regression"],
    }


def test_build_judgment_workbench_aggregates_workspace_inventory(
    tmp_path: Path,
) -> None:
    from spec_orch.services.judgment_workbench import (
        build_judgment_workbench,
        build_mission_judgment_workbench,
    )

    candidate_mission_id = "mission-judgment-candidate"
    candidate_round_dir = tmp_path / "docs" / "specs" / candidate_mission_id / "rounds" / "round-01"
    candidate_round_dir.mkdir(parents=True)
    (candidate_round_dir / "acceptance_review.json").write_text(
        json.dumps(
            {
                "status": "warn",
                "summary": "Transcript continuity needs a replay before promotion.",
                "confidence": 0.71,
                "evaluator": "acceptance_llm",
                "acceptance_mode": "exploratory",
                "coverage_status": "partial",
                "untested_expected_routes": ["/settings"],
                "recommended_next_step": "Replay the transcript route with compare enabled.",
                "issue_proposals": [
                    {
                        "title": "Clarify transcript continuity",
                        "summary": "Operators can miss whether the latest round is complete.",
                        "severity": "medium",
                        "route": "/?mission=mission-judgment-candidate&mode=missions&tab=transcript",
                        "hold_reason": "Replay evidence is still missing.",
                        "confidence": 0.63,
                        "why_it_matters": "Operators need a stable transcript handoff.",
                    }
                ],
                "artifacts": {
                    "acceptance_review": "docs/specs/mission-judgment-candidate/rounds/round-01/acceptance_review.json",
                    "graph_run": "docs/specs/mission-judgment-candidate/rounds/round-01/acceptance_graph_runs/agr-1/graph_run.json",
                    "graph_profile": "tuned_dashboard_compare_graph",
                    "compare_overlay": True,
                    "baseline_ref": "fixture:dashboard-transcript-baseline",
                    "step_artifacts": [
                        "docs/specs/mission-judgment-candidate/rounds/round-01/acceptance_graph_runs/agr-1/steps/01-route_inventory.json",
                        "docs/specs/mission-judgment-candidate/rounds/round-01/acceptance_graph_runs/agr-1/steps/02-compare_replay.json",
                    ],
                    "graph_transitions": [
                        "select_routing",
                        "collect_evidence",
                        "candidate_review",
                        "summarize_judgment",
                    ],
                    "final_transition": "summarize_judgment",
                },
                "campaign": {
                    "mode": "exploratory",
                    "goal": "Inspect transcript continuity.",
                    "primary_routes": [
                        "/?mission=mission-judgment-candidate&mode=missions&tab=overview"
                    ],
                    "related_routes": [
                        "/?mission=mission-judgment-candidate&mode=missions&tab=transcript"
                    ],
                    "coverage_expectations": ["overview", "transcript"],
                    "filing_policy": "auto_file_broken_flows_only",
                    "exploration_budget": "bounded",
                },
            }
        ),
        encoding="utf-8",
    )

    confirmed_mission_id = "mission-judgment-confirmed"
    confirmed_round_dir = tmp_path / "docs" / "specs" / confirmed_mission_id / "rounds" / "round-02"
    confirmed_round_dir.mkdir(parents=True)
    (confirmed_round_dir / "acceptance_review.json").write_text(
        json.dumps(
            {
                "status": "fail",
                "summary": "Primary CTA is missing from the dashboard home route.",
                "confidence": 0.93,
                "evaluator": "acceptance_llm",
                "acceptance_mode": "verify",
                "coverage_status": "complete",
                "untested_expected_routes": [],
                "recommended_next_step": "File the regression and rerun acceptance.",
                "findings": [{"severity": "high", "summary": "Primary CTA missing", "route": "/"}],
                "issue_proposals": [
                    {
                        "title": "Restore dashboard CTA",
                        "summary": "Acceptance evaluator found no CTA in the hero section.",
                        "severity": "high",
                        "route": "/",
                        "confidence": 0.93,
                        "linear_issue_id": "SON-3901",
                        "filing_status": "filed",
                    }
                ],
                "artifacts": {
                    "acceptance_review": "docs/specs/mission-judgment-confirmed/rounds/round-02/acceptance_review.json",
                    "graph_run": "docs/specs/mission-judgment-confirmed/rounds/round-02/acceptance_graph_runs/agr-1/graph_run.json",
                    "graph_profile": "tuned_dashboard_graph",
                    "step_artifacts": [
                        "docs/specs/mission-judgment-confirmed/rounds/round-02/acceptance_graph_runs/agr-1/steps/01-baseline_brief.json"
                    ],
                    "final_transition": "summarize_judgment",
                },
                "campaign": {
                    "mode": "impact_sweep",
                    "goal": "Verify the dashboard landing route.",
                    "primary_routes": ["/"],
                    "related_routes": ["/pricing"],
                    "coverage_expectations": ["homepage", "pricing"],
                    "filing_policy": "auto_file_regressions_only",
                    "exploration_budget": "medium",
                },
            }
        ),
        encoding="utf-8",
    )

    payload = build_judgment_workbench(tmp_path)

    assert payload["summary"] == {
        "workspace_count": 2,
        "reviewed_count": 2,
        "candidate_finding_count": 1,
        "confirmed_issue_count": 1,
        "compare_active_count": 1,
        "structural_regression_count": 1,
        "bottlenecked_workspace_count": 2,
    }
    assert payload["review_route"] == "/?mode=judgment"
    assert [item["workspace_id"] for item in payload["workspaces"]] == [
        candidate_mission_id,
        confirmed_mission_id,
    ]
    assert payload["workspaces"][0]["review_route"] == (
        f"/?mission={candidate_mission_id}&mode=missions&tab=judgment"
    )
    assert payload["workspaces"][0]["compare_state"] == "active"
    assert payload["workspaces"][1]["judgment_class"] == "confirmed_issue"
    assert payload["candidate_queue"] == [
        {
            "workspace_id": candidate_mission_id,
            "review_route": f"/?mission={candidate_mission_id}&mode=missions&tab=judgment",
            "candidate_finding_id": payload["workspaces"][0]["candidate_finding_ids"][0],
            "claim": "Clarify transcript continuity",
            "surface": "dashboard",
            "route": "/?mission=mission-judgment-candidate&mode=missions&tab=transcript",
            "why_it_matters": "Operators need a stable transcript handoff.",
            "confidence": 0.63,
            "impact_if_true": "medium",
            "repro_status": "needs_repro",
            "hold_reason": "Replay evidence is still missing.",
            "promotion_test": "Promote once the recommended next step completes.",
            "recommended_next_step": "Replay the transcript route with compare enabled.",
        }
    ]
    assert payload["compare_watch"] == [
        {
            "workspace_id": candidate_mission_id,
            "baseline_ref": "fixture:dashboard-transcript-baseline",
            "compare_state": "active",
            "artifact_drift_count": 2,
            "review_route": f"/?mission={candidate_mission_id}&mode=missions&tab=judgment",
        }
    ]
    assert payload["structural_watch"] == [
        {
            "workspace_id": candidate_mission_id,
            "quality_signal": "watch",
            "bottleneck": "candidate_repro_pending",
            "rule_violation_count": 3,
            "baseline_ref": "fixture:dashboard-transcript-baseline",
            "review_route": f"/?mission={candidate_mission_id}&mode=missions&tab=judgment",
        },
        {
            "workspace_id": confirmed_mission_id,
            "quality_signal": "regression",
            "bottleneck": "confirmed_issue",
            "rule_violation_count": 1,
            "baseline_ref": "",
            "review_route": f"/?mission={confirmed_mission_id}&mode=missions&tab=judgment",
        },
    ]

    mission_payload = build_mission_judgment_workbench(tmp_path, candidate_mission_id)

    assert mission_payload["mission_id"] == candidate_mission_id
    assert mission_payload["review_route"] == (
        f"/?mission={candidate_mission_id}&mode=missions&tab=judgment"
    )
    assert mission_payload["overview"]["judgment_class"] == "candidate_finding"
    assert mission_payload["overview"]["compare_state"] == "active"
    assert mission_payload["evidence_panel"]["route_count"] == 2
    assert mission_payload["candidate_queue"][0]["claim"] == "Clarify transcript continuity"
    assert (
        mission_payload["compare_view"]["baseline_ref"] == "fixture:dashboard-transcript-baseline"
    )
    assert mission_payload["structural_judgment"]["quality_signal"] == "watch"
    assert mission_payload["structural_judgment"]["bottleneck"] == "candidate_repro_pending"
    assert mission_payload["surface_pack_panel"]["surface_name"] == "dashboard"
    assert mission_payload["judgment_timeline"][-1]["event_type"] == "review_state_changed"
