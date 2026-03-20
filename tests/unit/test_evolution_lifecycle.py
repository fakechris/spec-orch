"""Tests for evolution lifecycle protocol and dataclasses."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from spec_orch.domain.models import (
    EvolutionChangeType,
    EvolutionOutcome,
    EvolutionProposal,
    EvolutionValidationMethod,
)
from spec_orch.domain.protocols import Evolver


class FakeEvolver:
    """Minimal implementation to verify the Evolver protocol."""

    EVOLVER_NAME = "fake_evolver"

    def observe(self, run_dirs: list[Path], *, context: Any | None = None) -> list[dict[str, Any]]:
        return [{"run_dir": str(d)} for d in run_dirs]

    def propose(
        self, evidence: list[dict[str, Any]], *, context: Any | None = None
    ) -> list[EvolutionProposal]:
        return [
            EvolutionProposal(
                proposal_id="p1",
                evolver_name=self.EVOLVER_NAME,
                change_type=EvolutionChangeType.PROMPT_VARIANT,
                content={"variant": "new_prompt"},
                evidence=evidence,
                confidence=0.8,
            )
        ]

    def validate(self, proposal: EvolutionProposal) -> EvolutionOutcome:
        return EvolutionOutcome(
            proposal_id=proposal.proposal_id,
            accepted=True,
            validation_method=EvolutionValidationMethod.AUTO,
            metrics={"pass_rate": 0.9},
        )

    def promote(self, proposal: EvolutionProposal) -> bool:
        return True


def test_fake_evolver_satisfies_protocol() -> None:
    e = FakeEvolver()
    assert isinstance(e, Evolver)


def test_evolution_proposal_to_dict() -> None:
    p = EvolutionProposal(
        proposal_id="p1",
        evolver_name="test",
        change_type=EvolutionChangeType.SCOPER_HINT,
        content={"hint": "prefer small waves"},
        evidence=[{"run_id": "r1"}, {"run_id": "r2"}],
        confidence=0.75,
    )
    d = p.to_dict()
    assert d["change_type"] == "scoper_hint"
    assert d["evidence_count"] == 2
    assert d["confidence"] == 0.75


def test_evolution_outcome_to_dict() -> None:
    o = EvolutionOutcome(
        proposal_id="p1",
        accepted=False,
        validation_method=EvolutionValidationMethod.BACKTEST,
        metrics={"false_positive_rate": 0.3},
        reason="too many false positives",
    )
    d = o.to_dict()
    assert d["accepted"] is False
    assert d["validation_method"] == "backtest"
    assert d["reason"] == "too many false positives"


def test_change_type_enum_values() -> None:
    assert EvolutionChangeType.PROMPT_VARIANT == "prompt_variant"
    assert EvolutionChangeType.POLICY == "policy"
    assert EvolutionChangeType.HARNESS_RULE == "harness_rule"


def test_full_lifecycle_flow() -> None:
    e = FakeEvolver()
    evidence = e.observe([Path("/tmp/run1")])
    proposals = e.propose(evidence)
    assert len(proposals) == 1
    outcome = e.validate(proposals[0])
    assert outcome.accepted
    assert e.promote(proposals[0])
