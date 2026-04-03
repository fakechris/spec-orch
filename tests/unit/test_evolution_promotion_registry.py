from __future__ import annotations

from pathlib import Path

from spec_orch.domain.models import EvolutionChangeType, EvolutionProposal
from spec_orch.services.evolution.promotion_registry import (
    PromotionGateDecision,
    PromotionOrigin,
    PromotionRegistry,
)


def _proposal(
    *,
    proposal_id: str = "proposal-1",
    evolver_name: str = "prompt_evolver",
    change_type: EvolutionChangeType = EvolutionChangeType.PROMPT_VARIANT,
    content: dict[str, object] | None = None,
) -> EvolutionProposal:
    return EvolutionProposal(
        proposal_id=proposal_id,
        evolver_name=evolver_name,
        change_type=change_type,
        content=content or {"variant_id": "v-next"},
        evidence=[{"kind": "example"}],
        confidence=0.8,
    )


def test_high_impact_gate_requires_reviewed_evidence(tmp_path: Path) -> None:
    registry = PromotionRegistry(tmp_path)
    decision = registry.evaluate_gate(
        _proposal(),
        reviewed_evidence_count=0,
        signal_origins=["execution"],
    )
    assert decision == PromotionGateDecision(
        allowed=False,
        reason="reviewed evidence required for high-impact promotion",
        origin=PromotionOrigin.EXECUTION,
        reviewed_evidence_count=0,
        signal_origins=["execution"],
    )


def test_register_promotion_supersedes_prior_active_asset(tmp_path: Path) -> None:
    registry = PromotionRegistry(tmp_path)

    first = registry.record_promotion(
        _proposal(proposal_id="proposal-1", content={"variant_id": "v1"}),
        origin=PromotionOrigin.DECISION_REVIEW,
        reviewed_evidence_count=2,
        signal_origins=["decision_review"],
    )
    second = registry.record_promotion(
        _proposal(proposal_id="proposal-2", content={"variant_id": "v2"}),
        origin=PromotionOrigin.DECISION_REVIEW,
        reviewed_evidence_count=3,
        signal_origins=["decision_review"],
    )

    records = registry.load_records()
    assert len(records) == 2
    old = next(r for r in records if r.promotion_id == first.promotion_id)
    new = next(r for r in records if r.promotion_id == second.promotion_id)
    assert old.status == "superseded"
    assert old.superseded_by == new.promotion_id
    assert new.status == "active"


def test_rollback_marks_record_and_preserves_reason(tmp_path: Path) -> None:
    registry = PromotionRegistry(tmp_path)
    promotion = registry.record_promotion(
        _proposal(proposal_id="proposal-1", content={"variant_id": "v1"}),
        origin=PromotionOrigin.ACCEPTANCE_REVIEW,
        reviewed_evidence_count=1,
        signal_origins=["acceptance_review"],
    )

    assert (
        registry.rollback(promotion.promotion_id, reason="false positive calibration drift") is True
    )

    rolled_back = registry.get(promotion.promotion_id)
    assert rolled_back is not None
    assert rolled_back.status == "rolled_back"
    assert rolled_back.rollback_reason == "false positive calibration drift"


def test_record_promotion_preserves_review_lineage_fields(tmp_path: Path) -> None:
    registry = PromotionRegistry(tmp_path)
    promotion = registry.record_promotion(
        _proposal(proposal_id="proposal-3", content={"variant_id": "v3"}),
        origin=PromotionOrigin.ACCEPTANCE_REVIEW,
        reviewed_evidence_count=2,
        signal_origins=["acceptance_review"],
        workspace_id="mission-learning",
        origin_finding_ref="candidate:learning-1",
        origin_review_ref="proposal:learning-1",
        promotion_target="EvolutionProposalRef",
        promotion_reason="Repeated reviewed transcript replay evidence.",
    )

    assert promotion.workspace_id == "mission-learning"
    assert promotion.origin_finding_ref == "candidate:learning-1"
    assert promotion.origin_review_ref == "proposal:learning-1"
    assert promotion.promotion_target == "EvolutionProposalRef"
    assert promotion.promotion_reason == "Repeated reviewed transcript replay evidence."


def test_retire_marks_record_and_preserves_reason(tmp_path: Path) -> None:
    registry = PromotionRegistry(tmp_path)
    promotion = registry.record_promotion(
        _proposal(proposal_id="proposal-4", content={"variant_id": "v4"}),
        origin=PromotionOrigin.ACCEPTANCE_REVIEW,
        reviewed_evidence_count=1,
        signal_origins=["acceptance_review"],
    )

    assert registry.retire(promotion.promotion_id, reason="Superseded by fixture replay bundle") is True

    retired = registry.get(promotion.promotion_id)
    assert retired is not None
    assert retired.status == "retired"
    assert retired.retirement_reason == "Superseded by fixture replay bundle"
