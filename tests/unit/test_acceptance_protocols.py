from __future__ import annotations

from pathlib import Path

from spec_orch.domain.models import (
    AcceptanceCampaign,
    AcceptanceReviewResult,
    BuilderResult,
    WorkPacket,
)
from spec_orch.domain.protocols import AcceptanceEvaluatorAdapter


def test_stub_acceptance_evaluator_is_protocol() -> None:
    class StubAcceptanceEvaluator:
        ADAPTER_NAME = "stub_acceptance"

        def evaluate_acceptance(
            self,
            *,
            mission_id: str,
            round_id: int,
            round_dir: Path,
            worker_results: list[tuple[WorkPacket, BuilderResult]],
            artifacts: dict[str, object],
            repo_root: Path,
            campaign: AcceptanceCampaign | None = None,
        ) -> AcceptanceReviewResult | None:
            return AcceptanceReviewResult(
                status="pass",
                summary="Looks good.",
                confidence=0.95,
                evaluator="stub_acceptance",
            )

    assert isinstance(StubAcceptanceEvaluator(), AcceptanceEvaluatorAdapter)
