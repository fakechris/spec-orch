from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from spec_orch.domain.operator_semantics import PromotedFinding


def _as_str(mapping: Mapping[str, object], key: str) -> str:
    value = mapping.get(key, "")
    return value.strip() if isinstance(value, str) else str(value or "").strip()


def evaluate_learning_promotion(
    finding: Mapping[str, object],
    *,
    fixture_candidates: Sequence[Mapping[str, object]],
    memory_refs: Sequence[Mapping[str, object]],
    evolution_refs: Sequence[Mapping[str, object]],
    archive_releases: Sequence[Mapping[str, object]],
) -> dict[str, Any]:
    mission_id = _as_str(finding, "mission_id")
    judgment_id = _as_str(finding, "judgment_id")
    finding_id = _as_str(finding, "finding_id")
    provenance = _as_str(finding, "provenance")
    workflow_state = _as_str(finding, "workflow_state")

    if provenance != "reviewed":
        return {
            "action": "reject",
            "verdict": "discard",
            "reason": "reviewed findings required for promotion",
            "promotion_state": "rejected",
            "eligible_targets": [],
            "promoted_finding": PromotedFinding(
                promoted_finding_id=f"promoted:{judgment_id or finding_id or mission_id}",
                workspace_id=mission_id,
                origin_judgment_ref=judgment_id,
                origin_review_ref=judgment_id,
                promotion_target="reviewed_learning",
                promoted_at=_as_str(finding, "created_at"),
                promoted_by="system",
                promotion_reason="reviewed finding required",
            ).to_dict(),
            "lineage": {
                "fixture_candidate_ids": [],
                "memory_ref_ids": [],
                "evolution_ref_ids": [],
                "archive_release_ids": [],
                "promoted_target_refs": {
                    "fixture_candidates": [],
                    "memory_refs": [],
                    "evolution_refs": [],
                },
                "raw_archive_release_ids": [],
            },
        }

    fixture_candidate_ids = [
        _as_str(item, "fixture_candidate_id") or _as_str(item, "seed_name")
        for item in fixture_candidates
        if _as_str(item, "fixture_candidate_id") or _as_str(item, "seed_name")
    ]
    memory_ref_ids = [
        _as_str(item, "memory_ref_id") for item in memory_refs if _as_str(item, "memory_ref_id")
    ]
    evolution_ref_ids = [
        _as_str(item, "evolution_ref_id") or _as_str(item, "promotion_id")
        for item in evolution_refs
        if _as_str(item, "evolution_ref_id") or _as_str(item, "promotion_id")
    ]
    archive_release_ids = [
        _as_str(item, "release_id") for item in archive_releases if _as_str(item, "release_id")
    ]

    eligible_targets: list[str] = []
    if fixture_candidate_ids:
        eligible_targets.append("FixtureCandidate")
    if memory_ref_ids:
        eligible_targets.append("MemoryEntryRef")
    if evolution_ref_ids:
        eligible_targets.append("EvolutionProposalRef")

    active_evolution_states = {
        _as_str(row, "promotion_state") or _as_str(row, "status") for row in evolution_refs
    }
    if "rolled_back" in active_evolution_states:
        action = "rollback"
        verdict = "rollback"
        promotion_state = "rolled_back"
        reason = "linked promotion was rolled back"
    elif "retired" in active_evolution_states:
        action = "retire"
        verdict = "retire"
        promotion_state = "retired"
        reason = "linked promotion was retired"
    elif eligible_targets:
        action = "promote"
        verdict = "promote"
        promotion_state = "promoted"
        reason = "reviewed finding linked to durable learning targets"
    elif workflow_state in {"promoted", "confirmed", "reviewed"}:
        action = "hold"
        verdict = "keep"
        promotion_state = "reviewed"
        reason = "reviewed finding is waiting for durable learning targets"
    else:
        action = "hold"
        verdict = "keep"
        promotion_state = workflow_state or "reviewed"
        reason = "reviewed finding is awaiting promotion review"

    promoted_finding = PromotedFinding(
        promoted_finding_id=f"promoted:{judgment_id or finding_id or mission_id}",
        workspace_id=mission_id,
        origin_judgment_ref=judgment_id,
        origin_review_ref=judgment_id,
        promotion_target="reviewed_learning",
        promoted_at=_as_str(finding, "created_at"),
        promoted_by="system",
        promotion_reason=reason,
    ).to_dict()

    return {
        "action": action,
        "verdict": verdict,
        "reason": reason,
        "promotion_state": promotion_state,
        "eligible_targets": eligible_targets,
        "promoted_finding": promoted_finding,
        "lineage": {
            "fixture_candidate_ids": fixture_candidate_ids,
            "memory_ref_ids": memory_ref_ids,
            "evolution_ref_ids": evolution_ref_ids,
            "archive_release_ids": archive_release_ids,
            "promoted_target_refs": {
                "fixture_candidates": fixture_candidate_ids,
                "memory_refs": memory_ref_ids,
                "evolution_refs": evolution_ref_ids,
            },
            "raw_archive_release_ids": archive_release_ids,
        },
    }


__all__ = ["evaluate_learning_promotion"]
