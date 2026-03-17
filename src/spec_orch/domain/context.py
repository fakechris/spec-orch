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


@dataclass
class TaskContext:
    """Contract context: what the task is and what its boundaries are."""

    issue: Issue
    spec_snapshot_text: str = ""
    acceptance_criteria: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    files_in_scope: list[str] = field(default_factory=list)
    files_out_of_scope: list[str] = field(default_factory=list)
    architecture_notes: str = ""


@dataclass
class ExecutionContext:
    """Execution context: current code state and run facts."""

    file_tree: str = ""
    git_diff: str = ""
    verification_results: VerificationSummary | None = None
    gate_report: GateVerdict | None = None
    builder_events_summary: str = ""
    review_summary: ReviewSummary | None = None
    deviation_slices: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class LearningContext:
    """Learning context: historical experience and evolution artifacts."""

    recent_run_summary: dict[str, Any] | None = None
    similar_failure_samples: list[dict[str, Any]] = field(default_factory=list)
    active_prompt_variant_id: str = ""
    scoper_hints: list[dict[str, Any]] = field(default_factory=list)
    relevant_policies: list[str] = field(default_factory=list)


@dataclass
class ContextBundle:
    """Unified context package assembled by ContextAssembler.

    Each LLM node receives this instead of ad-hoc prompt fragments.
    """

    task: TaskContext
    execution: ExecutionContext = field(default_factory=ExecutionContext)
    learning: LearningContext = field(default_factory=LearningContext)


@dataclass
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
