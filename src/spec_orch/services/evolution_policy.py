"""Config-driven evolution trigger policy.

Determines which evolvers should run and in what priority order based on
configurable rules, run metrics, and thresholds.  Replaces the simple
``increment_and_check()`` counter with a per-evolver policy evaluation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_TRIGGER = "run_count"
_DEFAULT_THRESHOLD = 0.10
_DEFAULT_MIN_RUNS = 5


@dataclass(slots=True)
class EvolverPolicyRule:
    """Policy rule for a single evolver."""

    evolver_name: str
    enabled: bool = True
    min_runs: int = _DEFAULT_MIN_RUNS
    trigger_on: str = _DEFAULT_TRIGGER
    threshold: float = _DEFAULT_THRESHOLD

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> EvolverPolicyRule:
        return cls(
            evolver_name=name,
            enabled=data.get("enabled", True),
            min_runs=data.get("min_runs", _DEFAULT_MIN_RUNS),
            trigger_on=data.get("trigger_on", _DEFAULT_TRIGGER),
            threshold=data.get("threshold", _DEFAULT_THRESHOLD),
        )


@dataclass(slots=True)
class EvolutionPolicy:
    """Config-driven evolution trigger policy."""

    global_min_runs: int = _DEFAULT_MIN_RUNS
    rules: dict[str, EvolverPolicyRule] = field(default_factory=dict)

    @classmethod
    def from_toml(cls, data: dict[str, Any]) -> EvolutionPolicy:
        """Parse ``[evolution.policies]`` from spec-orch.toml."""
        evo = data.get("evolution", {})
        global_min = evo.get("trigger_after_n_runs", _DEFAULT_MIN_RUNS)
        policies_data = evo.get("policies", {})
        rules: dict[str, EvolverPolicyRule] = {}
        for name, rule_data in policies_data.items():
            if isinstance(rule_data, dict):
                rules[name] = EvolverPolicyRule.from_dict(name, rule_data)
        return cls(global_min_runs=global_min, rules=rules)

    def get_rule(self, evolver_name: str) -> EvolverPolicyRule:
        """Get a policy rule for an evolver (returns defaults if not configured)."""
        return self.rules.get(
            evolver_name,
            EvolverPolicyRule(evolver_name=evolver_name, min_runs=self.global_min_runs),
        )

    def should_trigger(
        self,
        evolver_name: str,
        run_count: int,
        metrics: dict[str, float] | None = None,
        *,
        skip_min_runs: bool = False,
    ) -> bool:
        """Evaluate whether an evolver should run based on its policy rule.

        When called from within an already-triggered evolution cycle
        (``skip_min_runs=True``), the ``min_runs`` gate is skipped because the
        global trigger threshold has already been satisfied.
        """
        rule = self.get_rule(evolver_name)
        if not rule.enabled:
            return False
        if not skip_min_runs and run_count < rule.min_runs:
            return False

        metrics = metrics or {}
        trigger = rule.trigger_on

        if trigger == "run_count":
            return True

        if trigger == "pass_rate_drop":
            pass_rate = metrics.get("pass_rate", 1.0)
            return pass_rate < (1.0 - rule.threshold)

        if trigger == "deviation_spike":
            avg_dev = metrics.get("avg_deviations", 0.0)
            return avg_dev > rule.threshold

        if trigger == "new_failure_pattern":
            new_patterns = metrics.get("new_failure_patterns", 0.0)
            return new_patterns > 0

        if trigger == "trajectory_available":
            trajectories = metrics.get("trajectory_count", 0.0)
            return trajectories > 0

        logger.debug(
            "Unknown trigger_on value '%s' for %s; defaulting to run_count", trigger, evolver_name
        )
        return True

    def priority_order(
        self,
        candidates: list[str],
        metrics: dict[str, float] | None = None,
    ) -> list[str]:
        """Order evolver names by priority based on trigger urgency.

        Evolvers whose trigger conditions are met are ordered before those
        that are only triggered by run count.  Within each group, the order
        preserves the input order.
        """
        metrics = metrics or {}
        urgent: list[str] = []
        normal: list[str] = []

        for name in candidates:
            rule = self.get_rule(name)
            if rule.trigger_on != "run_count" and self.should_trigger(name, rule.min_runs, metrics):
                urgent.append(name)
            else:
                normal.append(name)

        return urgent + normal
