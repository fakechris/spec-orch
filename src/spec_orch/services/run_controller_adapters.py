from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from spec_orch.domain.protocols import BuilderAdapter, IssueSource, PlannerAdapter, ReviewAdapter
from spec_orch.services.builders.adapter_factory import (
    create_builder,
    create_issue_source,
    create_reviewer,
)


@dataclass(frozen=True)
class RunControllerAdapters:
    builder_adapter: BuilderAdapter | None = None
    planner_adapter: PlannerAdapter | None = None
    review_adapter: ReviewAdapter | None = None
    issue_source: IssueSource | None = None


@dataclass(frozen=True)
class ResolvedRunControllerAdapters:
    builder_adapter: BuilderAdapter
    planner_adapter: PlannerAdapter | None
    review_adapter: ReviewAdapter
    issue_source: IssueSource


def resolve_run_controller_adapters(
    *,
    repo_root: Path,
    codex_executable: str,
    builder_adapter: BuilderAdapter | None = None,
    planner_adapter: PlannerAdapter | None = None,
    review_adapter: ReviewAdapter | None = None,
    issue_source: IssueSource | None = None,
    adapters: RunControllerAdapters | None = None,
) -> ResolvedRunControllerAdapters:
    adapter_bundle = adapters or RunControllerAdapters()
    resolved_builder = adapter_bundle.builder_adapter or builder_adapter
    resolved_planner = adapter_bundle.planner_adapter or planner_adapter
    if resolved_builder is None:
        resolved_builder = create_builder(repo_root)
        if (
            codex_executable != "codex"
            and getattr(resolved_builder, "ADAPTER_NAME", "") == "codex_exec"
            and hasattr(resolved_builder, "executable")
        ):
            resolved_builder.executable = codex_executable

    return ResolvedRunControllerAdapters(
        builder_adapter=resolved_builder,
        planner_adapter=resolved_planner,
        review_adapter=(
            adapter_bundle.review_adapter or review_adapter or create_reviewer(repo_root)
        ),
        issue_source=adapter_bundle.issue_source or issue_source or create_issue_source(repo_root),
    )
