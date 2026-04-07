from __future__ import annotations

import pytest

from spec_orch.services.context.node_context_registry import (
    NODE_CONTEXT_SPEC_REGISTRY,
    get_node_context_spec,
    validate_node_context_registry,
)


def test_registry_includes_group_a_nodes() -> None:
    for node in ("readiness_checker", "planner", "scoper", "intent_classifier"):
        assert node in NODE_CONTEXT_SPEC_REGISTRY


def test_registry_includes_evolver_nodes() -> None:
    for node in (
        "prompt_evolver",
        "plan_strategy_evolver",
        "flow_policy_evolver",
        "gate_policy_evolver",
        "intent_evolver",
        "config_evolver",
    ):
        assert node in NODE_CONTEXT_SPEC_REGISTRY


def test_get_node_context_spec_returns_matching_spec() -> None:
    spec = get_node_context_spec("planner")
    assert spec.node_name == "planner"
    assert "spec_snapshot_text" in spec.required_task_fields


def test_get_node_context_spec_raises_for_unknown_node() -> None:
    with pytest.raises(KeyError):
        get_node_context_spec("unknown_node")


def test_validate_node_context_registry_passes() -> None:
    validate_node_context_registry()
