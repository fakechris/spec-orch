"""Tests for Epic C: Eval suite type, infra checks, outcome grading."""

from __future__ import annotations

import json
from pathlib import Path

from spec_orch.services.eval_runner import (
    EvalRunner,
    EvalSuiteType,
    OutcomeCheck,
    RunScore,
    Verdict,
)


def test_eval_suite_type_enum() -> None:
    assert EvalSuiteType.CAPABILITY == "capability"
    assert EvalSuiteType.REGRESSION == "regression"


def test_outcome_check_in_run_score() -> None:
    score = RunScore(
        run_id="r1",
        issue_id="i1",
        verdict=Verdict.PASS,
        mergeable=True,
        failed_conditions=[],
        verification_pass_rate=1.0,
        deviation_count=0,
        builder_adapter="test",
        has_retro=False,
        outcome_checks=[
            OutcomeCheck("check1", True),
            OutcomeCheck("check2", False, "detail"),
        ],
    )
    assert len(score.outcome_checks) == 2
    assert score.outcome_checks[0].passed
    assert not score.outcome_checks[1].passed


def test_infra_health_check(tmp_path: Path) -> None:
    runner = EvalRunner(tmp_path)
    checks = runner.check_infra()
    assert len(checks) >= 2
    config_check = next(c for c in checks if c.name == "config")
    assert config_check.status == "fail"

    (tmp_path / "spec-orch.toml").write_text("[general]\n")
    checks2 = runner.check_infra()
    config_check2 = next(c for c in checks2 if c.name == "config")
    assert config_check2.status == "pass"


def test_evaluate_with_suite_type(tmp_path: Path) -> None:
    runner = EvalRunner(tmp_path)
    report = runner.evaluate(suite_type=EvalSuiteType.REGRESSION)
    assert report.suite_type == EvalSuiteType.REGRESSION
    assert report.infra_checks is not None


def test_outcome_checks_in_score_run(tmp_path: Path) -> None:
    run_dir = tmp_path / ".spec_orch_runs" / "test-run"
    artifact_dir = run_dir / "run_artifact"
    artifact_dir.mkdir(parents=True)

    conclusion = {
        "run_id": "test-run",
        "issue_id": "TEST-1",
        "verdict": "pass",
        "mergeable": True,
        "failed_conditions": [],
    }
    (artifact_dir / "conclusion.json").write_text(json.dumps(conclusion))

    runner = EvalRunner(tmp_path)
    report = runner.evaluate()
    assert report.total == 1
    assert report.run_scores[0].outcome_checks is not None
    conclusion_check = next(
        c for c in report.run_scores[0].outcome_checks if c.name == "conclusion_exists"
    )
    assert conclusion_check.passed
