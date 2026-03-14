"""Tests for PolicyDistiller — deterministic code policies for recurring tasks."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from spec_orch.services.policy_distiller import Policy, PolicyDistiller


def _write_report(run_dir: Path, report: dict) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "report.json").write_text(json.dumps(report))


# ------------------------------------------------------------------
# Load / save policies
# ------------------------------------------------------------------


def test_load_empty(tmp_path: Path) -> None:
    distiller = PolicyDistiller(tmp_path)
    assert distiller.load_policies() == []


def test_save_and_load(tmp_path: Path) -> None:
    distiller = PolicyDistiller(tmp_path)
    policies = [
        Policy(
            policy_id="fix-lint",
            name="Fix Lint",
            description="Auto-fix lint errors.",
            trigger_patterns=[r"\bruff\b", r"\blint\b"],
            total_executions=5,
            successful_executions=4,
        ),
    ]
    distiller.save_policies(policies)
    loaded = distiller.load_policies()
    assert len(loaded) == 1
    assert loaded[0].policy_id == "fix-lint"
    assert loaded[0].success_rate == 0.8


def test_load_malformed(tmp_path: Path) -> None:
    (tmp_path / "policies_index.json").write_text("not json")
    distiller = PolicyDistiller(tmp_path)
    assert distiller.load_policies() == []


def test_load_non_list(tmp_path: Path) -> None:
    (tmp_path / "policies_index.json").write_text('{"key": "val"}')
    distiller = PolicyDistiller(tmp_path)
    assert distiller.load_policies() == []


# ------------------------------------------------------------------
# identify_candidates
# ------------------------------------------------------------------


def test_identify_no_runs(tmp_path: Path) -> None:
    distiller = PolicyDistiller(tmp_path)
    assert distiller.identify_candidates() == []


def test_identify_with_recurring_checks(tmp_path: Path) -> None:
    for i in range(4):
        rd = tmp_path / ".spec_orch_runs" / f"RUN-{i}"
        _write_report(
            rd,
            {
                "mergeable": True,
                "failed_conditions": [],
                "verification": {
                    "ruff": {"exit_code": 0, "command": "ruff check ."},
                    "pytest": {"exit_code": 0, "command": "pytest"},
                },
            },
        )

    distiller = PolicyDistiller(tmp_path)
    candidates = distiller.identify_candidates(min_occurrences=3)
    pattern_names = [c["pattern"] for c in candidates]
    assert "fix-ruff" in pattern_names
    assert "fix-pytest" in pattern_names


# ------------------------------------------------------------------
# distill (LLM-driven)
# ------------------------------------------------------------------


def test_distill_no_planner(tmp_path: Path) -> None:
    distiller = PolicyDistiller(tmp_path, planner=None)
    assert distiller.distill("fix lint") is None


def test_distill_with_mock_planner(tmp_path: Path) -> None:
    planner = MagicMock()
    planner.brainstorm.return_value = json.dumps(
        {
            "policy_id": "auto-fix-ruff",
            "name": "Auto Fix Ruff",
            "description": "Run ruff --fix to auto-fix lint issues.",
            "trigger_patterns": [r"\bruff\b", r"\blint\b"],
            "script": "#!/usr/bin/env python3\nimport subprocess\nsubprocess.run(['ruff', 'check', '--fix', '.'])\n",
            "estimated_savings": "Saves ~2min LLM call per run",
        }
    )

    distiller = PolicyDistiller(tmp_path, planner=planner)
    policy = distiller.distill("Fix ruff lint errors")

    assert policy is not None
    assert policy.policy_id == "auto-fix-ruff"
    assert policy.name == "Auto Fix Ruff"
    assert (tmp_path / "policies" / "auto-fix-ruff.py").exists()

    loaded = distiller.load_policies()
    assert len(loaded) == 1

    call_args = planner.brainstorm.call_args
    messages = call_args.kwargs["conversation_history"]
    assert messages[0]["role"] == "system"
    assert "policy-distiller" in messages[0]["content"]


def test_distill_non_string_response(tmp_path: Path) -> None:
    planner = MagicMock()
    planner.brainstorm.return_value = 42

    distiller = PolicyDistiller(tmp_path, planner=planner)
    assert distiller.distill("some task") is None


def test_distill_auto_pick_candidate(tmp_path: Path) -> None:
    for i in range(3):
        rd = tmp_path / ".spec_orch_runs" / f"RUN-{i}"
        _write_report(
            rd,
            {
                "mergeable": True,
                "failed_conditions": [],
                "verification": {"ruff": {"exit_code": 0, "command": "ruff check ."}},
            },
        )

    planner = MagicMock()
    planner.brainstorm.return_value = json.dumps(
        {
            "policy_id": "auto-ruff",
            "name": "Auto Ruff",
            "description": "test",
            "script": "print('hello')\n",
        }
    )

    distiller = PolicyDistiller(tmp_path, planner=planner)
    policy = distiller.distill()
    assert policy is not None


# ------------------------------------------------------------------
# execute
# ------------------------------------------------------------------


def test_execute_simple_script(tmp_path: Path) -> None:
    policies_dir = tmp_path / "policies"
    policies_dir.mkdir()
    script = policies_dir / "hello.py"
    script.write_text("print('hello policy')\n")

    distiller = PolicyDistiller(tmp_path)
    policies = [
        Policy(
            policy_id="hello",
            name="Hello",
            description="test",
            script_path="policies/hello.py",
            is_active=True,
        ),
    ]
    distiller.save_policies(policies)

    result = distiller.execute("hello")
    assert result["succeeded"] is True
    assert result["exit_code"] == 0
    assert "hello policy" in result["stdout"]

    reloaded = distiller.load_policies()
    assert reloaded[0].total_executions == 1
    assert reloaded[0].successful_executions == 1


def test_execute_failing_script(tmp_path: Path) -> None:
    policies_dir = tmp_path / "policies"
    policies_dir.mkdir()
    script = policies_dir / "fail.py"
    script.write_text("import sys; sys.exit(1)\n")

    distiller = PolicyDistiller(tmp_path)
    policies = [
        Policy(policy_id="fail", name="Fail", description="test", script_path="policies/fail.py"),
    ]
    distiller.save_policies(policies)

    result = distiller.execute("fail")
    assert result["succeeded"] is False
    assert result["exit_code"] == 1


def test_execute_not_found(tmp_path: Path) -> None:
    distiller = PolicyDistiller(tmp_path)
    result = distiller.execute("nonexistent")
    assert result["succeeded"] is False
    assert "not found" in result["error"]


def test_execute_inactive(tmp_path: Path) -> None:
    distiller = PolicyDistiller(tmp_path)
    policies = [
        Policy(
            policy_id="inactive",
            name="Inactive",
            description="test",
            script_path="x.py",
            is_active=False,
        ),
    ]
    distiller.save_policies(policies)

    result = distiller.execute("inactive")
    assert result["succeeded"] is False
    assert "inactive" in result["error"]


# ------------------------------------------------------------------
# match_policy
# ------------------------------------------------------------------


def test_match_policy(tmp_path: Path) -> None:
    distiller = PolicyDistiller(tmp_path)
    policies = [
        Policy(
            policy_id="fix-lint",
            name="Fix Lint",
            description="test",
            trigger_patterns=[r"\bruff\b", r"\blint\b"],
            is_active=True,
        ),
    ]
    distiller.save_policies(policies)

    assert distiller.match_policy("Please fix ruff errors") is not None
    assert distiller.match_policy("Deploy to production") is None


def test_match_policy_inactive_skipped(tmp_path: Path) -> None:
    distiller = PolicyDistiller(tmp_path)
    policies = [
        Policy(
            policy_id="fix-lint",
            name="Fix Lint",
            description="test",
            trigger_patterns=[r"\bruff\b"],
            is_active=False,
        ),
    ]
    distiller.save_policies(policies)

    assert distiller.match_policy("fix ruff") is None


def test_match_policy_invalid_regex(tmp_path: Path) -> None:
    distiller = PolicyDistiller(tmp_path)
    policies = [
        Policy(
            policy_id="bad",
            name="Bad",
            description="test",
            trigger_patterns=["[invalid"],
            is_active=True,
        ),
    ]
    distiller.save_policies(policies)

    assert distiller.match_policy("anything") is None


# ------------------------------------------------------------------
# Policy properties
# ------------------------------------------------------------------


def test_success_rate_zero() -> None:
    p = Policy(policy_id="x", name="X", description="test")
    assert p.success_rate == 0.0


# ------------------------------------------------------------------
# CLI smoke tests
# ------------------------------------------------------------------


def test_policy_list_cli_empty(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from spec_orch.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["policy", "list", "--repo-root", str(tmp_path)])
    assert result.exit_code == 0
    assert "No policies" in result.output


def test_policy_list_cli_with_policies(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from spec_orch.cli import app

    distiller = PolicyDistiller(tmp_path)
    distiller.save_policies(
        [Policy(policy_id="p1", name="Policy One", description="test", is_active=True)]
    )

    runner = CliRunner()
    result = runner.invoke(app, ["policy", "list", "--repo-root", str(tmp_path)])
    assert result.exit_code == 0
    assert "p1" in result.output
