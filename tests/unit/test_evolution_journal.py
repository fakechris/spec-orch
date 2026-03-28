from __future__ import annotations

import json
from pathlib import Path

from spec_orch.domain.models import (
    EvolutionChangeType,
    EvolutionOutcome,
    EvolutionProposal,
    EvolutionValidationMethod,
)
from spec_orch.services.evolution_trigger import EvolutionConfig, EvolutionTrigger


class _DummyPromptEvolver:
    EVOLVER_NAME = "prompt_evolver"

    def observe(self, run_dirs: list[Path], *, context=None) -> list[dict]:
        return [{"run_dirs": len(run_dirs), "signal": "regression_cluster"}]

    def propose(self, evidence: list[dict], *, context=None) -> list[EvolutionProposal]:
        return [
            EvolutionProposal(
                proposal_id="proposal-1",
                evolver_name=self.EVOLVER_NAME,
                change_type=EvolutionChangeType.PROMPT_VARIANT,
                content={"variant_id": "v-next"},
                evidence=evidence,
                confidence=0.83,
            )
        ]

    def validate(self, proposal: EvolutionProposal) -> EvolutionOutcome:
        return EvolutionOutcome(
            proposal_id=proposal.proposal_id,
            accepted=True,
            validation_method=EvolutionValidationMethod.BACKTEST,
            metrics={"success_rate_delta": 0.17},
            reason="Backtest improved regression recovery.",
        )

    def promote(self, proposal: EvolutionProposal) -> bool:
        return True


def test_evolution_trigger_writes_granular_evolution_journal(tmp_path: Path) -> None:
    cfg = EvolutionConfig(
        enabled=True,
        trigger_after_n_runs=1,
        auto_promote=True,
        prompt_evolver_enabled=True,
        plan_strategy_evolver_enabled=False,
        harness_synthesizer_enabled=False,
        policy_distiller_enabled=False,
        config_evolver_enabled=False,
        intent_evolver_enabled=False,
        gate_policy_evolver_enabled=False,
        flow_policy_evolver_enabled=False,
        skill_evolver_enabled=False,
    )
    trigger = EvolutionTrigger(repo_root=tmp_path, config=cfg, latest_workspace=tmp_path)
    trigger._build_lifecycle_evolver = lambda name: _DummyPromptEvolver()  # type: ignore[method-assign]
    trigger._collect_run_dirs = lambda: [tmp_path / ".spec_orch_runs" / "run-1"]  # type: ignore[method-assign]
    trigger._assemble_evolver_context = lambda node_name: None  # type: ignore[method-assign]

    result = trigger.run_evolution_cycle()

    assert result.triggered is True
    journal_path = tmp_path / ".spec_orch_evolution" / "evolution_journal.jsonl"
    assert journal_path.exists()
    entries = [json.loads(line) for line in journal_path.read_text().splitlines() if line.strip()]
    assert [entry["stage"] for entry in entries] == ["observe", "propose", "validate", "promote"]
    assert entries[0]["evolver_name"] == "prompt_evolver"
    assert entries[1]["proposal_count"] == 1
    assert entries[2]["proposal_id"] == "proposal-1"
    assert entries[2]["accepted"] is True
    assert entries[3]["promoted"] is True
