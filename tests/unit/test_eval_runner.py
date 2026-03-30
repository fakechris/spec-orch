"""Unit tests for EvalRunner (P6 baseline)."""

from __future__ import annotations

import json
from pathlib import Path

from spec_orch.domain.execution_semantics import (
    ContinuityKind,
    ExecutionAttempt,
    ExecutionAttemptState,
    ExecutionOutcome,
    ExecutionOwnerKind,
    ExecutionStatus,
    ExecutionUnitKind,
)
from spec_orch.services.eval_runner import EvalRunner


def _write_conclusion(run_dir: Path, data: dict) -> None:
    art = run_dir / "run_artifact"
    art.mkdir(parents=True)
    (art / "conclusion.json").write_text(json.dumps(data))


def _write_live(run_dir: Path, data: dict) -> None:
    art = run_dir / "run_artifact"
    art.mkdir(parents=True, exist_ok=True)
    (art / "live.json").write_text(json.dumps(data))


def test_eval_empty_repo(tmp_path: Path) -> None:
    runner = EvalRunner(tmp_path)
    report = runner.evaluate()
    assert report.total == 0
    assert report.pass_rate == 0.0


def test_eval_single_pass(tmp_path: Path) -> None:
    runs = tmp_path / ".spec_orch_runs"
    rd = runs / "issue-1"
    rd.mkdir(parents=True)
    _write_conclusion(
        rd,
        {
            "run_id": "r1",
            "issue_id": "issue-1",
            "verdict": "pass",
            "mergeable": True,
            "failed_conditions": [],
            "state": "merged",
        },
    )
    _write_live(
        rd,
        {
            "builder": {"adapter": "codex", "agent": "codex-exec"},
            "verification": {"lint": {"exit_code": 0}, "test": {"exit_code": 0}},
        },
    )

    runner = EvalRunner(tmp_path)
    report = runner.evaluate()
    assert report.total == 1
    assert report.passed == 1
    assert report.pass_rate == 1.0
    assert report.run_scores[0].builder_adapter == "codex"
    assert report.run_scores[0].verification_pass_rate == 1.0


def test_eval_mixed_results(tmp_path: Path) -> None:
    runs = tmp_path / ".spec_orch_runs"
    for i in range(4):
        rd = runs / f"issue-{i}"
        rd.mkdir(parents=True)
        mergeable = i % 2 == 0
        _write_conclusion(
            rd,
            {
                "run_id": f"r{i}",
                "issue_id": f"issue-{i}",
                "verdict": "pass" if mergeable else "fail",
                "mergeable": mergeable,
                "failed_conditions": [] if mergeable else ["spec_exists"],
            },
        )

    runner = EvalRunner(tmp_path)
    report = runner.evaluate()
    assert report.total == 4
    assert report.passed == 2
    assert report.failed == 2
    assert report.pass_rate == 0.5
    assert report.failure_breakdown.get("spec_exists") == 2


def test_eval_filter_tags(tmp_path: Path) -> None:
    runs = tmp_path / ".spec_orch_runs"
    for idx, adapter in enumerate(["codex", "opencode", "codex"]):
        rd = runs / f"issue-{adapter}-{idx}"
        rd.mkdir(parents=True)
        _write_conclusion(
            rd,
            {
                "run_id": f"r-{adapter}-{idx}",
                "issue_id": rd.name,
                "mergeable": True,
                "verdict": "pass",
            },
        )
        _write_live(rd, {"builder": {"adapter": adapter}})

    runner = EvalRunner(tmp_path)
    all_report = runner.evaluate()
    assert all_report.total == 3

    filtered = runner.evaluate(filter_tags={"adapter": "codex"})
    assert filtered.total == 2


def test_eval_write_report(tmp_path: Path) -> None:
    runs = tmp_path / ".spec_orch_runs"
    rd = runs / "issue-x"
    rd.mkdir(parents=True)
    _write_conclusion(
        rd,
        {
            "run_id": "rx",
            "issue_id": "issue-x",
            "mergeable": False,
            "verdict": "fail",
            "failed_conditions": ["lint"],
        },
    )

    runner = EvalRunner(tmp_path)
    report = runner.evaluate()
    out = tmp_path / "eval_output" / "report.json"
    runner.write_report(report, out)
    assert out.exists()
    data = json.loads(out.read_text())
    assert data["total"] == 1
    assert data["pass_rate"] == 0.0


def test_eval_deviations_counted(tmp_path: Path) -> None:
    runs = tmp_path / ".spec_orch_runs"
    rd = runs / "issue-dev"
    rd.mkdir(parents=True)
    _write_conclusion(
        rd,
        {
            "run_id": "rd",
            "issue_id": "issue-dev",
            "mergeable": True,
            "verdict": "pass",
        },
    )
    (rd / "deviations.jsonl").write_text('{"file_path":"a.py"}\n{"file_path":"b.py"}\n')

    runner = EvalRunner(tmp_path)
    report = runner.evaluate()
    assert report.run_scores[0].deviation_count == 2
    assert report.avg_deviation_count == 2.0


def test_eval_legacy_report_fallback(tmp_path: Path) -> None:
    runs = tmp_path / ".spec_orch_runs"
    rd = runs / "legacy"
    rd.mkdir(parents=True)
    (rd / "report.json").write_text(
        json.dumps(
            {
                "run_id": "rl",
                "issue_id": "legacy",
                "mergeable": True,
                "state": "merged",
                "builder": {"adapter": "claude"},
            }
        )
    )

    runner = EvalRunner(tmp_path)
    report = runner.evaluate()
    assert report.total == 1
    assert report.passed == 1
    assert report.run_scores[0].builder_adapter == "claude"


def test_eval_prefers_normalized_execution_attempt_reader(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / ".spec_orch_runs" / "normalized-only"
    run_dir.mkdir(parents=True)

    normalized = ExecutionAttempt(
        attempt_id="r-normalized",
        unit_kind=ExecutionUnitKind.ISSUE,
        unit_id="issue-normalized",
        owner_kind=ExecutionOwnerKind.RUN_CONTROLLER,
        continuity_kind=ContinuityKind.FILE_BACKED_RUN,
        workspace_root=str(run_dir),
        attempt_state=ExecutionAttemptState.COMPLETED,
        outcome=ExecutionOutcome(
            unit_kind=ExecutionUnitKind.ISSUE,
            owner_kind=ExecutionOwnerKind.RUN_CONTROLLER,
            status=ExecutionStatus.SUCCEEDED,
            build={"adapter": "codex"},
            verification={"test": {"exit_code": 0}},
            gate={"mergeable": True, "verdict": "pass", "failed_conditions": []},
            artifacts={},
        ),
    )

    monkeypatch.setattr(
        "spec_orch.services.eval_runner.read_issue_execution_attempt",
        lambda _: normalized,
    )

    report = EvalRunner(tmp_path).evaluate()
    assert report.total == 1
    assert report.passed == 1
    assert report.run_scores[0].builder_adapter == "codex"


def test_eval_adapter_breakdown(tmp_path: Path) -> None:
    runs = tmp_path / ".spec_orch_runs"
    for i, (adapter, ok) in enumerate([("codex", True), ("codex", False), ("opencode", True)]):
        rd = runs / f"issue-{i}"
        rd.mkdir(parents=True)
        _write_conclusion(
            rd,
            {
                "run_id": f"r{i}",
                "issue_id": f"issue-{i}",
                "mergeable": ok,
                "verdict": "pass" if ok else "fail",
            },
        )
        _write_live(rd, {"builder": {"adapter": adapter}})

    runner = EvalRunner(tmp_path)
    report = runner.evaluate()
    assert report.adapter_breakdown["codex"] == {"total": 2, "passed": 1}
    assert report.adapter_breakdown["opencode"] == {"total": 1, "passed": 1}
