"""Structured context types for LLM node consumption.

Defines the three-part ContextBundle (Task / Execution / Learning) and the
NodeContextSpec that each LLM node uses to declare its input requirements.
The ContextAssembler reads these specs to dynamically assemble the right
context from ArtifactRegistry + MemoryService.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from spec_orch.domain.models import (
    GateVerdict,
    Issue,
    ReviewSummary,
    VerificationSummary,
)


@dataclass(slots=True)
class TaskContext:
    """Contract context: what the task is and what its boundaries are."""

    issue: Issue
    spec_snapshot_text: str = ""
    acceptance_criteria: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    files_in_scope: list[str] = field(default_factory=list)
    files_out_of_scope: list[str] = field(default_factory=list)
    architecture_notes: str = ""


@dataclass(slots=True)
class ExecutionContext:
    """Execution context: current code state and run facts."""

    file_tree: str = ""
    git_diff: str = ""
    verification_results: VerificationSummary | None = None
    gate_report: GateVerdict | None = None
    builder_events_summary: str = ""
    review_summary: ReviewSummary | None = None
    deviation_slices: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class ProjectProfile:
    """Long-lived project-level profile assembled from memory."""

    tech_stack: list[str] = field(default_factory=list)
    common_failures: list[str] = field(default_factory=list)
    verification_commands: list[str] = field(default_factory=list)
    architecture_constraints: list[str] = field(default_factory=list)
    directory_hotspots: list[str] = field(default_factory=list)

    recent_success_rate: float | None = None
    recent_period_days: int = 7
    high_freq_failure_conditions: list[str] = field(default_factory=list)
    volatile_components: list[str] = field(default_factory=list)
    active_skills: list[str] = field(default_factory=list)
    active_policies: list[str] = field(default_factory=list)
    builder_adapter_performance: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class LearningContext:
    """Learning context: historical experience and evolution artifacts."""

    recent_run_summary: dict[str, Any] | None = None
    similar_failure_samples: list[dict[str, Any]] = field(default_factory=list)
    active_prompt_variant_id: str = ""
    scoper_hints: list[dict[str, Any]] = field(default_factory=list)
    relevant_policies: list[str] = field(default_factory=list)
    matched_skills: list[dict[str, Any]] = field(default_factory=list)
    relevant_procedures: list[dict[str, Any]] = field(default_factory=list)
    success_trend: dict[str, Any] | None = None
    project_profile: dict[str, Any] | None = None
    failure_patterns: list[dict[str, Any]] = field(default_factory=list)
    success_recipes: list[dict[str, Any]] = field(default_factory=list)
    active_run_signals: dict[str, Any] | None = None
    active_self_learnings: list[dict[str, Any]] = field(default_factory=list)
    active_delivery_learnings: list[dict[str, Any]] = field(default_factory=list)
    active_feedback_learnings: list[dict[str, Any]] = field(default_factory=list)
    recent_evolution_journal: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class ContextBundle:
    """Unified context package assembled by ContextAssembler.

    Each LLM node receives this instead of ad-hoc prompt fragments.
    """

    task: TaskContext
    execution: ExecutionContext = field(default_factory=ExecutionContext)
    learning: LearningContext = field(default_factory=LearningContext)


class CompactRetentionPriority:
    """Defines what to preserve during context compression.

    Priority order (highest first):
    1. Architecture decisions — never summarize
    2. Modified files and key changes
    3. Verification state (pass/fail)
    4. Unresolved TODOs and rollback notes
    5. Tool output — deletable, keep only pass/fail conclusion

    Identifiers (UUID, hash, URL, file path) must be preserved verbatim.
    """

    ARCHITECTURE_DECISIONS = 1
    MODIFIED_FILES = 2
    VERIFICATION_STATE = 3
    UNRESOLVED_TODOS = 4
    TOOL_OUTPUT = 5

    @staticmethod
    def retention_instructions() -> str:
        return (
            "When compacting context, preserve in this order:\n"
            "1. Architecture decisions — do NOT summarize\n"
            "2. Modified files and key changes\n"
            "3. Verification state (pass/fail)\n"
            "4. Unresolved TODOs and rollback notes\n"
            "5. Tool output — keep only pass/fail conclusions\n"
            "CRITICAL: Never modify identifiers (UUID, hash, IP, port, URL, file paths)."
        )


@dataclass(slots=True)
class NodeContextSpec:
    """Declares what context fields a specific LLM node needs.

    The ContextAssembler uses this to decide which data to fetch and how
    much token budget to allocate per section.
    """

    node_name: str
    required_task_fields: list[str] = field(default_factory=list)
    required_execution_fields: list[str] = field(default_factory=list)
    required_learning_fields: list[str] = field(default_factory=list)
    optional_fields: list[str] = field(default_factory=list)
    max_tokens_budget: int = 8000
    exclude_framework_events: bool = True
