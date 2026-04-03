from __future__ import annotations

import json
from pathlib import Path

from spec_orch.acceptance_core.calibration import (
    FixtureGraduationStage,
    append_fixture_graduation_event,
    write_fixture_candidate_seed,
)
from spec_orch.acceptance_core.models import (
    AcceptanceJudgment,
    AcceptanceJudgmentClass,
    AcceptanceRunMode,
    AcceptanceWorkflowState,
    CandidateFinding,
)
from spec_orch.domain.models import EvolutionChangeType, EvolutionProposal
from spec_orch.services.evolution.promotion_registry import PromotionOrigin, PromotionRegistry
from spec_orch.services.memory.service import MemoryService


def _seed_learning_workspace(repo_root: Path, mission_id: str) -> None:
    specs_dir = repo_root / "docs" / "specs" / mission_id
    specs_dir.mkdir(parents=True, exist_ok=True)
    (specs_dir / "mission.json").write_text(
        json.dumps(
            {
                "mission_id": mission_id,
                "title": "Mission Learning Workbench",
                "status": "approved",
                "spec_path": f"docs/specs/{mission_id}/spec.md",
                "acceptance_criteria": [],
                "constraints": [],
                "interface_contracts": [],
                "created_at": "2026-04-03T00:00:00+00:00",
                "approved_at": "2026-04-03T00:10:00+00:00",
                "completed_at": None,
            }
        ),
        encoding="utf-8",
    )
    (specs_dir / "spec.md").write_text("# Mission Learning Workbench\n", encoding="utf-8")

    svc = MemoryService(repo_root=repo_root)
    svc.record_acceptance_judgments(
        mission_id=mission_id,
        round_id=3,
        judgments=[
            AcceptanceJudgment(
                judgment_id="proposal:learning-1",
                judgment_class=AcceptanceJudgmentClass.CANDIDATE_FINDING,
                run_mode=AcceptanceRunMode.EXPLORE,
                workflow_state=AcceptanceWorkflowState.PROMOTED,
                summary="Transcript continuity regression was promoted to a stable learning.",
                candidate=CandidateFinding(
                    finding_id="candidate:learning-1",
                    claim="Transcript continuity regression repeats across rounds.",
                    route=f"/?mission={mission_id}&mode=missions&tab=transcript",
                    evidence_refs=[
                        f"docs/specs/{mission_id}/rounds/round-03/acceptance_review.json",
                        f"docs/specs/{mission_id}/rounds/round-03/browser_evidence.json",
                    ],
                    baseline_ref="fixture:dashboard-transcript-regression",
                    origin_step="candidate_review",
                    graph_profile="tuned_dashboard_compare_graph",
                    run_mode="explore",
                    compare_overlay=True,
                    promotion_test="Promote when transcript replay reproduces twice.",
                    dedupe_key="dashboard:transcript-continuity",
                ),
            )
        ],
    )
    svc.record_evolution_journal(
        evolver_name="prompt_evolver",
        stage="promote",
        summary="Promoted transcript continuity guidance after repeated replay evidence.",
        metadata={
            "proposal_id": "proposal-1",
            "mission_id": mission_id,
            "promoted": True,
            "origin_finding_ref": "candidate:learning-1",
            "origin_review_ref": "proposal:learning-1",
        },
    )
    svc.synthesize_active_learning_slice("self", top_k=5)

    proposal = EvolutionProposal(
        proposal_id="proposal-1",
        evolver_name="prompt_evolver",
        change_type=EvolutionChangeType.PROMPT_VARIANT,
        content={"variant_id": "transcript-continuity-v2"},
        evidence=[{"type": "acceptance_review", "mission_id": mission_id}],
        confidence=0.83,
    )
    PromotionRegistry(repo_root).record_promotion(
        proposal,
        origin=PromotionOrigin.ACCEPTANCE_REVIEW,
        reviewed_evidence_count=2,
        signal_origins=["acceptance_review"],
    )

    graduation_event = append_fixture_graduation_event(
        repo_root,
        mission_id=mission_id,
        judgment_id="proposal:learning-1",
        finding_id="candidate:learning-1",
        stage=FixtureGraduationStage.FIXTURE_CANDIDATE,
        summary="Candidate fixture ready for transcript continuity replay.",
        source_record_id="acceptance-judgment-record",
        evidence_refs=[
            f"docs/specs/{mission_id}/rounds/round-03/acceptance_review.json",
        ],
        repeat_count=3,
        dedupe_key="dashboard:transcript-continuity",
        baseline_ref="fixture:dashboard-transcript-regression",
        graph_profile="tuned_dashboard_compare_graph",
        graph_run=f"docs/specs/{mission_id}/rounds/round-03/acceptance_graph_runs/agr-1/graph_run.json",
        step_artifacts=[
            f"docs/specs/{mission_id}/rounds/round-03/acceptance_graph_runs/agr-1/steps/01-route_inventory.json",
        ],
        graph_transitions=["candidate_review", "summarize_judgment"],
        final_transition="summarize_judgment",
        route=f"/?mission={mission_id}&mode=missions&tab=transcript",
        origin_step="candidate_review",
        promotion_test="Promote when transcript replay reproduces twice.",
    )
    write_fixture_candidate_seed(
        repo_root,
        mission_id=mission_id,
        event=graduation_event,
        review_payload={
            "status": "warn",
            "summary": "Transcript continuity still needs replay confirmation.",
        },
    )

    acceptance_history_dir = repo_root / "docs" / "acceptance-history"
    acceptance_history_dir.mkdir(parents=True, exist_ok=True)
    release_dir = (
        acceptance_history_dir
        / "releases"
        / "judgment-workbench-tranche-son-390-2026-04-03"
    )
    release_dir.mkdir(parents=True, exist_ok=True)
    (release_dir / "source_runs.json").write_text(
        json.dumps(
            {
                "mission_start": {
                    "mission_id": mission_id,
                    "report_path": f"docs/specs/{mission_id}/operator/mission_start_acceptance.json",
                }
            }
        ),
        encoding="utf-8",
    )
    (acceptance_history_dir / "index.json").write_text(
        json.dumps(
            {
                "releases": [
                    {
                        "release_id": "judgment-workbench-tranche-son-390-2026-04-03",
                        "release_label": "Judgment Workbench Tranche",
                        "created_at": "2026-04-03T03:30:00Z",
                        "overall_status": "pass",
                        "bundle_path": (
                            "docs/acceptance-history/releases/"
                            "judgment-workbench-tranche-son-390-2026-04-03"
                        ),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def _seed_empty_learning_workspace(repo_root: Path, mission_id: str) -> None:
    specs_dir = repo_root / "docs" / "specs" / mission_id
    specs_dir.mkdir(parents=True, exist_ok=True)
    (specs_dir / "mission.json").write_text(
        json.dumps(
            {
                "mission_id": mission_id,
                "title": "Empty Learning Workspace",
                "status": "approved",
                "spec_path": f"docs/specs/{mission_id}/spec.md",
                "acceptance_criteria": [],
                "constraints": [],
                "interface_contracts": [],
                "created_at": "2026-04-03T00:00:00+00:00",
                "approved_at": "2026-04-03T00:10:00+00:00",
                "completed_at": None,
            }
        ),
        encoding="utf-8",
    )
    (specs_dir / "spec.md").write_text("# Empty Learning Workspace\n", encoding="utf-8")


def test_build_mission_learning_workbench_surfaces_promotions_patterns_and_archive_lineage(
    tmp_path: Path,
) -> None:
    from spec_orch.services.learning_workbench import build_mission_learning_workbench

    mission_id = "mission-learning"
    _seed_learning_workspace(tmp_path, mission_id)

    payload = build_mission_learning_workbench(tmp_path, mission_id)

    assert payload["mission_id"] == mission_id
    assert payload["overview"] == {
        "promoted_finding_count": 1,
        "fixture_candidate_count": 1,
        "active_promotion_count": 1,
        "evolution_event_count": 1,
        "archive_release_count": 1,
        "linked_release_count": 1,
        "last_learning_summary": "Transcript continuity regression was promoted to a stable learning.",
    }
    assert payload["promotion_timeline"][0]["proposal_id"] == "proposal-1"
    assert payload["promotion_timeline"][0]["workspace_id"] == mission_id
    assert payload["promotion_timeline"][0]["origin_finding_ref"] == "candidate:learning-1"
    assert payload["promotion_timeline"][0]["promotion_state"] == "promoted"
    assert payload["patterns"][0]["dedupe_key"] == "dashboard:transcript-continuity"
    assert payload["patterns"][0]["review_route"] == (
        f"/?mission={mission_id}&mode=missions&tab=learning"
    )
    assert payload["promoted_findings"][0]["promotion_target"] == "reviewed_learning"
    assert payload["promotion_policy"]["summary"]["promote_count"] == 1
    assert payload["promotion_policy"]["summary"]["linked_release_count"] == 1
    assert payload["memory_links"]["memory_refs"][0]["origin_finding_ref"] == "candidate:learning-1"
    assert payload["fixture_registry"]["summary"] == {
        "candidate_count": 1,
        "graduation_count": 1,
    }
    assert payload["fixture_registry"]["candidates"][0]["seed_name"] == (
        "fixture-candidate-dashboard-transcript-continuity"
    )
    assert payload["fixture_registry"]["graduations"][0]["stage"] == "fixture_candidate"
    assert payload["memory_links"]["acceptance_findings"][0]["judgment_id"] == "proposal:learning-1"
    assert payload["memory_links"]["learning_slices"]["self"][0]["key"] == (
        "evolution-journal-prompt_evolver-promote"
    )
    assert payload["evolution_registry"]["recent_journal"][0]["evolver_name"] == "prompt_evolver"
    assert payload["evolution_registry"]["active_promotions"][0]["status"] == "active"
    assert payload["archive_lineage"]["releases"][0]["release_id"] == (
        "judgment-workbench-tranche-son-390-2026-04-03"
    )
    assert payload["archive_lineage"]["linked_releases"][0]["release_id"] == (
        "judgment-workbench-tranche-son-390-2026-04-03"
    )
    assert payload["review_route"] == f"/?mission={mission_id}&mode=missions&tab=learning"


def test_build_learning_workbench_aggregates_workspace_inventory(tmp_path: Path) -> None:
    from spec_orch.services.learning_workbench import build_learning_workbench

    _seed_learning_workspace(tmp_path, "mission-learning")

    payload = build_learning_workbench(tmp_path)

    assert payload["summary"] == {
        "workspace_count": 1,
        "promoted_finding_count": 1,
        "fixture_candidate_count": 1,
        "active_promotion_count": 1,
        "archive_release_count": 1,
        "linked_release_count": 1,
    }
    assert payload["workspaces"][0]["workspace_id"] == "mission-learning"
    assert payload["workspaces"][0]["promoted_finding_count"] == 1
    assert payload["workspaces"][0]["promotion_decision"] == "promote"
    assert payload["promotion_timeline"][0]["proposal_id"] == "proposal-1"
    assert payload["patterns"][0]["workspace_id"] == "mission-learning"
    assert payload["fixture_registry"]["candidates"][0]["mission_id"] == "mission-learning"
    assert payload["memory_links"]["acceptance_findings"][0]["mission_id"] == "mission-learning"
    assert payload["memory_links"]["memory_refs"][0]["origin_review_ref"] == "proposal:learning-1"
    assert payload["evolution_registry"]["active_promotions"][0]["proposal_id"] == "proposal-1"
    assert payload["archive_lineage"]["releases"][0]["release_id"] == (
        "judgment-workbench-tranche-son-390-2026-04-03"
    )
    assert payload["archive_lineage"]["linked_releases"][0]["release_id"] == (
        "judgment-workbench-tranche-son-390-2026-04-03"
    )
    assert payload["review_route"] == "/?mode=learning"


def test_build_learning_workbench_handles_workspace_without_promotion_decisions(
    tmp_path: Path,
) -> None:
    from spec_orch.services.learning_workbench import build_learning_workbench

    _seed_empty_learning_workspace(tmp_path, "mission-empty")

    payload = build_learning_workbench(tmp_path)

    assert payload["summary"]["workspace_count"] == 1
    assert payload["workspaces"][0]["workspace_id"] == "mission-empty"
    assert payload["workspaces"][0]["promotion_decision"] == ""
