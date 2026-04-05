from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from spec_orch.domain.protocols import BuilderAdapter, IssueSource, PlannerAdapter, ReviewAdapter
from spec_orch.services.codex_exec_builder_adapter import CodexExecBuilderAdapter
from spec_orch.services.fixture_issue_source import FixtureIssueSource
from spec_orch.services.review_adapter import LocalReviewAdapter


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
    return ResolvedRunControllerAdapters(
        builder_adapter=adapter_bundle.builder_adapter
        or builder_adapter
        or CodexExecBuilderAdapter(executable=codex_executable),
        planner_adapter=adapter_bundle.planner_adapter if adapters is not None else planner_adapter,
        review_adapter=adapter_bundle.review_adapter or review_adapter or LocalReviewAdapter(),
        issue_source=adapter_bundle.issue_source
        or issue_source
        or FixtureIssueSource(repo_root=repo_root),
    )
