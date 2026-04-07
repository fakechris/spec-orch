"""Tests for Wave 3 case-driven evolution enhancements."""

from __future__ import annotations

import json
from pathlib import Path

from spec_orch.domain.models import (
    EvolutionChangeType,
    EvolutionProposal,
)
from spec_orch.services.evolution.plan_strategy_evolver import (
    HintSet,
    PlanStrategyEvolver,
    ScoperHint,
)
from spec_orch.services.policy_distiller import PolicyDistiller


def test_trajectory_candidates_empty(tmp_path: Path) -> None:
    pd = PolicyDistiller(tmp_path)
    assert pd.identify_trajectory_candidates() == []


def test_trajectory_candidates_found(tmp_path: Path) -> None:
    runs_dir = tmp_path / ".spec_orch_runs"
    runs_dir.mkdir()

    fail_dir = runs_dir / "run-fail"
    (fail_dir / "run_artifact").mkdir(parents=True)
    (fail_dir / "run_artifact" / "conclusion.json").write_text(
        json.dumps({"issue_id": "X-1", "mergeable": False, "failed_conditions": ["lint"]})
    )

    success_dir = runs_dir / "run-ok"
    (success_dir / "run_artifact").mkdir(parents=True)
    (success_dir / "run_artifact" / "conclusion.json").write_text(
        json.dumps({"issue_id": "X-1", "mergeable": True})
    )

    pd = PolicyDistiller(tmp_path)
    trajectories = pd.identify_trajectory_candidates()
    assert len(trajectories) == 1
    assert trajectories[0]["issue_id"] == "X-1"
    assert trajectories[0]["failure_conditions"] == ["lint"]


def test_pse_to_proposals() -> None:
    pse = PlanStrategyEvolver(Path("/tmp"))
    hint_set = HintSet(
        hints=[
            ScoperHint(hint_id="h1", text="Use single wave for small changes", confidence="high"),
            ScoperHint(hint_id="h2", text="Isolate DB migrations", confidence="low"),
        ]
    )
    proposals = pse.to_proposals(hint_set)
    assert len(proposals) == 2
    assert proposals[0].change_type == EvolutionChangeType.SCOPER_HINT
    assert proposals[0].confidence == 0.9
    assert proposals[1].confidence == 0.3


def test_pse_validate_accept() -> None:
    pse = PlanStrategyEvolver(Path("/tmp"))
    p = EvolutionProposal(
        proposal_id="pse-h1",
        evolver_name="plan_strategy_evolver",
        change_type=EvolutionChangeType.SCOPER_HINT,
        confidence=0.8,
    )
    outcome = pse.validate_proposal(p)
    assert outcome.accepted is True


def test_pse_validate_reject() -> None:
    pse = PlanStrategyEvolver(Path("/tmp"))
    p = EvolutionProposal(
        proposal_id="pse-h2",
        evolver_name="plan_strategy_evolver",
        change_type=EvolutionChangeType.SCOPER_HINT,
        confidence=0.2,
    )
    outcome = pse.validate_proposal(p)
    assert outcome.accepted is False
    assert "confidence" in outcome.reason


def test_pse_promote(tmp_path: Path) -> None:
    pse = PlanStrategyEvolver(tmp_path)
    p = EvolutionProposal(
        proposal_id="pse-h1",
        evolver_name="plan_strategy_evolver",
        change_type=EvolutionChangeType.SCOPER_HINT,
        content={"hint_id": "h1", "text": "Prefer small waves", "evidence": "data"},
        confidence=0.9,
    )
    assert pse.promote_proposal(p)
    loaded = pse.load_hints()
    assert any(h.hint_id == "h1" for h in loaded.hints)


def test_pse_promote_empty_text_rejected(tmp_path: Path) -> None:
    pse = PlanStrategyEvolver(tmp_path)
    p = EvolutionProposal(
        proposal_id="pse-empty",
        evolver_name="plan_strategy_evolver",
        change_type=EvolutionChangeType.SCOPER_HINT,
        content={"hint_id": "empty", "text": "", "evidence": ""},
        confidence=0.9,
    )
    assert not pse.promote_proposal(p)
