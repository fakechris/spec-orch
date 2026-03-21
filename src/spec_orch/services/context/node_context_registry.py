"""Registry of NodeContextSpec declarations for LLM nodes."""

from __future__ import annotations

from spec_orch.domain.context import NodeContextSpec

_TASK_FIELDS = {
    "spec_snapshot_text",
    "acceptance_criteria",
    "constraints",
    "files_in_scope",
    "files_out_of_scope",
    "architecture_notes",
}
_EXECUTION_FIELDS = {
    "file_tree",
    "git_diff",
    "verification_results",
    "gate_report",
    "builder_events_summary",
    "review_summary",
    "deviation_slices",
}
_LEARNING_FIELDS = {
    "recent_run_summary",
    "similar_failure_samples",
    "active_prompt_variant_id",
    "scoper_hints",
    "relevant_policies",
    "matched_skills",
}


NODE_CONTEXT_SPEC_REGISTRY: dict[str, NodeContextSpec] = {
    # SON-178 group A
    "readiness_checker": NodeContextSpec(
        node_name="readiness_checker",
        required_task_fields=["spec_snapshot_text", "acceptance_criteria", "constraints"],
        required_execution_fields=["file_tree"],
        required_learning_fields=["similar_failure_samples"],
        max_tokens_budget=6000,
    ),
    "planner": NodeContextSpec(
        node_name="planner",
        required_task_fields=["spec_snapshot_text", "constraints", "architecture_notes"],
        required_execution_fields=["file_tree", "verification_results"],
        required_learning_fields=["similar_failure_samples"],
        max_tokens_budget=9000,
    ),
    "scoper": NodeContextSpec(
        node_name="scoper",
        required_task_fields=["spec_snapshot_text", "files_in_scope", "constraints"],
        required_execution_fields=["file_tree", "git_diff"],
        required_learning_fields=["scoper_hints"],
        max_tokens_budget=8000,
    ),
    "intent_classifier": NodeContextSpec(
        node_name="intent_classifier",
        required_task_fields=["constraints"],
        required_execution_fields=[],
        required_learning_fields=["scoper_hints"],
        max_tokens_budget=4000,
    ),
    # Existing consumer
    "llm_reviewer": NodeContextSpec(
        node_name="llm_reviewer",
        required_task_fields=["acceptance_criteria", "constraints"],
        required_execution_fields=["git_diff", "verification_results", "gate_report"],
        required_learning_fields=["similar_failure_samples"],
        max_tokens_budget=10000,
    ),
    # SON-179 group B
    "prompt_evolver": NodeContextSpec(
        node_name="prompt_evolver",
        required_task_fields=["constraints"],
        required_execution_fields=["verification_results", "deviation_slices"],
        required_learning_fields=["similar_failure_samples"],
        max_tokens_budget=7000,
    ),
    "plan_strategy_evolver": NodeContextSpec(
        node_name="plan_strategy_evolver",
        required_task_fields=["constraints"],
        required_execution_fields=["verification_results", "deviation_slices"],
        required_learning_fields=["similar_failure_samples"],
        max_tokens_budget=7000,
    ),
    "flow_policy_evolver": NodeContextSpec(
        node_name="flow_policy_evolver",
        required_task_fields=["constraints"],
        required_execution_fields=["verification_results", "deviation_slices"],
        required_learning_fields=["similar_failure_samples"],
        max_tokens_budget=7000,
    ),
    "gate_policy_evolver": NodeContextSpec(
        node_name="gate_policy_evolver",
        required_task_fields=["constraints", "acceptance_criteria"],
        required_execution_fields=["verification_results", "gate_report"],
        required_learning_fields=["similar_failure_samples"],
        max_tokens_budget=7000,
    ),
    "intent_evolver": NodeContextSpec(
        node_name="intent_evolver",
        required_task_fields=["constraints"],
        required_execution_fields=["deviation_slices"],
        required_learning_fields=["scoper_hints", "similar_failure_samples"],
        max_tokens_budget=7000,
    ),
    "config_evolver": NodeContextSpec(
        node_name="config_evolver",
        required_task_fields=["constraints"],
        required_execution_fields=["verification_results", "deviation_slices"],
        required_learning_fields=["similar_failure_samples", "relevant_policies"],
        max_tokens_budget=7000,
    ),
    "harness_synthesizer": NodeContextSpec(
        node_name="harness_synthesizer",
        required_task_fields=["constraints"],
        required_execution_fields=["verification_results", "deviation_slices"],
        required_learning_fields=["similar_failure_samples"],
        max_tokens_budget=8000,
    ),
    "policy_distiller": NodeContextSpec(
        node_name="policy_distiller",
        required_task_fields=["constraints"],
        required_execution_fields=["verification_results"],
        required_learning_fields=["relevant_policies"],
        max_tokens_budget=7000,
    ),
}


def get_node_context_spec(node_name: str) -> NodeContextSpec:
    """Return a registered context spec for a node name."""
    try:
        return NODE_CONTEXT_SPEC_REGISTRY[node_name]
    except KeyError as exc:
        names = ", ".join(sorted(NODE_CONTEXT_SPEC_REGISTRY))
        raise KeyError(f"Unknown node '{node_name}'. Registered nodes: {names}") from exc


def validate_node_context_registry() -> None:
    """Validate registry consistency and field declarations."""
    for node_name, spec in NODE_CONTEXT_SPEC_REGISTRY.items():
        if node_name != spec.node_name:
            raise ValueError(
                f"Registry key '{node_name}' does not match spec.node_name '{spec.node_name}'."
            )
        if spec.max_tokens_budget <= 0:
            raise ValueError(f"Node '{node_name}' has non-positive max_tokens_budget.")

        unknown_task = set(spec.required_task_fields) - _TASK_FIELDS
        unknown_execution = set(spec.required_execution_fields) - _EXECUTION_FIELDS
        unknown_learning = set(spec.required_learning_fields) - _LEARNING_FIELDS
        if unknown_task or unknown_execution or unknown_learning:
            raise ValueError(
                f"Node '{node_name}' has unknown fields: "
                f"task={sorted(unknown_task)}, "
                f"execution={sorted(unknown_execution)}, "
                f"learning={sorted(unknown_learning)}"
            )


# Validate at import time so invalid declarations fail fast.
validate_node_context_registry()
