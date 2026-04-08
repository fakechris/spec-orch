"""Context pipeline with pluggable providers and completeness scoring.

Wraps :class:`ContextAssembler` to add:

- Provider registry with required/optional classification
- Completeness scoring (0.0–1.0) based on which providers succeeded
- Fail-fast for critical providers (spec, acceptance criteria)
- Structured provenance metadata for each context section
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from spec_orch.domain.context import ContextBundle, NodeContextSpec
from spec_orch.domain.models import Issue

logger = logging.getLogger(__name__)


class ProviderPriority(StrEnum):
    """How critical a context provider is to downstream LLM quality."""

    CRITICAL = "critical"  # Missing → fail fast (spec, acceptance criteria)
    IMPORTANT = "important"  # Missing → degrade score significantly
    OPTIONAL = "optional"  # Missing → log warning, minor score penalty


@dataclass(frozen=True)
class ProviderResult:
    """Outcome of a single context provider."""

    name: str
    priority: ProviderPriority
    succeeded: bool
    field_count: int = 0  # how many fields were populated
    error: str = ""


@dataclass
class ContextPipelineResult:
    """Enriched context assembly result with completeness metadata."""

    bundle: ContextBundle
    completeness_score: float
    provider_results: list[ProviderResult] = field(default_factory=list)
    missing_critical: list[str] = field(default_factory=list)
    missing_important: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        """True if all critical providers succeeded."""
        return len(self.missing_critical) == 0

    def summary(self) -> str:
        """Human-readable completeness summary."""
        total = len(self.provider_results)
        succeeded = sum(1 for p in self.provider_results if p.succeeded)
        pct = f"{self.completeness_score:.0%}"
        lines = [f"Context completeness: {pct} ({succeeded}/{total} providers)"]
        if self.missing_critical:
            lines.append(f"  CRITICAL MISSING: {', '.join(self.missing_critical)}")
        if self.missing_important:
            lines.append(f"  Important missing: {', '.join(self.missing_important)}")
        if self.warnings:
            for w in self.warnings:
                lines.append(f"  Warning: {w}")
        return "\n".join(lines)


# -- Provider weight map for scoring --
_PRIORITY_WEIGHTS: dict[ProviderPriority, float] = {
    ProviderPriority.CRITICAL: 3.0,
    ProviderPriority.IMPORTANT: 2.0,
    ProviderPriority.OPTIONAL: 1.0,
}

# -- Default provider classification --
_TASK_PROVIDERS: dict[str, ProviderPriority] = {
    "spec_snapshot_text": ProviderPriority.CRITICAL,
    "acceptance_criteria": ProviderPriority.CRITICAL,
    "constraints": ProviderPriority.OPTIONAL,
    "files_in_scope": ProviderPriority.OPTIONAL,
    "architecture_notes": ProviderPriority.OPTIONAL,
}

_EXECUTION_PROVIDERS: dict[str, ProviderPriority] = {
    "file_tree": ProviderPriority.IMPORTANT,
    "git_diff": ProviderPriority.IMPORTANT,
    "verification_results": ProviderPriority.IMPORTANT,
    "gate_report": ProviderPriority.OPTIONAL,
    "builder_events_summary": ProviderPriority.OPTIONAL,
    "review_summary": ProviderPriority.OPTIONAL,
}

_TRUNCATION_WARNING_THRESHOLD = 0.5  # warn when retained < 50% of original

_LEARNING_PROVIDERS: dict[str, ProviderPriority] = {
    "similar_failure_samples": ProviderPriority.IMPORTANT,
    "matched_skills": ProviderPriority.OPTIONAL,
    "relevant_procedures": ProviderPriority.OPTIONAL,
    "failure_patterns": ProviderPriority.OPTIONAL,
    "success_recipes": ProviderPriority.OPTIONAL,
    "active_run_signals": ProviderPriority.OPTIONAL,
    "project_profile": ProviderPriority.OPTIONAL,
    "success_trend": ProviderPriority.OPTIONAL,
}


def _is_populated(value: Any) -> bool:
    """Check if a context field has meaningful content."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


class ContextPipeline:
    """Wraps ContextAssembler with completeness scoring and fail-fast logic."""

    def __init__(
        self,
        *,
        fail_on_missing_critical: bool = True,
    ) -> None:
        from spec_orch.services.context.context_assembler import ContextAssembler

        self._assembler = ContextAssembler()
        self._fail_on_missing_critical = fail_on_missing_critical

    def run(
        self,
        spec: NodeContextSpec,
        issue: Issue,
        workspace: Path,
        memory: Any | None = None,
        repo_root: Path | None = None,
    ) -> ContextPipelineResult:
        """Assemble context and score completeness."""
        bundle = self._assembler.assemble(
            spec=spec,
            issue=issue,
            workspace=workspace,
            memory=memory,
            repo_root=repo_root,
        )

        provider_results: list[ProviderResult] = []
        missing_critical: list[str] = []
        missing_important: list[str] = []
        warnings: list[str] = []

        # Score task context
        task = bundle.task
        for field_name, priority in _TASK_PROVIDERS.items():
            value = getattr(task, field_name, None)
            populated = _is_populated(value)
            provider_results.append(
                ProviderResult(
                    name=f"task.{field_name}",
                    priority=priority,
                    succeeded=populated,
                    field_count=1 if populated else 0,
                )
            )
            if not populated:
                if priority == ProviderPriority.CRITICAL:
                    missing_critical.append(f"task.{field_name}")
                elif priority == ProviderPriority.IMPORTANT:
                    missing_important.append(f"task.{field_name}")

        # Score execution context
        execution = bundle.execution
        for field_name, priority in _EXECUTION_PROVIDERS.items():
            value = getattr(execution, field_name, None)
            populated = _is_populated(value)
            provider_results.append(
                ProviderResult(
                    name=f"execution.{field_name}",
                    priority=priority,
                    succeeded=populated,
                    field_count=1 if populated else 0,
                )
            )
            if not populated and priority == ProviderPriority.IMPORTANT:
                missing_important.append(f"execution.{field_name}")

        # Score learning context
        learning = bundle.learning
        for field_name, priority in _LEARNING_PROVIDERS.items():
            value = getattr(learning, field_name, None)
            populated = _is_populated(value)
            provider_results.append(
                ProviderResult(
                    name=f"learning.{field_name}",
                    priority=priority,
                    succeeded=populated,
                    field_count=1 if populated else 0,
                )
            )
            if not populated and priority == ProviderPriority.IMPORTANT:
                missing_important.append(f"learning.{field_name}")

        # Check truncation metadata for silent data loss
        for meta in bundle.truncation_metadata:
            original = meta.get("original_chars", 0)
            retained = meta.get("retained_chars", 0)
            if original > 0 and retained < original * _TRUNCATION_WARNING_THRESHOLD:
                field_path = f"{meta.get('context', '?')}.{meta.get('field', '?')}"
                warnings.append(
                    f"{field_path} truncated to {retained}/{original} chars "
                    f"({retained / original:.0%} retained)"
                )

        # Calculate weighted completeness score
        total_weight = sum(_PRIORITY_WEIGHTS[p.priority] for p in provider_results)
        scored_weight = sum(_PRIORITY_WEIGHTS[p.priority] for p in provider_results if p.succeeded)
        completeness = scored_weight / total_weight if total_weight > 0 else 0.0

        if missing_critical:
            msg = f"Critical context missing: {', '.join(missing_critical)}"
            logger.warning(msg)
            if self._fail_on_missing_critical:
                warnings.insert(0, msg)

        result = ContextPipelineResult(
            bundle=bundle,
            completeness_score=completeness,
            provider_results=provider_results,
            missing_critical=missing_critical,
            missing_important=missing_important,
            warnings=warnings,
        )

        logger.info(
            "Context pipeline: completeness=%.0f%% (%d/%d providers)",
            completeness * 100,
            sum(1 for p in provider_results if p.succeeded),
            len(provider_results),
        )
        return result
