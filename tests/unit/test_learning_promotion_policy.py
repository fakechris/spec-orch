from __future__ import annotations

from spec_orch.services.learning_promotion_policy import evaluate_learning_promotion


def _finding(
    *, provenance: str = "reviewed", workflow_state: str = "promoted"
) -> dict[str, object]:
    return {
        "mission_id": "mission-learning",
        "judgment_id": "proposal:learning-1",
        "finding_id": "candidate:learning-1",
        "workflow_state": workflow_state,
        "summary": "Transcript continuity regression was promoted to a stable learning.",
        "provenance": provenance,
        "created_at": "2026-04-03T00:00:00+00:00",
    }


def test_evaluate_learning_promotion_requires_reviewed_finding() -> None:
    decision = evaluate_learning_promotion(
        _finding(provenance="unreviewed"),
        fixture_candidates=[],
        memory_refs=[],
        evolution_refs=[],
        archive_releases=[],
    )

    assert decision["action"] == "reject"
    assert decision["reason"] == "reviewed findings required for promotion"
    assert decision["eligible_targets"] == []


def test_evaluate_learning_promotion_surfaces_targets_and_lineage() -> None:
    decision = evaluate_learning_promotion(
        _finding(),
        fixture_candidates=[
            {
                "fixture_candidate_id": "fixture-candidate-dashboard-transcript-continuity",
                "origin_finding_ref": "candidate:learning-1",
            }
        ],
        memory_refs=[
            {
                "memory_ref_id": "memory-ref:self:acceptance-judgment-proposal-learning-1",
                "origin_finding_ref": "candidate:learning-1",
            }
        ],
        evolution_refs=[
            {
                "evolution_ref_id": "proposal-1",
                "origin_finding_ref": "candidate:learning-1",
                "promotion_state": "promoted",
            }
        ],
        archive_releases=[
            {
                "release_id": "structural-judgment-tranche-1-2026-04-03",
                "bundle_path": "docs/acceptance-history/releases/structural-judgment-tranche-1-2026-04-03",
            }
        ],
    )

    assert decision["action"] == "promote"
    assert decision["promotion_state"] == "promoted"
    assert decision["eligible_targets"] == [
        "FixtureCandidate",
        "MemoryEntryRef",
        "EvolutionProposalRef",
    ]
    assert decision["lineage"]["fixture_candidate_ids"] == [
        "fixture-candidate-dashboard-transcript-continuity"
    ]
    assert decision["lineage"]["memory_ref_ids"] == [
        "memory-ref:self:acceptance-judgment-proposal-learning-1"
    ]
    assert decision["lineage"]["archive_release_ids"] == [
        "structural-judgment-tranche-1-2026-04-03"
    ]


def test_evaluate_learning_promotion_ignores_placeholder_linkage_rows() -> None:
    decision = evaluate_learning_promotion(
        _finding(),
        fixture_candidates=[{}],
        memory_refs=[{"memory_ref_id": ""}],
        evolution_refs=[{"promotion_id": ""}],
        archive_releases=[],
    )

    assert decision["action"] == "hold"
    assert decision["promotion_state"] == "reviewed"
    assert decision["eligible_targets"] == []
    assert decision["lineage"]["fixture_candidate_ids"] == []
    assert decision["lineage"]["memory_ref_ids"] == []
    assert decision["lineage"]["evolution_ref_ids"] == []
