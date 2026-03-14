"""Tests for PlanStrategyEvolver — scoper hints from historical plan outcomes."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from spec_orch.services.plan_strategy_evolver import (
    HintSet,
    PlanStrategyEvolver,
    ScoperHint,
)


def _write_report(run_dir: Path, report: dict) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "report.json").write_text(json.dumps(report))


def _write_deviations(run_dir: Path, deviations: list[dict]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(d) for d in deviations]
    (run_dir / "deviations.jsonl").write_text("\n".join(lines))


# ------------------------------------------------------------------
# Load / save hints
# ------------------------------------------------------------------


def test_load_empty_hints(tmp_path: Path) -> None:
    evolver = PlanStrategyEvolver(tmp_path)
    hint_set = evolver.load_hints()
    assert hint_set.hints == []
    assert hint_set.analysis_summary == ""


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    evolver = PlanStrategyEvolver(tmp_path)
    hints = HintSet(
        hints=[
            ScoperHint(hint_id="h1", text="Isolate migrations in wave-0", confidence="high"),
            ScoperHint(hint_id="h2", text="Test files need own packet", confidence="medium"),
        ],
        analysis_summary="Migrations correlate with failures.",
        generated_at="2026-03-10T00:00:00Z",
    )
    evolver.save_hints(hints)
    loaded = evolver.load_hints()
    assert len(loaded.hints) == 2
    assert loaded.hints[0].hint_id == "h1"
    assert loaded.analysis_summary == "Migrations correlate with failures."


def test_load_malformed_file(tmp_path: Path) -> None:
    (tmp_path / "scoper_hints.json").write_text("not json")
    evolver = PlanStrategyEvolver(tmp_path)
    assert evolver.load_hints().hints == []


def test_load_non_dict_file(tmp_path: Path) -> None:
    (tmp_path / "scoper_hints.json").write_text("[1, 2, 3]")
    evolver = PlanStrategyEvolver(tmp_path)
    assert evolver.load_hints().hints == []


# ------------------------------------------------------------------
# collect_plan_outcomes
# ------------------------------------------------------------------


def test_collect_empty(tmp_path: Path) -> None:
    evolver = PlanStrategyEvolver(tmp_path)
    assert evolver.collect_plan_outcomes() == {}


def test_collect_with_runs(tmp_path: Path) -> None:
    rd1 = tmp_path / ".spec_orch_runs" / "ISSUE-1"
    _write_report(
        rd1,
        {
            "mergeable": True,
            "failed_conditions": [],
            "verification": {"pytest": {"exit_code": 0}},
            "metadata": {"plan": [{"wave": 0}]},
        },
    )

    rd2 = tmp_path / ".spec_orch_runs" / "ISSUE-2"
    _write_report(
        rd2,
        {
            "mergeable": False,
            "failed_conditions": ["verification"],
            "verification": {"ruff": {"exit_code": 1}},
        },
    )
    _write_deviations(rd2, [{"file_path": "src/foo.py", "severity": "major"}])

    evolver = PlanStrategyEvolver(tmp_path)
    data = evolver.collect_plan_outcomes()

    assert data["total_runs"] == 2
    outcomes = data["outcomes"]
    assert outcomes[0]["succeeded"] is True
    assert outcomes[0]["plan_structure"] == [{"wave": 0}]
    assert outcomes[1]["succeeded"] is False
    assert outcomes[1]["deviation_count"] == 1


# ------------------------------------------------------------------
# analyze (LLM-driven)
# ------------------------------------------------------------------


def test_analyze_no_planner(tmp_path: Path) -> None:
    evolver = PlanStrategyEvolver(tmp_path, planner=None)
    assert evolver.analyze() is None


def test_analyze_no_runs(tmp_path: Path) -> None:
    planner = MagicMock()
    evolver = PlanStrategyEvolver(tmp_path, planner=planner)
    assert evolver.analyze() is None
    planner.brainstorm.assert_not_called()


def test_analyze_with_mock_planner(tmp_path: Path) -> None:
    rd = tmp_path / ".spec_orch_runs" / "RUN-1"
    _write_report(rd, {"mergeable": False, "failed_conditions": ["verification"]})

    planner = MagicMock()
    planner.brainstorm.return_value = json.dumps(
        {
            "hints": [
                {
                    "hint_id": "isolate-migrations",
                    "text": "Isolate database migrations in wave-0.",
                    "evidence": "3 out of 5 migration runs failed.",
                    "confidence": "high",
                }
            ],
            "analysis_summary": "Migrations are the primary failure source.",
        }
    )

    evolver = PlanStrategyEvolver(tmp_path, planner=planner)
    result = evolver.analyze()

    assert result is not None
    assert len(result.hints) == 1
    assert result.hints[0].hint_id == "isolate-migrations"
    assert result.hints[0].is_active is True
    assert result.analysis_summary == "Migrations are the primary failure source."

    call_args = planner.brainstorm.call_args
    messages = call_args.kwargs["conversation_history"]
    assert messages[0]["role"] == "system"
    assert "planning strategy analyst" in messages[0]["content"]


def test_analyze_non_string_response(tmp_path: Path) -> None:
    rd = tmp_path / ".spec_orch_runs" / "R1"
    _write_report(rd, {"mergeable": True, "failed_conditions": []})

    planner = MagicMock()
    planner.brainstorm.return_value = None

    evolver = PlanStrategyEvolver(tmp_path, planner=planner)
    assert evolver.analyze() is None


def test_analyze_saves_to_disk(tmp_path: Path) -> None:
    rd = tmp_path / ".spec_orch_runs" / "R1"
    _write_report(rd, {"mergeable": True, "failed_conditions": []})

    planner = MagicMock()
    planner.brainstorm.return_value = json.dumps(
        {
            "hints": [{"hint_id": "h1", "text": "A hint"}],
            "analysis_summary": "Summary",
        }
    )

    evolver = PlanStrategyEvolver(tmp_path, planner=planner)
    evolver.analyze()

    loaded = evolver.load_hints()
    assert len(loaded.hints) == 1


# ------------------------------------------------------------------
# format_hints_for_prompt
# ------------------------------------------------------------------


def test_format_hints_empty(tmp_path: Path) -> None:
    evolver = PlanStrategyEvolver(tmp_path)
    assert evolver.format_hints_for_prompt() == ""


def test_format_hints_with_active(tmp_path: Path) -> None:
    evolver = PlanStrategyEvolver(tmp_path)
    hint_set = HintSet(
        hints=[
            ScoperHint(hint_id="h1", text="Isolate migrations", confidence="high", is_active=True),
            ScoperHint(hint_id="h2", text="Inactive hint", confidence="low", is_active=False),
            ScoperHint(
                hint_id="h3", text="Test files need packets", confidence="medium", is_active=True
            ),
        ]
    )
    result = evolver.format_hints_for_prompt(hint_set)
    assert "<scoper_hints>" in result
    assert "Isolate migrations [high]" in result
    assert "Test files need packets [medium]" in result
    assert "Inactive hint" not in result


# ------------------------------------------------------------------
# merge_hints
# ------------------------------------------------------------------


def test_merge_hints_no_duplicates(tmp_path: Path) -> None:
    evolver = PlanStrategyEvolver(tmp_path)
    existing = HintSet(
        hints=[ScoperHint(hint_id="h1", text="hint 1")],
        analysis_summary="old",
        generated_at="old-time",
    )
    evolver.save_hints(existing)

    new = HintSet(
        hints=[
            ScoperHint(hint_id="h1", text="updated hint 1"),
            ScoperHint(hint_id="h2", text="hint 2"),
        ],
        analysis_summary="new summary",
        generated_at="new-time",
    )
    merged = evolver.merge_hints(new)

    assert len(merged.hints) == 2
    assert merged.hints[0].text == "hint 1"  # not overwritten
    assert merged.hints[1].hint_id == "h2"
    assert merged.analysis_summary == "new summary"


# ------------------------------------------------------------------
# CLI smoke tests
# ------------------------------------------------------------------


def test_strategy_status_cli_empty(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from spec_orch.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["strategy", "status", "--repo-root", str(tmp_path)])
    assert result.exit_code == 0
    assert "No scoper hints" in result.output


def test_strategy_status_cli_with_hints(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from spec_orch.cli import app

    evolver = PlanStrategyEvolver(tmp_path)
    evolver.save_hints(
        HintSet(
            hints=[ScoperHint(hint_id="h1", text="Test hint", confidence="high")],
            analysis_summary="Test summary.",
        )
    )

    runner = CliRunner()
    result = runner.invoke(app, ["strategy", "status", "--repo-root", str(tmp_path)])
    assert result.exit_code == 0
    assert "Test hint" in result.output
