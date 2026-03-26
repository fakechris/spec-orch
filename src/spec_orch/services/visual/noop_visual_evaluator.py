from __future__ import annotations

from pathlib import Path

from spec_orch.domain.models import BuilderResult, VisualEvaluationResult, Wave, WorkPacket


class NoopVisualEvaluator:
    """Default visual evaluator that intentionally does nothing."""

    ADAPTER_NAME = "noop"

    def evaluate_round(
        self,
        *,
        mission_id: str,
        round_id: int,
        wave: Wave,
        worker_results: list[tuple[WorkPacket, BuilderResult]],
        repo_root: Path,
        round_dir: Path,
    ) -> VisualEvaluationResult | None:
        return None
