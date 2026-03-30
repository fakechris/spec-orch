"""Tests for EvidenceAnalyzer and PatternSummary."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from spec_orch.domain.execution_semantics import (
    ContinuityKind,
    ExecutionAttempt,
    ExecutionAttemptState,
    ExecutionOutcome,
    ExecutionOwnerKind,
    ExecutionStatus,
    ExecutionUnitKind,
)
from spec_orch.cli import app
from spec_orch.services.evidence_analyzer import EvidenceAnalyzer, PatternSummary


def _write_report(run_dir: Path, report: dict) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "report.json").write_text(json.dumps(report))


def _write_deviations(run_dir: Path, deviations: list[dict]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(d) for d in deviations]
    (run_dir / "deviations.jsonl").write_text("\n".join(lines))


# ------------------------------------------------------------------
# Empty / missing directories
# ------------------------------------------------------------------


def test_no_run_dirs_returns_empty_summary(tmp_path: Path) -> None:
    analyzer = EvidenceAnalyzer(tmp_path)
    summary = analyzer.analyze()
    assert summary == PatternSummary()
    assert summary.total_runs == 0
    assert summary.success_rate == 0.0


def test_empty_run_dirs(tmp_path: Path) -> None:
    (tmp_path / ".spec_orch_runs").mkdir()
    analyzer = EvidenceAnalyzer(tmp_path)
    summary = analyzer.analyze()
    assert summary.total_runs == 0


# ------------------------------------------------------------------
# Basic aggregation
# ------------------------------------------------------------------


def test_single_successful_run(tmp_path: Path) -> None:
    _write_report(
        tmp_path / ".spec_orch_runs" / "ISSUE-1",
        {
            "state": "gate_evaluated",
            "issue_id": "ISSUE-1",
            "mergeable": True,
            "failed_conditions": [],
            "verification": {
                "ruff": {"exit_code": 0, "command": "ruff check ."},
                "pytest": {"exit_code": 0, "command": "pytest"},
            },
        },
    )
    summary = EvidenceAnalyzer(tmp_path).analyze()
    assert summary.total_runs == 1
    assert summary.successful_runs == 1
    assert summary.failed_runs == 0
    assert summary.success_rate == 1.0
    assert summary.average_verification_pass_rate == 1.0


def test_mixed_runs(tmp_path: Path) -> None:
    _write_report(
        tmp_path / ".spec_orch_runs" / "A",
        {"mergeable": True, "failed_conditions": []},
    )
    _write_report(
        tmp_path / ".spec_orch_runs" / "B",
        {"mergeable": False, "failed_conditions": ["verification", "review"]},
    )
    _write_report(
        tmp_path / ".spec_orch_runs" / "C",
        {"mergeable": False, "failed_conditions": ["verification"]},
    )

    summary = EvidenceAnalyzer(tmp_path).analyze()
    assert summary.total_runs == 3
    assert summary.successful_runs == 1
    assert summary.failed_runs == 2
    assert abs(summary.success_rate - 1 / 3) < 0.01
    assert summary.top_failure_reasons[0] == ("verification", 2)
    assert ("review", 1) in summary.top_failure_reasons


def test_worktrees_dir_also_scanned(tmp_path: Path) -> None:
    _write_report(
        tmp_path / ".worktrees" / "WT-1",
        {"mergeable": True, "failed_conditions": []},
    )
    summary = EvidenceAnalyzer(tmp_path).analyze()
    assert summary.total_runs == 1
    assert summary.successful_runs == 1


def test_unified_artifacts_scanned_without_legacy_report(tmp_path: Path) -> None:
    rd = tmp_path / ".spec_orch_runs" / "U1"
    (rd / "run_artifact").mkdir(parents=True)
    (rd / "run_artifact" / "conclusion.json").write_text(
        json.dumps(
            {
                "issue_id": "U1",
                "run_id": "run-u1",
                "state": "gate_evaluated",
                "mergeable": False,
                "failed_conditions": ["verification"],
            }
        )
    )
    (rd / "run_artifact" / "live.json").write_text(
        json.dumps({"verification": {"pytest": {"exit_code": 1, "command": "pytest"}}})
    )

    summary = EvidenceAnalyzer(tmp_path).analyze()
    assert summary.total_runs == 1
    assert summary.successful_runs == 0
    assert summary.top_failure_reasons[0] == ("verification", 1)
    assert summary.average_verification_pass_rate == 0.0


def test_analyzer_prefers_normalized_execution_attempt_reader(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / ".spec_orch_runs" / "normalized-only"
    run_dir.mkdir(parents=True)

    normalized = ExecutionAttempt(
        attempt_id="run-normalized",
        unit_kind=ExecutionUnitKind.ISSUE,
        unit_id="ISSUE-N",
        owner_kind=ExecutionOwnerKind.RUN_CONTROLLER,
        continuity_kind=ContinuityKind.FILE_BACKED_RUN,
        workspace_root=str(run_dir),
        attempt_state=ExecutionAttemptState.COMPLETED,
        outcome=ExecutionOutcome(
            unit_kind=ExecutionUnitKind.ISSUE,
            owner_kind=ExecutionOwnerKind.RUN_CONTROLLER,
            status=ExecutionStatus.FAILED,
            build={"adapter": "codex"},
            verification={"pytest": {"exit_code": 1, "command": "pytest"}},
            gate={"mergeable": False, "failed_conditions": ["verification"]},
            artifacts={},
        ),
    )

    monkeypatch.setattr(
        "spec_orch.services.evidence_analyzer.read_issue_execution_attempt",
        lambda _: normalized,
    )

    summary = EvidenceAnalyzer(tmp_path).analyze()
    assert summary.total_runs == 1
    assert summary.failed_runs == 1
    assert summary.top_failure_reasons[0] == ("verification", 1)


def test_both_dirs_combined(tmp_path: Path) -> None:
    _write_report(
        tmp_path / ".spec_orch_runs" / "R1",
        {"mergeable": True, "failed_conditions": []},
    )
    _write_report(
        tmp_path / ".worktrees" / "W1",
        {"mergeable": False, "failed_conditions": ["review"]},
    )
    summary = EvidenceAnalyzer(tmp_path).analyze()
    assert summary.total_runs == 2
    assert summary.successful_runs == 1
    assert summary.failed_runs == 1


# ------------------------------------------------------------------
# Deviations
# ------------------------------------------------------------------


def test_deviations_aggregation(tmp_path: Path) -> None:
    rd = tmp_path / ".spec_orch_runs" / "D1"
    _write_report(rd, {"mergeable": False, "failed_conditions": []})
    _write_deviations(
        rd,
        [
            {"file_path": "tests/foo.py", "severity": "minor"},
            {"file_path": "tests/foo.py", "severity": "major"},
            {"file_path": "src/bar.py", "severity": "minor"},
        ],
    )

    rd2 = tmp_path / ".spec_orch_runs" / "D2"
    _write_report(rd2, {"mergeable": True, "failed_conditions": []})
    _write_deviations(
        rd2,
        [{"file_path": "tests/foo.py", "severity": "minor"}],
    )

    summary = EvidenceAnalyzer(tmp_path).analyze()
    assert summary.total_deviations == 4
    assert summary.top_deviation_files[0] == ("tests/foo.py", 3)
    assert ("src/bar.py", 1) in summary.top_deviation_files


# ------------------------------------------------------------------
# Retrospectives
# ------------------------------------------------------------------


def test_retrospective_counting(tmp_path: Path) -> None:
    rd1 = tmp_path / ".spec_orch_runs" / "R1"
    _write_report(rd1, {"mergeable": True, "failed_conditions": []})
    (rd1 / "retrospective.md").write_text("# Retro\nAll good.")

    rd2 = tmp_path / ".spec_orch_runs" / "R2"
    _write_report(rd2, {"mergeable": True, "failed_conditions": []})

    summary = EvidenceAnalyzer(tmp_path).analyze()
    assert summary.has_retrospectives == 1


# ------------------------------------------------------------------
# Verification pass rate
# ------------------------------------------------------------------


def test_verification_pass_rate(tmp_path: Path) -> None:
    _write_report(
        tmp_path / ".spec_orch_runs" / "V1",
        {
            "mergeable": False,
            "failed_conditions": ["verification"],
            "verification": {
                "ruff": {"exit_code": 0, "command": "ruff check ."},
                "pytest": {"exit_code": 1, "command": "pytest"},
            },
        },
    )
    _write_report(
        tmp_path / ".spec_orch_runs" / "V2",
        {
            "mergeable": True,
            "failed_conditions": [],
            "verification": {
                "ruff": {"exit_code": 0, "command": "ruff check ."},
                "pytest": {"exit_code": 0, "command": "pytest"},
            },
        },
    )

    summary = EvidenceAnalyzer(tmp_path).analyze()
    # V1: 1/2 = 0.5, V2: 2/2 = 1.0, avg = 0.75
    assert abs(summary.average_verification_pass_rate - 0.75) < 0.01


def test_no_verification_data(tmp_path: Path) -> None:
    _write_report(
        tmp_path / ".spec_orch_runs" / "NV",
        {"mergeable": True, "failed_conditions": []},
    )
    summary = EvidenceAnalyzer(tmp_path).analyze()
    assert summary.average_verification_pass_rate == 0.0


# ------------------------------------------------------------------
# Malformed data handling
# ------------------------------------------------------------------


def test_malformed_report_skipped(tmp_path: Path) -> None:
    rd = tmp_path / ".spec_orch_runs" / "BAD"
    rd.mkdir(parents=True)
    (rd / "report.json").write_text("NOT VALID JSON {{{")

    rd2 = tmp_path / ".spec_orch_runs" / "GOOD"
    _write_report(rd2, {"mergeable": True, "failed_conditions": []})

    summary = EvidenceAnalyzer(tmp_path).analyze()
    assert summary.total_runs == 1
    assert summary.successful_runs == 1


def test_malformed_deviation_line_skipped(tmp_path: Path) -> None:
    rd = tmp_path / ".spec_orch_runs" / "MIXED"
    _write_report(rd, {"mergeable": True, "failed_conditions": []})
    (rd / "deviations.jsonl").write_text('{"file_path": "a.py"}\nBAD LINE\n{"file_path": "b.py"}\n')

    summary = EvidenceAnalyzer(tmp_path).analyze()
    assert summary.total_deviations == 2
    assert len(summary.top_deviation_files) == 2


def test_run_dir_without_report(tmp_path: Path) -> None:
    rd = tmp_path / ".spec_orch_runs" / "EMPTY"
    rd.mkdir(parents=True)
    summary = EvidenceAnalyzer(tmp_path).analyze()
    assert summary.total_runs == 0


# ------------------------------------------------------------------
# format_summary
# ------------------------------------------------------------------


def test_format_summary_readable(tmp_path: Path) -> None:
    _write_report(
        tmp_path / ".spec_orch_runs" / "FS1",
        {
            "mergeable": False,
            "failed_conditions": ["verification"],
            "verification": {"ruff": {"exit_code": 1, "command": "ruff check ."}},
        },
    )
    rd = tmp_path / ".spec_orch_runs" / "FS1"
    _write_deviations(rd, [{"file_path": "x.py"}])

    analyzer = EvidenceAnalyzer(tmp_path)
    summary = analyzer.analyze()
    text = analyzer.format_summary(summary)

    assert "Evidence Summary" in text
    assert "Total runs:" in text
    assert "Success rate:" in text
    assert "verification" in text
    assert "x.py" in text


def test_format_summary_empty() -> None:
    analyzer = EvidenceAnalyzer(Path("/nonexistent"))
    text = analyzer.format_summary(PatternSummary())
    assert "Total runs:        0" in text


# ------------------------------------------------------------------
# format_as_llm_context
# ------------------------------------------------------------------


def test_format_as_llm_context_no_data() -> None:
    analyzer = EvidenceAnalyzer(Path("/nonexistent"))
    ctx = analyzer.format_as_llm_context(PatternSummary())
    assert "<evidence>" in ctx
    assert "No historical run data" in ctx
    assert "</evidence>" in ctx


def test_format_as_llm_context_with_data(tmp_path: Path) -> None:
    _write_report(
        tmp_path / ".spec_orch_runs" / "LC1",
        {
            "mergeable": False,
            "failed_conditions": ["verification"],
            "verification": {
                "ruff": {"exit_code": 0, "command": "ruff"},
                "pytest": {"exit_code": 1, "command": "pytest"},
            },
        },
    )
    rd = tmp_path / ".spec_orch_runs" / "LC1"
    _write_deviations(rd, [{"file_path": "z.py"}])

    analyzer = EvidenceAnalyzer(tmp_path)
    summary = analyzer.analyze()
    ctx = analyzer.format_as_llm_context(summary)

    assert "<evidence>" in ctx
    assert "</evidence>" in ctx
    assert "1 runs" in ctx
    assert "verification" in ctx
    assert "z.py" in ctx


# ------------------------------------------------------------------
# CLI integration
# ------------------------------------------------------------------


def test_evidence_summary_cli(tmp_path: Path) -> None:
    _write_report(
        tmp_path / ".spec_orch_runs" / "CLI1",
        {"mergeable": True, "failed_conditions": []},
    )
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["evidence", "summary", "--repo-root", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert "Evidence Summary" in result.output
    assert "Total runs:        1" in result.output


def test_evidence_summary_cli_empty(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["evidence", "summary", "--repo-root", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert "Total runs:        0" in result.output
