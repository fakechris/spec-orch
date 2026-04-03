from __future__ import annotations

import json
from pathlib import Path

from spec_orch.acceptance_core.models import (
    AcceptanceJudgment,
    AcceptanceJudgmentClass,
    AcceptanceRunMode,
    AcceptanceWorkflowState,
    CandidateFinding,
)
from spec_orch.domain.models import EvolutionChangeType, EvolutionProposal
from spec_orch.runtime_chain.models import ChainPhase, RuntimeChainStatus, RuntimeSubjectKind
from spec_orch.runtime_chain.store import write_chain_status
from spec_orch.services.evolution.promotion_registry import PromotionOrigin, PromotionRegistry
from spec_orch.services.memory.service import MemoryService


def _seed_showcase_workspace(repo_root: Path, mission_id: str) -> None:
    specs_dir = repo_root / "docs" / "specs" / mission_id
    round_dir = specs_dir / "rounds" / "round-02"
    previous_mission_id = f"{mission_id}-previous"
    previous_specs_dir = repo_root / "docs" / "specs" / previous_mission_id
    previous_round_dir = previous_specs_dir / "rounds" / "round-01"
    previous_bundle_dir = (
        repo_root
        / "docs"
        / "acceptance-history"
        / "releases"
        / "learning-promotion-discipline-tranche-1-2026-04-03"
    )
    bundle_dir = (
        repo_root
        / "docs"
        / "acceptance-history"
        / "releases"
        / "showcase-tranche-son-363-seed-2026-04-03"
    )
    round_dir.mkdir(parents=True)
    previous_round_dir.mkdir(parents=True, exist_ok=True)
    previous_bundle_dir.mkdir(parents=True, exist_ok=True)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    (specs_dir / "mission.json").write_text(
        json.dumps(
            {
                "mission_id": mission_id,
                "title": "Mission Showcase Workspace",
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
    (specs_dir / "spec.md").write_text("# Mission Showcase Workspace\n", encoding="utf-8")
    (previous_specs_dir / "mission.json").write_text(
        json.dumps(
            {
                "mission_id": previous_mission_id,
                "title": "Mission Showcase Workspace Previous",
                "status": "approved",
                "spec_path": f"docs/specs/{previous_mission_id}/spec.md",
                "acceptance_criteria": [],
                "constraints": [],
                "interface_contracts": [],
                "created_at": "2026-04-02T23:00:00+00:00",
                "approved_at": "2026-04-02T23:10:00+00:00",
                "completed_at": None,
            }
        ),
        encoding="utf-8",
    )
    (previous_specs_dir / "spec.md").write_text(
        "# Mission Showcase Workspace Previous\n", encoding="utf-8"
    )
    (round_dir / "acceptance_review.json").write_text(
        json.dumps(
            {
                "status": "pass",
                "summary": "Replay, judgment, and learning all aligned after rerun.",
                "confidence": 0.91,
                "acceptance_mode": "exploratory",
                "coverage_status": "complete",
                "recommended_next_step": "Archive this rerun for operator showcase.",
                "structural_judgment": {
                    "quality_signal": "stable",
                    "bottleneck": "none",
                    "rule_violations": [],
                    "baseline_diff": {"baseline_ref": "fixture:dashboard-transcript-regression"},
                    "current_state": "verified",
                },
            }
        ),
        encoding="utf-8",
    )
    write_chain_status(
        specs_dir / "operator" / "runtime_chain",
        RuntimeChainStatus(
            chain_id=f"chain-{mission_id}",
            active_span_id=f"chain-{mission_id}:acceptance",
            subject_kind=RuntimeSubjectKind.ACCEPTANCE,
            subject_id=mission_id,
            phase=ChainPhase.COMPLETED,
            status_reason="acceptance_completed",
            updated_at="2026-04-03T03:20:00+00:00",
        ),
    )

    svc = MemoryService(repo_root=repo_root)
    svc.record_acceptance_judgments(
        mission_id=mission_id,
        round_id=2,
        judgments=[
            AcceptanceJudgment(
                judgment_id="proposal:showcase-1",
                judgment_class=AcceptanceJudgmentClass.CANDIDATE_FINDING,
                run_mode=AcceptanceRunMode.EXPLORE,
                workflow_state=AcceptanceWorkflowState.PROMOTED,
                summary="Transcript continuity fix is now stable enough to narrate.",
                candidate=CandidateFinding(
                    finding_id="candidate:showcase-1",
                    claim="Transcript continuity is now stable after the rerun.",
                    route=f"/?mission={mission_id}&mode=missions&tab=judgment",
                    evidence_refs=[
                        f"docs/specs/{mission_id}/rounds/round-02/acceptance_review.json",
                    ],
                    baseline_ref="fixture:dashboard-transcript-regression",
                    origin_step="candidate_review",
                    graph_profile="tuned_dashboard_compare_graph",
                    run_mode="explore",
                    compare_overlay=True,
                    promotion_test="Promote once the rerun remains green.",
                    dedupe_key="dashboard:transcript-continuity",
                ),
            )
        ],
    )
    svc.record_evolution_journal(
        evolver_name="prompt_evolver",
        stage="promote",
        summary="Promoted transcript continuity guidance for showcase lineage.",
        metadata={
            "proposal_id": "proposal-showcase-1",
            "mission_id": mission_id,
            "origin_finding_ref": "candidate:showcase-1",
            "origin_review_ref": "proposal:showcase-1",
            "promoted": True,
        },
    )
    svc.synthesize_active_learning_slice("self", top_k=5)
    PromotionRegistry(repo_root).record_promotion(
        EvolutionProposal(
            proposal_id="proposal-showcase-1",
            evolver_name="prompt_evolver",
            change_type=EvolutionChangeType.PROMPT_VARIANT,
            content={"variant_id": "transcript-continuity-showcase"},
            evidence=[{"type": "acceptance_review", "mission_id": mission_id}],
            confidence=0.9,
        ),
        origin=PromotionOrigin.ACCEPTANCE_REVIEW,
        reviewed_evidence_count=1,
        signal_origins=["acceptance_review"],
        workspace_id=mission_id,
        origin_finding_ref="candidate:showcase-1",
        origin_review_ref="proposal:showcase-1",
        promotion_target="EvolutionProposalRef",
        promotion_reason="Stable rerun ready for showcase narrative.",
    )

    (repo_root / "docs" / "acceptance-history").mkdir(parents=True, exist_ok=True)
    (repo_root / "docs" / "acceptance-history" / "index.json").write_text(
        json.dumps(
            {
                "releases": [
                    {
                        "release_id": "learning-promotion-discipline-tranche-1-2026-04-03",
                        "release_label": "Learning Promotion Discipline Tranche 1 2026-04-03",
                        "created_at": "2026-04-03T03:15:00Z",
                        "git_commit": "ecd5130",
                        "overall_status": "pass",
                        "findings_count": 0,
                        "issue_proposal_count": 0,
                        "bundle_path": (
                            "docs/acceptance-history/releases/"
                            "learning-promotion-discipline-tranche-1-2026-04-03"
                        ),
                    },
                    {
                        "release_id": "showcase-tranche-son-363-seed-2026-04-03",
                        "release_label": "Showcase Narrative Seed",
                        "created_at": "2026-04-03T03:30:00Z",
                        "git_commit": "db9e272",
                        "overall_status": "pass",
                        "findings_count": 1,
                        "issue_proposal_count": 0,
                        "bundle_path": (
                            "docs/acceptance-history/releases/"
                            "showcase-tranche-son-363-seed-2026-04-03"
                        ),
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    (previous_bundle_dir / "summary.md").write_text(
        "# Learning Promotion Discipline Tranche 1\n\nPrevious bundle.\n",
        encoding="utf-8",
    )
    (previous_bundle_dir / "manifest.json").write_text(
        json.dumps(
            {
                "release_id": "learning-promotion-discipline-tranche-1-2026-04-03",
                "lineage": {"notes": ["Previous release before showcase compare narrative."]},
            }
        ),
        encoding="utf-8",
    )
    (previous_bundle_dir / "status.json").write_text(
        json.dumps({"overall_status": "pass", "checks": {"exploratory": "pass"}}),
        encoding="utf-8",
    )
    (previous_bundle_dir / "findings.json").write_text(
        json.dumps(
            {
                "findings": [],
                "issue_proposals": [],
                "counts": {"findings_count": 0, "issue_proposal_count": 0},
            }
        ),
        encoding="utf-8",
    )
    (previous_bundle_dir / "source_runs.json").write_text(
        json.dumps(
            {
                "mission_start": {
                    "mission_id": previous_mission_id,
                    "report_path": (
                        f"docs/specs/{previous_mission_id}/operator/mission_start_acceptance.json"
                    ),
                },
                "exploratory": {
                    "mission_id": previous_mission_id,
                    "report_path": (
                        f"docs/specs/{previous_mission_id}/operator/exploratory_acceptance_smoke.json"
                    ),
                },
            }
        ),
        encoding="utf-8",
    )
    (previous_bundle_dir / "artifacts.json").write_text(
        json.dumps(
            {
                "status_markdown": "docs/plans/2026-03-30-stability-acceptance-status.md",
                "browser_evidence_paths": [],
            }
        ),
        encoding="utf-8",
    )
    (bundle_dir / "summary.md").write_text(
        "# Showcase Narrative Seed\n\nThis bundle proves the rerun passed.\n",
        encoding="utf-8",
    )
    (bundle_dir / "manifest.json").write_text(
        json.dumps(
            {
                "release_id": "showcase-tranche-son-363-seed-2026-04-03",
                "lineage": {
                    "notes": [
                        "Seed showcase bundle proving replay, judgment, and learning lineage.",
                        "Source-run compare versus prior seed: mission_start and exploratory stayed green.",
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    (bundle_dir / "status.json").write_text(
        json.dumps({"overall_status": "pass", "checks": {"exploratory": "pass"}}),
        encoding="utf-8",
    )
    (bundle_dir / "findings.json").write_text(
        json.dumps(
            {
                "findings": [
                    {
                        "finding_id": "candidate:showcase-1",
                        "bug_type": "ux_gap",
                        "summary": "Transcript continuity was previously unclear.",
                        "current_state": "verified_fixed",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (bundle_dir / "source_runs.json").write_text(
        json.dumps(
            {
                "mission_start": {
                    "mission_id": mission_id,
                    "report_path": f"docs/specs/{mission_id}/operator/mission_start_acceptance.json",
                },
                "exploratory": {
                    "mission_id": mission_id,
                    "report_path": f"docs/specs/{mission_id}/operator/exploratory_acceptance_smoke.json",
                },
            }
        ),
        encoding="utf-8",
    )
    (bundle_dir / "artifacts.json").write_text(
        json.dumps(
            {
                "status_markdown": ("docs/plans/2026-03-30-stability-acceptance-status.md"),
                "browser_evidence_paths": [
                    f"docs/specs/{mission_id}/rounds/round-02/browser_evidence.json"
                ],
            }
        ),
        encoding="utf-8",
    )


def test_build_showcase_workbench_surfaces_release_timeline_and_workspace_storylines(
    tmp_path: Path,
) -> None:
    from spec_orch.services.showcase_workbench import build_showcase_workbench

    mission_id = "mission-showcase"
    _seed_showcase_workspace(tmp_path, mission_id)

    payload = build_showcase_workbench(tmp_path)

    assert payload["summary"] == {
        "release_count": 2,
        "passing_release_count": 2,
        "workspace_story_count": 2,
        "highlight_count": 2,
    }
    assert payload["release_timeline"][0]["release_id"] == (
        "showcase-tranche-son-363-seed-2026-04-03"
    )
    assert payload["release_timeline"][0]["summary_artifact_path"].endswith("summary.md")
    assert payload["release_timeline"][0]["workspace_ids"] == [mission_id]
    assert "Seed showcase bundle" in payload["release_timeline"][0]["lineage_notes"][0]
    assert payload["release_timeline"][0]["compare_target_release_id"] == (
        "learning-promotion-discipline-tranche-1-2026-04-03"
    )
    assert payload["release_timeline"][0]["compare_counts"] == {
        "advanced": 2,
        "stayed": 0,
        "new": 0,
        "missing": 0,
    }
    assert payload["release_timeline"][0]["compare_focus"] == [
        "mission_start advanced",
        "exploratory advanced",
    ]
    assert payload["release_timeline"][0]["source_run_compare"]["mission_start"]["status"] == (
        "advanced"
    )
    assert payload["release_timeline"][0]["source_run_compare"]["exploratory"]["status"] == (
        "advanced"
    )
    storyline = next(
        item for item in payload["workspace_storylines"] if item["workspace_id"] == mission_id
    )
    assert storyline["workspace_id"] == mission_id
    assert storyline["routes"]["judgment"] == (f"/?mission={mission_id}&mode=missions&tab=judgment")
    assert storyline["governance_story"]["structural"]["quality_signal"] == ("regression")
    assert storyline["governance_story"]["learning"]["promotion_decision"] == ("promote")
    assert storyline["lineage_drilldown"]["latest_release_id"] == (
        "showcase-tranche-son-363-seed-2026-04-03"
    )
    assert storyline["lineage_drilldown"]["compare_target_release_id"] == (
        "learning-promotion-discipline-tranche-1-2026-04-03"
    )
    assert storyline["lineage_drilldown"]["compare_counts"] == {
        "advanced": 2,
        "stayed": 0,
        "new": 0,
        "missing": 0,
    }
    assert storyline["lineage_drilldown"]["compare_focus"] == [
        "mission_start advanced",
        "exploratory advanced",
    ]
    assert storyline["lineage_drilldown"]["source_run_compare_summary"] == (
        "mission_start advanced; exploratory advanced"
    )
    assert "Execution completed" in storyline["narrative"]
    assert payload["highlights"][0]["kind"] == "release"
    assert payload["highlights"][1]["kind"] == "workspace"
    assert payload["review_route"] == "/?mode=showcase"
