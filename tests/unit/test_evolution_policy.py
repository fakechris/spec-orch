"""Tests for EvolutionPolicy engine."""

from __future__ import annotations

from spec_orch.services.evolution_policy import (
    EvolutionPolicy,
    EvolverPolicyRule,
)


def test_from_toml_empty() -> None:
    policy = EvolutionPolicy.from_toml({})
    assert policy.global_min_runs == 5
    assert policy.rules == {}


def test_from_toml_with_policies() -> None:
    toml_data = {
        "evolution": {
            "trigger_after_n_runs": 10,
            "policies": {
                "prompt_evolver": {
                    "min_runs": 5,
                    "trigger_on": "pass_rate_drop",
                    "threshold": 0.1,
                },
                "harness_synthesizer": {
                    "min_runs": 10,
                    "trigger_on": "new_failure_pattern",
                },
            },
        }
    }
    policy = EvolutionPolicy.from_toml(toml_data)
    assert policy.global_min_runs == 10
    assert len(policy.rules) == 2
    assert policy.rules["prompt_evolver"].trigger_on == "pass_rate_drop"


def test_should_trigger_run_count() -> None:
    policy = EvolutionPolicy(global_min_runs=5)
    assert not policy.should_trigger("prompt_evolver", 3)
    assert policy.should_trigger("prompt_evolver", 5)
    assert policy.should_trigger("prompt_evolver", 10)


def test_should_trigger_pass_rate_drop() -> None:
    policy = EvolutionPolicy(
        rules={
            "prompt_evolver": EvolverPolicyRule(
                evolver_name="prompt_evolver",
                min_runs=5,
                trigger_on="pass_rate_drop",
                threshold=0.1,
            )
        }
    )
    assert not policy.should_trigger("prompt_evolver", 5, {"pass_rate": 0.95})
    assert policy.should_trigger("prompt_evolver", 5, {"pass_rate": 0.8})


def test_should_trigger_deviation_spike() -> None:
    policy = EvolutionPolicy(
        rules={
            "plan_strategy": EvolverPolicyRule(
                evolver_name="plan_strategy",
                min_runs=5,
                trigger_on="deviation_spike",
                threshold=0.1,
            )
        }
    )
    assert not policy.should_trigger("plan_strategy", 5, {"avg_deviations": 0.05})
    assert policy.should_trigger("plan_strategy", 5, {"avg_deviations": 0.2})


def test_should_trigger_new_failure_pattern() -> None:
    policy = EvolutionPolicy(
        rules={
            "harness_synthesizer": EvolverPolicyRule(
                evolver_name="harness_synthesizer",
                min_runs=10,
                trigger_on="new_failure_pattern",
            )
        }
    )
    assert not policy.should_trigger("harness_synthesizer", 10, {"new_failure_patterns": 0})
    assert policy.should_trigger("harness_synthesizer", 10, {"new_failure_patterns": 3})


def test_should_trigger_trajectory_available() -> None:
    policy = EvolutionPolicy(
        rules={
            "policy_distiller": EvolverPolicyRule(
                evolver_name="policy_distiller",
                min_runs=10,
                trigger_on="trajectory_available",
            )
        }
    )
    assert not policy.should_trigger("policy_distiller", 10, {"trajectory_count": 0})
    assert policy.should_trigger("policy_distiller", 10, {"trajectory_count": 2})


def test_should_trigger_disabled() -> None:
    policy = EvolutionPolicy(rules={"test": EvolverPolicyRule(evolver_name="test", enabled=False)})
    assert not policy.should_trigger("test", 100)


def test_priority_order() -> None:
    policy = EvolutionPolicy(
        global_min_runs=5,
        rules={
            "prompt_evolver": EvolverPolicyRule(
                evolver_name="prompt_evolver",
                min_runs=5,
                trigger_on="pass_rate_drop",
                threshold=0.1,
            ),
            "harness_synthesizer": EvolverPolicyRule(
                evolver_name="harness_synthesizer",
                min_runs=5,
                trigger_on="new_failure_pattern",
            ),
        },
    )
    metrics = {"pass_rate": 0.7, "new_failure_patterns": 2}
    ordered = policy.priority_order(
        ["config_evolver", "prompt_evolver", "harness_synthesizer"],
        metrics,
    )
    assert ordered[0] == "prompt_evolver"
    assert ordered[1] == "harness_synthesizer"
    assert ordered[2] == "config_evolver"


def test_get_rule_default() -> None:
    policy = EvolutionPolicy(global_min_runs=7)
    rule = policy.get_rule("unknown_evolver")
    assert rule.evolver_name == "unknown_evolver"
    assert rule.min_runs == 7
    assert rule.trigger_on == "run_count"
