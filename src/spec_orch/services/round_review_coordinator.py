from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from spec_orch.domain.models import (
    ExecutionPlan,
    RoundArtifacts,
    RoundDecision,
    RoundStatus,
    RoundSummary,
    Wave,
)
from spec_orch.services.context.node_context_registry import get_node_context_spec


class RoundReviewCoordinator:
    """Owns supervisor review preparation and decision persistence for a round."""

    def review(
        self,
        *,
        host: Any,
        mission_id: str,
        round_id: int,
        round_dir: Path,
        wave: Wave,
        artifacts: RoundArtifacts,
        plan: ExecutionPlan,
        round_history: list[RoundSummary],
        summary: RoundSummary,
        chain_root: Path,
        chain_id: str,
        round_span_id: str,
    ) -> RoundDecision:
        supervisor_issue = host._build_supervisor_issue(
            mission_id=mission_id,
            round_id=round_id,
            wave=wave,
        )
        host._write_supervisor_task_spec(
            round_dir=round_dir,
            mission_id=mission_id,
            wave=wave,
        )
        summary.status = RoundStatus.REVIEWING
        host._persist_round(round_dir, summary)

        assembled_context = host.context_assembler.assemble(
            get_node_context_spec("supervisor"),
            supervisor_issue,
            round_dir,
            repo_root=host.repo_root,
        )
        context = host._build_supervisor_context(
            mission_id=mission_id,
            round_id=round_id,
            wave=wave,
            issue=supervisor_issue,
            assembled_context=assembled_context,
            artifacts=artifacts,
        )
        decision = cast(
            RoundDecision,
            host._call_runtime_chain_aware(
                host.supervisor.review_round,
                round_artifacts=artifacts,
                plan=plan,
                round_history=round_history,
                context=context,
                chain_root=chain_root,
                chain_id=chain_id,
                span_id=f"{round_span_id}:supervisor",
                parent_span_id=round_span_id,
            ),
        )
        summary.decision = decision
        summary.status = RoundStatus.DECIDED
        summary.completed_at = datetime.now(UTC).isoformat()
        host._persist_round(round_dir, summary)
        return decision
