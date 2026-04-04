"""Promotion lifecycle governance for evolver outputs."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from spec_orch.domain.models import EvolutionChangeType, EvolutionProposal
from spec_orch.services.io import atomic_write_json


class PromotionOrigin(StrEnum):
    EXECUTION = "execution"
    DECISION_REVIEW = "decision_review"
    ACCEPTANCE_REVIEW = "acceptance_review"
    SELF_REFLECTION = "self_reflection"


@dataclass(slots=True)
class PromotionGateDecision:
    allowed: bool
    reason: str
    origin: PromotionOrigin
    reviewed_evidence_count: int
    signal_origins: list[str]


@dataclass(slots=True)
class PromotionRecord:
    promotion_id: str
    proposal_id: str
    evolver_name: str
    change_type: str
    asset_key: str
    origin: str
    reviewed_evidence_count: int
    signal_origins: list[str]
    workspace_id: str = ""
    origin_finding_ref: str = ""
    origin_review_ref: str = ""
    promotion_target: str = ""
    promotion_reason: str = ""
    discipline_verdict: str = "promote"
    status: str = "active"
    created_at: str = ""
    superseded_by: str | None = None
    rollback_reason: str = ""
    retirement_reason: str = ""


class PromotionRegistry:
    """File-backed promotion lifecycle state for Epic 6."""

    _HIGH_IMPACT = frozenset(
        {
            EvolutionChangeType.PROMPT_VARIANT.value,
            EvolutionChangeType.POLICY.value,
            EvolutionChangeType.HARNESS_RULE.value,
        }
    )

    def __init__(self, repo_root: Path) -> None:
        self._root = repo_root / ".spec_orch_evolution"
        self._root.mkdir(parents=True, exist_ok=True)
        self._path = self._root / "promotion_registry.json"

    def load_records(self) -> list[PromotionRecord]:
        if not self._path.exists():
            return []
        try:
            raw = json.loads(self._path.read_text())
        except (json.JSONDecodeError, OSError):
            return []
        if not isinstance(raw, list):
            return []
        records: list[PromotionRecord] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                records.append(PromotionRecord(**item))
            except TypeError:
                continue
        return records

    def save_records(self, records: list[PromotionRecord]) -> None:
        atomic_write_json(self._path, [asdict(record) for record in records])

    def get(self, promotion_id: str) -> PromotionRecord | None:
        return next(
            (record for record in self.load_records() if record.promotion_id == promotion_id),
            None,
        )

    def evaluate_gate(
        self,
        proposal: EvolutionProposal,
        *,
        reviewed_evidence_count: int,
        signal_origins: list[str],
    ) -> PromotionGateDecision:
        origin = self._resolve_origin(signal_origins)
        if proposal.change_type.value in self._HIGH_IMPACT and reviewed_evidence_count <= 0:
            return PromotionGateDecision(
                allowed=False,
                reason="reviewed evidence required for high-impact promotion",
                origin=origin,
                reviewed_evidence_count=reviewed_evidence_count,
                signal_origins=signal_origins,
            )
        return PromotionGateDecision(
            allowed=True,
            reason="",
            origin=origin,
            reviewed_evidence_count=reviewed_evidence_count,
            signal_origins=signal_origins,
        )

    def record_promotion(
        self,
        proposal: EvolutionProposal,
        *,
        origin: PromotionOrigin,
        reviewed_evidence_count: int,
        signal_origins: list[str],
        workspace_id: str = "",
        origin_finding_ref: str = "",
        origin_review_ref: str = "",
        promotion_target: str = "",
        promotion_reason: str = "",
    ) -> PromotionRecord:
        records = self.load_records()
        asset_key = self._asset_key(proposal)
        promotion_id = f"promo-{uuid.uuid4().hex[:12]}"
        for record in records:
            if record.asset_key == asset_key and record.status == "active":
                record.status = "superseded"
                record.discipline_verdict = "retire"
                record.superseded_by = promotion_id
        new_record = PromotionRecord(
            promotion_id=promotion_id,
            proposal_id=proposal.proposal_id,
            evolver_name=proposal.evolver_name,
            change_type=proposal.change_type.value,
            asset_key=asset_key,
            origin=origin.value,
            reviewed_evidence_count=reviewed_evidence_count,
            signal_origins=list(signal_origins),
            workspace_id=workspace_id,
            origin_finding_ref=origin_finding_ref,
            origin_review_ref=origin_review_ref,
            promotion_target=promotion_target,
            promotion_reason=promotion_reason,
            discipline_verdict="promote",
            created_at=datetime.now(UTC).isoformat(),
        )
        records.append(new_record)
        self.save_records(records)
        return new_record

    def rollback(self, promotion_id: str, *, reason: str) -> bool:
        records = self.load_records()
        updated = False
        for record in records:
            if record.promotion_id == promotion_id:
                record.status = "rolled_back"
                record.discipline_verdict = "rollback"
                record.rollback_reason = reason
                updated = True
                break
        if updated:
            self.save_records(records)
        return updated

    def retire(self, promotion_id: str, *, reason: str) -> bool:
        records = self.load_records()
        updated = False
        for record in records:
            if record.promotion_id == promotion_id:
                record.status = "retired"
                record.discipline_verdict = "retire"
                record.retirement_reason = reason
                updated = True
                break
        if updated:
            self.save_records(records)
        return updated

    @staticmethod
    def _resolve_origin(signal_origins: list[str]) -> PromotionOrigin:
        if "decision_review" in signal_origins:
            return PromotionOrigin.DECISION_REVIEW
        if "acceptance_review" in signal_origins:
            return PromotionOrigin.ACCEPTANCE_REVIEW
        if "execution" in signal_origins:
            return PromotionOrigin.EXECUTION
        return PromotionOrigin.SELF_REFLECTION

    @staticmethod
    def _asset_key(proposal: EvolutionProposal) -> str:
        content = proposal.content
        if proposal.change_type is EvolutionChangeType.PROMPT_VARIANT:
            return f"{proposal.evolver_name}:{proposal.change_type.value}"
        for field in ("variant_id", "intent_category", "policy_id", "skill_id"):
            value = content.get(field)
            if isinstance(value, str) and value.strip():
                return (
                    f"{proposal.evolver_name}:{proposal.change_type.value}:{field}:{value.strip()}"
                )
        return f"{proposal.evolver_name}:{proposal.change_type.value}"
