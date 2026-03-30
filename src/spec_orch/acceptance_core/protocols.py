"""Protocol boundaries for acceptance-core seams."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from spec_orch.acceptance_core.models import AcceptanceJudgment
from spec_orch.acceptance_core.routing import AcceptanceRequest, AcceptanceRoutingDecision
from spec_orch.domain.models import AcceptanceReviewResult


class AcceptanceRoutingPolicy(Protocol):
    def route(self, request: AcceptanceRequest) -> AcceptanceRoutingDecision: ...


class AcceptanceJudgmentNormalizer(Protocol):
    def normalize(self, result: AcceptanceReviewResult) -> list[AcceptanceJudgment]: ...


class AcceptanceDispositionStore(Protocol):
    def append(self, repo_root: Path, mission_id: str, judgment: AcceptanceJudgment) -> Path: ...


__all__ = [
    "AcceptanceDispositionStore",
    "AcceptanceJudgmentNormalizer",
    "AcceptanceRoutingPolicy",
]
