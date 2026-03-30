"""Tests for PromptEvolver — versioned prompts with A/B testing."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from spec_orch.services.prompt_evolver import PromptEvolver, PromptVariant

# ------------------------------------------------------------------
# Initialization and history persistence
# ------------------------------------------------------------------


def test_load_empty_history(tmp_path: Path) -> None:
    evolver = PromptEvolver(tmp_path)
    assert evolver.load_history() == []


def test_initialize_from_current(tmp_path: Path) -> None:
    evolver = PromptEvolver(tmp_path)
    v0 = evolver.initialize_from_current("Hello builder")
    assert v0.variant_id == "v0"
    assert v0.prompt_text == "Hello builder"
    assert v0.is_active is True

    reloaded = evolver.load_history()
    assert len(reloaded) == 1
    assert reloaded[0].variant_id == "v0"


def test_initialize_idempotent(tmp_path: Path) -> None:
    evolver = PromptEvolver(tmp_path)
    v0a = evolver.initialize_from_current("prompt A")
    v0b = evolver.initialize_from_current("prompt B")
    assert v0a.variant_id == v0b.variant_id == "v0"
    assert v0b.prompt_text == "prompt A"
    assert len(evolver.load_history()) == 1


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    evolver = PromptEvolver(tmp_path)
    variants = [
        PromptVariant(
            variant_id="v0", prompt_text="base", is_active=True, total_runs=10, successful_runs=8
        ),
        PromptVariant(
            variant_id="v1",
            prompt_text="improved",
            is_candidate=True,
            total_runs=5,
            successful_runs=4,
        ),
    ]
    evolver.save_history(variants)
    loaded = evolver.load_history()
    assert len(loaded) == 2
    assert loaded[0].success_rate == 0.8
    assert loaded[1].success_rate == 0.8


def test_get_active_prompt(tmp_path: Path) -> None:
    evolver = PromptEvolver(tmp_path)
    evolver.initialize_from_current("my prompt")
    active = evolver.get_active_prompt()
    assert active is not None
    assert active.variant_id == "v0"


def test_get_active_prompt_none(tmp_path: Path) -> None:
    evolver = PromptEvolver(tmp_path)
    assert evolver.get_active_prompt() is None


# ------------------------------------------------------------------
# Recording run outcomes
# ------------------------------------------------------------------


def test_record_run_success(tmp_path: Path) -> None:
    evolver = PromptEvolver(tmp_path)
    evolver.initialize_from_current("prompt")
    evolver.record_run("v0", succeeded=True)
    evolver.record_run("v0", succeeded=False)
    evolver.record_run("v0", succeeded=True)

    reloaded = evolver.load_history()
    assert reloaded[0].total_runs == 3
    assert reloaded[0].successful_runs == 2


def test_record_run_unknown_variant(tmp_path: Path) -> None:
    evolver = PromptEvolver(tmp_path)
    evolver.record_run("nonexistent", succeeded=True)


# ------------------------------------------------------------------
# Evolve (LLM-driven)
# ------------------------------------------------------------------


def test_evolve_no_planner(tmp_path: Path) -> None:
    evolver = PromptEvolver(tmp_path, planner=None)
    assert evolver.evolve() is None


def test_evolve_no_active_prompt(tmp_path: Path) -> None:
    planner = MagicMock()
    evolver = PromptEvolver(tmp_path, planner=planner)
    assert evolver.evolve() is None
    planner.brainstorm.assert_not_called()


def test_evolve_with_mock_planner(tmp_path: Path) -> None:
    planner = MagicMock()
    planner.brainstorm.return_value = json.dumps(
        {
            "variant_id": "v1",
            "prompt_text": "Improved prompt text",
            "rationale": "Added clearer constraints",
            "target_improvements": ["fewer deviations"],
        }
    )

    evolver = PromptEvolver(tmp_path, planner=planner)
    evolver.initialize_from_current("Original prompt")

    new_variant = evolver.evolve()
    assert new_variant is not None
    assert new_variant.variant_id == "v1"
    assert new_variant.prompt_text == "Improved prompt text"
    assert new_variant.is_candidate is True
    assert new_variant.is_active is False

    history = evolver.load_history()
    assert len(history) == 2

    call_args = planner.brainstorm.call_args
    messages = call_args.kwargs["conversation_history"]
    assert messages[0]["role"] == "system"
    assert "prompt-engineering specialist" in messages[0]["content"]


def test_prompt_evolver_system_prompt_includes_constitution() -> None:
    from spec_orch.services.evolution.prompt_evolver import _EVOLVE_SYSTEM_PROMPT

    assert "## Constitution" in _EVOLVE_SYSTEM_PROMPT
    assert "Prefer narrow, evidence-backed prompt changes." in _EVOLVE_SYSTEM_PROMPT
    assert "Do not widen change scope beyond the observed failure modes." in _EVOLVE_SYSTEM_PROMPT
    assert "Do not claim improvements that the evidence does not support." in _EVOLVE_SYSTEM_PROMPT


def test_render_context_for_prompt_includes_reviewed_decisions_and_acceptance() -> None:
    from spec_orch.domain.context import (
        ContextBundle,
        ExecutionContext,
        LearningContext,
        TaskContext,
    )
    from spec_orch.domain.models import Issue
    from spec_orch.services.evolution.prompt_evolver import PromptEvolver

    ctx = ContextBundle(
        task=TaskContext(
            issue=Issue(issue_id="SON-601", title="prompt evidence", summary=""),
            constraints=["keep scope narrow"],
        ),
        execution=ExecutionContext(deviation_slices=[{"kind": "retry-loop", "count": 2}]),
        learning=LearningContext(
            similar_failure_samples=[{"key": "fail-1", "content": "verification drift"}],
            reviewed_decision_failures=[{"record_id": "dr-1", "summary": "Prompt widened scope"}],
            reviewed_decision_recipes=[
                {"record_id": "dr-2", "summary": "Prompt kept actions concrete"}
            ],
            reviewed_acceptance_findings=[
                {"finding_id": "af-1", "summary": "Transcript route still hides retry evidence"}
            ],
        ),
    )

    rendered = PromptEvolver._render_context_for_prompt(ctx)

    assert "Reviewed decision failures:" in rendered
    assert "Reviewed decision recipes:" in rendered
    assert "Reviewed acceptance findings:" in rendered


def test_render_context_for_prompt_ignores_malformed_reviewed_entries() -> None:
    from spec_orch.domain.context import ContextBundle, LearningContext, TaskContext
    from spec_orch.domain.models import Issue
    from spec_orch.services.evolution.prompt_evolver import PromptEvolver

    ctx = ContextBundle(
        task=TaskContext(
            issue=Issue(issue_id="SON-602", title="prompt evidence", summary=""),
            constraints=["keep scope narrow"],
        ),
        learning=LearningContext(
            reviewed_decision_failures=["bad-entry", {"record_id": "dr-1", "summary": "useful"}],
            reviewed_decision_recipes=[None, {"record_id": "dr-2", "summary": "recipe"}],
            reviewed_acceptance_findings=[42, {"finding_id": "af-1", "summary": "finding"}],
        ),
    )

    rendered = PromptEvolver._render_context_for_prompt(ctx)

    assert "dr-1" in rendered
    assert "dr-2" in rendered
    assert "af-1" in rendered


def test_evolve_non_string_response(tmp_path: Path) -> None:
    planner = MagicMock()
    planner.brainstorm.return_value = None

    evolver = PromptEvolver(tmp_path, planner=planner)
    evolver.initialize_from_current("prompt")
    assert evolver.evolve() is None


def test_evolve_duplicate_variant_id(tmp_path: Path) -> None:
    planner = MagicMock()
    planner.brainstorm.return_value = json.dumps(
        {
            "variant_id": "v0",
            "prompt_text": "Clash with existing v0",
            "rationale": "test",
        }
    )

    evolver = PromptEvolver(tmp_path, planner=planner)
    evolver.initialize_from_current("base")
    new_variant = evolver.evolve()
    assert new_variant is not None
    assert new_variant.variant_id != "v0"


# ------------------------------------------------------------------
# A/B comparison and promotion
# ------------------------------------------------------------------


def test_compare_variants(tmp_path: Path) -> None:
    evolver = PromptEvolver(tmp_path)
    variants = [
        PromptVariant(
            variant_id="v0", prompt_text="a", is_active=True, total_runs=10, successful_runs=7
        ),
        PromptVariant(
            variant_id="v1", prompt_text="b", is_candidate=True, total_runs=10, successful_runs=9
        ),
    ]
    evolver.save_history(variants)

    result = evolver.compare_variants("v0", "v1")
    assert result is not None
    assert result.winner_id == "v1"
    assert result.loser_id == "v0"
    assert result.confidence == "medium"


def test_compare_insufficient_runs(tmp_path: Path) -> None:
    evolver = PromptEvolver(tmp_path)
    variants = [
        PromptVariant(variant_id="v0", prompt_text="a", total_runs=3, successful_runs=2),
        PromptVariant(variant_id="v1", prompt_text="b", total_runs=10, successful_runs=9),
    ]
    evolver.save_history(variants)

    result = evolver.compare_variants("v0", "v1")
    assert result is None


def test_promote_variant(tmp_path: Path) -> None:
    evolver = PromptEvolver(tmp_path)
    variants = [
        PromptVariant(variant_id="v0", prompt_text="a", is_active=True),
        PromptVariant(variant_id="v1", prompt_text="b", is_candidate=True),
    ]
    evolver.save_history(variants)

    assert evolver.promote_variant("v1") is True
    history = evolver.load_history()
    assert history[0].is_active is False
    assert history[1].is_active is True
    assert history[1].is_candidate is False


def test_promote_nonexistent(tmp_path: Path) -> None:
    evolver = PromptEvolver(tmp_path)
    assert evolver.promote_variant("v99") is False


def test_auto_promote_if_ready(tmp_path: Path) -> None:
    evolver = PromptEvolver(tmp_path)
    variants = [
        PromptVariant(
            variant_id="v0", prompt_text="a", is_active=True, total_runs=10, successful_runs=5
        ),
        PromptVariant(
            variant_id="v1", prompt_text="b", is_candidate=True, total_runs=8, successful_runs=7
        ),
    ]
    evolver.save_history(variants)

    result = evolver.auto_promote_if_ready()
    assert result is not None
    assert result.winner_id == "v1"

    history = evolver.load_history()
    active = [v for v in history if v.is_active]
    assert len(active) == 1
    assert active[0].variant_id == "v1"


def test_auto_promote_keeps_active_if_better(tmp_path: Path) -> None:
    evolver = PromptEvolver(tmp_path)
    variants = [
        PromptVariant(
            variant_id="v0", prompt_text="a", is_active=True, total_runs=10, successful_runs=9
        ),
        PromptVariant(
            variant_id="v1", prompt_text="b", is_candidate=True, total_runs=8, successful_runs=3
        ),
    ]
    evolver.save_history(variants)

    result = evolver.auto_promote_if_ready()
    assert result is not None
    assert result.winner_id == "v0"

    history = evolver.load_history()
    active = [v for v in history if v.is_active]
    assert active[0].variant_id == "v0"


def test_auto_promote_no_candidate(tmp_path: Path) -> None:
    evolver = PromptEvolver(tmp_path)
    variants = [
        PromptVariant(
            variant_id="v0", prompt_text="a", is_active=True, total_runs=10, successful_runs=5
        ),
    ]
    evolver.save_history(variants)
    assert evolver.auto_promote_if_ready() is None


# ------------------------------------------------------------------
# PromptVariant properties
# ------------------------------------------------------------------


def test_success_rate_zero_runs() -> None:
    v = PromptVariant(variant_id="v0", prompt_text="x")
    assert v.success_rate == 0.0


def test_malformed_history_file(tmp_path: Path) -> None:
    (tmp_path / "prompt_history.json").write_text("not valid json")
    evolver = PromptEvolver(tmp_path)
    assert evolver.load_history() == []


def test_non_list_history_file(tmp_path: Path) -> None:
    (tmp_path / "prompt_history.json").write_text('{"key": "value"}')
    evolver = PromptEvolver(tmp_path)
    assert evolver.load_history() == []


# ------------------------------------------------------------------
# CLI smoke tests
# ------------------------------------------------------------------


def test_prompt_init_cli(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from spec_orch.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["prompt", "init", "--repo-root", str(tmp_path)])
    assert result.exit_code == 0
    assert "v0" in result.output


def test_prompt_status_cli_empty(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from spec_orch.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["prompt", "status", "--repo-root", str(tmp_path)])
    assert result.exit_code == 0
    assert "No prompt history" in result.output


def test_prompt_status_cli_with_history(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from spec_orch.cli import app

    evolver = PromptEvolver(tmp_path)
    evolver.initialize_from_current("test prompt")
    evolver.record_run("v0", succeeded=True)

    runner = CliRunner()
    result = runner.invoke(app, ["prompt", "status", "--repo-root", str(tmp_path)])
    assert result.exit_code == 0
    assert "v0" in result.output
    assert "ACTIVE" in result.output


def test_prompt_auto_promote_cli_no_candidate(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from spec_orch.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["prompt", "auto-promote", "--repo-root", str(tmp_path)])
    assert result.exit_code == 0
    assert "No candidate" in result.output
