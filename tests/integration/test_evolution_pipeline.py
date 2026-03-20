"""Integration tests for the full evolution pipeline (Phase 2~3).

Verifies that the components work together end-to-end without requiring
actual LLM calls.
"""

from __future__ import annotations

import json
from pathlib import Path

from spec_orch.services.context_assembler import ContextAssembler
from spec_orch.services.evolution_policy import EvolutionPolicy
from spec_orch.services.evolution_trigger import EvolutionConfig, EvolutionTrigger
from spec_orch.services.node_context_registry import (
    get_node_context_spec,
    validate_node_context_registry,
)
from spec_orch.services.plan_strategy_evolver import HintSet, PlanStrategyEvolver, ScoperHint
from spec_orch.services.policy_distiller import PolicyDistiller


def test_registry_consistency() -> None:
    """All node context specs must be self-consistent."""
    validate_node_context_registry()


def test_new_specs_registered() -> None:
    """Wave 2 registered specs for HS and PD."""
    hs_spec = get_node_context_spec("harness_synthesizer")
    assert "similar_failure_samples" in hs_spec.required_learning_fields

    pd_spec = get_node_context_spec("policy_distiller")
    assert "relevant_policies" in pd_spec.required_learning_fields


def test_context_assembler_loads_policies(tmp_path: Path) -> None:
    """LearningContext.relevant_policies populated from policies_index.json."""
    policies_dir = tmp_path / "policies"
    policies_dir.mkdir()
    (policies_dir / "policies_index.json").write_text(
        json.dumps(
            [
                {"policy_id": "fix-lint", "name": "Fix Lint"},
                {"policy_id": "fix-test", "name": "Fix Tests"},
            ]
        )
    )
    (tmp_path / "spec_snapshot.json").write_text(
        json.dumps({"issue": {"issue_id": "T-1", "title": "test"}})
    )

    from spec_orch.domain.models import Issue, IssueContext

    assembler = ContextAssembler()
    spec = get_node_context_spec("policy_distiller")
    issue = Issue(issue_id="T-1", title="test", summary="test", context=IssueContext())
    bundle = assembler.assemble(spec, issue, tmp_path, repo_root=tmp_path)

    assert "fix-lint" in bundle.learning.relevant_policies
    assert "fix-test" in bundle.learning.relevant_policies


def test_policy_from_toml() -> None:
    """EvolutionPolicy parses toml config correctly."""
    toml_data = {
        "evolution": {
            "trigger_after_n_runs": 10,
            "policies": {
                "prompt_evolver": {
                    "min_runs": 5,
                    "trigger_on": "pass_rate_drop",
                    "threshold": 0.15,
                },
            },
        }
    }
    policy = EvolutionPolicy.from_toml(toml_data)
    assert policy.should_trigger("prompt_evolver", 5, {"pass_rate": 0.7})
    assert not policy.should_trigger("prompt_evolver", 3, {"pass_rate": 0.7})


def test_pse_full_lifecycle(tmp_path: Path) -> None:
    """PlanStrategyEvolver: propose → validate → promote."""
    pse = PlanStrategyEvolver(tmp_path)
    hints = HintSet(
        hints=[
            ScoperHint(hint_id="iso-db", text="Isolate DB migrations", confidence="high"),
            ScoperHint(hint_id="tiny", text="Be tiny", confidence="low"),
        ]
    )
    proposals = pse.to_proposals(hints)
    assert len(proposals) == 2

    promoted = 0
    for p in proposals:
        outcome = pse.validate_proposal(p)
        if outcome.accepted:
            assert pse.promote_proposal(p)
            promoted += 1

    assert promoted == 1
    saved = pse.load_hints()
    assert any(h.hint_id == "iso-db" for h in saved.hints)


def test_trajectory_mining_integration(tmp_path: Path) -> None:
    """PolicyDistiller finds trajectories across run history."""
    runs_dir = tmp_path / ".spec_orch_runs"
    runs_dir.mkdir()

    for i in range(3):
        rd = runs_dir / f"run-{i}"
        (rd / "run_artifact").mkdir(parents=True)
        (rd / "run_artifact" / "conclusion.json").write_text(
            json.dumps(
                {
                    "issue_id": "ISS-1" if i < 2 else "ISS-2",
                    "mergeable": i == 1,
                    "failed_conditions": ["lint"] if i != 1 else [],
                }
            )
        )

    pd = PolicyDistiller(tmp_path)
    trajectories = pd.identify_trajectory_candidates()
    assert len(trajectories) == 1
    assert trajectories[0]["issue_id"] == "ISS-1"


def test_evolution_trigger_with_policy(tmp_path: Path) -> None:
    """EvolutionTrigger uses EvolutionPolicy for trigger decisions."""
    config = EvolutionConfig(
        enabled=True,
        trigger_after_n_runs=1,
        prompt_evolver_enabled=False,
        plan_strategy_evolver_enabled=False,
        harness_synthesizer_enabled=False,
        policy_distiller_enabled=False,
        config_evolver_enabled=False,
    )
    policy = EvolutionPolicy(global_min_runs=1)
    trigger = EvolutionTrigger(
        repo_root=tmp_path,
        config=config,
        policy=policy,
    )
    result = trigger.run_evolution_cycle()
    assert result.triggered
    assert result.errors == []
