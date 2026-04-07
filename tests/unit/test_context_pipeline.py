"""Tests for ContextPipeline completeness scoring."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from spec_orch.domain.context import (
    ContextBundle,
    EvidenceContext,
    ExecutionContext,
    LearningContext,
    NodeContextSpec,
    PromotedLearningContext,
    TaskContext,
)
from spec_orch.domain.models import Issue, IssueContext
from spec_orch.services.context.context_pipeline import (
    ContextPipeline,
    ProviderPriority,
    _is_populated,
)


def _make_issue() -> Issue:
    return Issue(
        issue_id="SPC-1",
        title="Test issue",
        summary="A test",
        context=IssueContext(),
    )


def _make_spec() -> NodeContextSpec:
    return NodeContextSpec(
        node_name="test_node",
        required_task_fields=["spec_snapshot_text", "acceptance_criteria"],
        required_execution_fields=["file_tree"],
        required_learning_fields=[],
        max_tokens_budget=4000,
    )


def _make_bundle(
    *,
    spec_text: str = "spec content",
    acceptance: list[str] | None = None,
    file_tree: str = "src/\n  main.py",
) -> ContextBundle:
    issue = _make_issue()
    return ContextBundle(
        task=TaskContext(
            issue=issue,
            spec_snapshot_text=spec_text,
            acceptance_criteria=acceptance or ["test passes"],
        ),
        execution=ExecutionContext(
            file_tree=file_tree,
        ),
        learning=LearningContext(),
        evidence=EvidenceContext(),
        promoted_learning=PromotedLearningContext(),
    )


def test_full_context_scores_high(tmp_path: Path) -> None:
    bundle = _make_bundle()
    pipeline = ContextPipeline(fail_on_missing_critical=False)

    with patch.object(pipeline._assembler, "assemble", return_value=bundle):
        result = pipeline.run(
            spec=_make_spec(),
            issue=_make_issue(),
            workspace=tmp_path,
        )

    # Critical providers (spec, acceptance) are present
    assert result.is_complete
    assert result.missing_critical == []
    # Score reflects that optional/important learning providers are empty
    assert result.completeness_score > 0.2


def test_missing_spec_lowers_score_and_flags_critical(tmp_path: Path) -> None:
    bundle = _make_bundle(spec_text="")
    # Manually clear acceptance to truly empty
    bundle.task.acceptance_criteria = []
    pipeline = ContextPipeline(fail_on_missing_critical=False)

    with patch.object(pipeline._assembler, "assemble", return_value=bundle):
        result = pipeline.run(
            spec=_make_spec(),
            issue=_make_issue(),
            workspace=tmp_path,
        )

    assert not result.is_complete
    assert "task.spec_snapshot_text" in result.missing_critical
    assert "task.acceptance_criteria" in result.missing_critical
    assert result.completeness_score < 0.8


def test_truncation_generates_warning(tmp_path: Path) -> None:
    bundle = _make_bundle()
    bundle.truncation_metadata = [
        {
            "context": "task",
            "field": "spec_snapshot_text",
            "original_chars": 10000,
            "retained_chars": 2000,
        }
    ]
    pipeline = ContextPipeline(fail_on_missing_critical=False)

    with patch.object(pipeline._assembler, "assemble", return_value=bundle):
        result = pipeline.run(
            spec=_make_spec(),
            issue=_make_issue(),
            workspace=tmp_path,
        )

    assert any("truncated" in w for w in result.warnings)


def test_summary_output(tmp_path: Path) -> None:
    bundle = _make_bundle(spec_text="")
    pipeline = ContextPipeline(fail_on_missing_critical=False)

    with patch.object(pipeline._assembler, "assemble", return_value=bundle):
        result = pipeline.run(
            spec=_make_spec(),
            issue=_make_issue(),
            workspace=tmp_path,
        )

    summary = result.summary()
    assert "Context completeness" in summary
    assert "CRITICAL MISSING" in summary


def test_is_populated_helper() -> None:
    assert _is_populated("hello")
    assert not _is_populated("")
    assert not _is_populated(None)
    assert _is_populated(["item"])
    assert not _is_populated([])
    assert _is_populated({"key": "val"})
    assert not _is_populated({})
    assert _is_populated(42)


def test_provider_priority_values() -> None:
    assert ProviderPriority.CRITICAL == "critical"
    assert ProviderPriority.IMPORTANT == "important"
    assert ProviderPriority.OPTIONAL == "optional"
