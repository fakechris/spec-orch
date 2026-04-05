from __future__ import annotations

import copy
from pathlib import Path
from unittest.mock import MagicMock

from spec_orch.domain.models import (
    ExecutionPlan,
    RoundAction,
    RoundArtifacts,
    RoundDecision,
    RoundStatus,
    RoundSummary,
    Wave,
)
from spec_orch.services.round_review_coordinator import RoundReviewCoordinator


def test_round_review_coordinator_persists_reviewing_state_before_supervisor_call(
    tmp_path: Path,
) -> None:
    host = MagicMock()
    host.repo_root = tmp_path
    host._build_supervisor_issue.return_value = MagicMock()
    host._build_supervisor_context.return_value = {}
    host.context_assembler.assemble.return_value = {"node": "supervisor"}
    host._call_runtime_chain_aware.return_value = RoundDecision(
        action=RoundAction.CONTINUE,
        summary="Continue",
    )

    persisted: list[RoundSummary] = []
    host._persist_round.side_effect = lambda _round_dir, current: persisted.append(
        copy.deepcopy(current)
    )

    summary = RoundSummary(round_id=1, wave_id=0, status=RoundStatus.EXECUTING)
    coordinator = RoundReviewCoordinator()

    coordinator.review(
        host=host,
        mission_id="mission-1",
        round_id=1,
        round_dir=tmp_path / "round-01",
        wave=Wave(wave_number=0, description="Wave 0", work_packets=[]),
        artifacts=RoundArtifacts(round_id=1, mission_id="mission-1"),
        plan=ExecutionPlan(plan_id="plan-1", mission_id="mission-1", waves=[]),
        round_history=[],
        summary=summary,
        chain_root=tmp_path / "chain",
        chain_id="chain-1",
        round_span_id="round-span-1",
    )

    first_persist = persisted[0]
    second_persist = persisted[1]

    assert first_persist.status is RoundStatus.REVIEWING
    assert second_persist.status is RoundStatus.DECIDED
