"""Registry of NodeContextSpec instances for every LLM node in the system.

Maps each node name to its declared context requirements so that
ContextAssembler can fetch exactly the right data.
"""

from __future__ import annotations

from spec_orch.domain.context import NodeContextSpec

CONTEXT_SPECS: dict[str, NodeContextSpec] = {
    "readiness_checker": NodeContextSpec(
        node_name="readiness_checker",
        required_task_fields=["spec_snapshot_text", "acceptance_criteria"],
        required_execution_fields=["file_tree"],
        required_learning_fields=["similar_failure_samples"],
        max_tokens_budget=4000,
    ),
    "planner": NodeContextSpec(
        node_name="planner",
        required_task_fields=[
            "spec_snapshot_text",
            "acceptance_criteria",
            "constraints",
            "files_in_scope",
            "architecture_notes",
        ],
        required_execution_fields=["file_tree", "git_diff"],
        required_learning_fields=["scoper_hints"],
        max_tokens_budget=12000,
    ),
    "scoper": NodeContextSpec(
        node_name="scoper",
        required_task_fields=[
            "spec_snapshot_text",
            "acceptance_criteria",
            "constraints",
            "files_in_scope",
        ],
        required_execution_fields=["file_tree"],
        required_learning_fields=["scoper_hints"],
        max_tokens_budget=8000,
    ),
    "intent_classifier": NodeContextSpec(
        node_name="intent_classifier",
        required_task_fields=["spec_snapshot_text"],
        max_tokens_budget=2000,
    ),
    "llm_review": NodeContextSpec(
        node_name="llm_review",
        required_task_fields=[
            "spec_snapshot_text",
            "acceptance_criteria",
            "constraints",
        ],
        required_execution_fields=[
            "git_diff",
            "verification_results",
            "builder_events_summary",
        ],
        max_tokens_budget=8000,
    ),
    "prompt_evolver": NodeContextSpec(
        node_name="prompt_evolver",
        required_task_fields=["spec_snapshot_text"],
        required_learning_fields=["similar_failure_samples"],
        max_tokens_budget=4000,
    ),
    "plan_strategy_evolver": NodeContextSpec(
        node_name="plan_strategy_evolver",
        required_task_fields=["spec_snapshot_text"],
        required_learning_fields=["scoper_hints"],
        max_tokens_budget=4000,
    ),
    "intent_evolver": NodeContextSpec(
        node_name="intent_evolver",
        max_tokens_budget=2000,
    ),
    "harness_synthesizer": NodeContextSpec(
        node_name="harness_synthesizer",
        required_task_fields=["spec_snapshot_text"],
        required_learning_fields=["similar_failure_samples"],
        max_tokens_budget=4000,
    ),
    "policy_distiller": NodeContextSpec(
        node_name="policy_distiller",
        max_tokens_budget=4000,
    ),
    "smart_project_analyzer": NodeContextSpec(
        node_name="smart_project_analyzer",
        required_execution_fields=["file_tree"],
        max_tokens_budget=4000,
    ),
}

_DEFAULT_SPEC = NodeContextSpec(node_name="unknown", max_tokens_budget=4000)


def get_context_spec(node_name: str) -> NodeContextSpec:
    """Return the context spec for *node_name*, or a minimal default."""
    return CONTEXT_SPECS.get(
        node_name,
        NodeContextSpec(
            node_name=node_name,
            max_tokens_budget=_DEFAULT_SPEC.max_tokens_budget,
        ),
    )
