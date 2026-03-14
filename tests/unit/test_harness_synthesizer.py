"""Tests for HarnessSynthesizer and RuleValidator."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import yaml
from typer.testing import CliRunner

from spec_orch.cli import app
from spec_orch.services.harness_synthesizer import (
    CandidateRule,
    HarnessSynthesizer,
    RuleValidator,
)


def _write_report(run_dir: Path, report: dict) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "report.json").write_text(json.dumps(report))


def _write_deviations(run_dir: Path, deviations: list[dict]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(d) for d in deviations]
    (run_dir / "deviations.jsonl").write_text("\n".join(lines))


def _write_builder_events(run_dir: Path, events: list[dict]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(e) for e in events]
    (run_dir / "builder_events.jsonl").write_text("\n".join(lines))


def _make_candidate(**overrides) -> CandidateRule:
    defaults = {
        "id": "test-rule",
        "name": "Test Rule",
        "description": "A test rule.",
        "severity": "warning",
        "patterns": [r"\btest\b"],
        "check_fields": ["text"],
    }
    defaults.update(overrides)
    return CandidateRule(**defaults)


# ------------------------------------------------------------------
# HarnessSynthesizer.collect_failure_data
# ------------------------------------------------------------------


def test_collect_failure_data_no_runs(tmp_path: Path) -> None:
    synth = HarnessSynthesizer(tmp_path)
    result = synth.collect_failure_data()
    assert result == {}


def test_collect_failure_data_with_runs(tmp_path: Path) -> None:
    rd1 = tmp_path / ".spec_orch_runs" / "ISSUE-1"
    _write_report(
        rd1,
        {
            "mergeable": False,
            "failed_conditions": ["verification", "review"],
            "verification": {
                "ruff": {"exit_code": 1, "command": "ruff check ."},
                "pytest": {"exit_code": 0, "command": "pytest"},
            },
        },
    )
    _write_deviations(
        rd1,
        [
            {"file_path": "src/foo.py", "severity": "major"},
        ],
    )

    rd2 = tmp_path / ".spec_orch_runs" / "ISSUE-2"
    _write_report(
        rd2,
        {
            "mergeable": True,
            "failed_conditions": [],
        },
    )

    synth = HarnessSynthesizer(tmp_path)
    data = synth.collect_failure_data()

    assert "run_ids" in data
    assert len(data["run_ids"]) == 2
    assert len(data["gate_failures"]) == 1
    assert data["gate_failures"][0]["failed_conditions"] == ["verification", "review"]
    assert len(data["verification_failures"]) == 1
    assert data["verification_failures"][0]["check"] == "ruff"
    assert len(data["deviations"]) == 1
    assert data["deviations"][0]["file_path"] == "src/foo.py"


# ------------------------------------------------------------------
# HarnessSynthesizer.synthesize
# ------------------------------------------------------------------


def test_synthesize_without_planner(tmp_path: Path) -> None:
    synth = HarnessSynthesizer(tmp_path, planner=None)
    result = synth.synthesize()
    assert result == []


def test_synthesize_with_mock_planner(tmp_path: Path) -> None:
    rd = tmp_path / ".spec_orch_runs" / "RUN-1"
    _write_report(
        rd,
        {
            "mergeable": False,
            "failed_conditions": ["verification"],
            "verification": {"pytest": {"exit_code": 1, "command": "pytest"}},
        },
    )

    (tmp_path / "compliance.contracts.yaml").write_text(
        yaml.dump({"contracts": [{"id": "existing", "name": "Existing", "patterns": []}]})
    )

    llm_response = json.dumps(
        [
            {
                "id": "no-print-statements",
                "name": "No Print Statements",
                "description": "Avoid print() in production code.",
                "severity": "warning",
                "patterns": [r"\bprint\s*\("],
                "check_fields": ["text"],
            }
        ]
    )

    planner = MagicMock()
    planner.brainstorm.return_value = llm_response

    synth = HarnessSynthesizer(tmp_path, planner=planner)
    candidates = synth.synthesize()

    assert len(candidates) == 1
    assert candidates[0].id == "no-print-statements"
    assert candidates[0].name == "No Print Statements"
    assert candidates[0].severity == "warning"
    assert candidates[0].source == "harness-synthesizer"
    assert candidates[0].generated_at != ""
    assert "RUN-1" in candidates[0].source_runs

    planner.brainstorm.assert_called_once()
    call_kwargs = planner.brainstorm.call_args
    assert "conversation_history" in call_kwargs.kwargs


# ------------------------------------------------------------------
# HarnessSynthesizer.format_candidates_yaml
# ------------------------------------------------------------------


def test_format_candidates_yaml(tmp_path: Path) -> None:
    synth = HarnessSynthesizer(tmp_path)
    candidates = [
        _make_candidate(id="rule-a", name="Rule A", severity="error"),
        _make_candidate(id="rule-b", name="Rule B", severity="warning"),
    ]
    yaml_str = synth.format_candidates_yaml(candidates)
    parsed = yaml.safe_load(yaml_str)

    assert "contracts" in parsed
    assert len(parsed["contracts"]) == 2
    assert parsed["contracts"][0]["id"] == "rule-a"
    assert parsed["contracts"][0]["severity"] == "error"
    assert parsed["contracts"][1]["id"] == "rule-b"


# ------------------------------------------------------------------
# RuleValidator.validate
# ------------------------------------------------------------------


def test_validate_accepts_valid_regex(tmp_path: Path) -> None:
    validator = RuleValidator(tmp_path)
    candidates = [_make_candidate(patterns=[r"\bsudo\s+"])]
    accepted, rejected = validator.validate(candidates)
    assert len(accepted) == 1
    assert len(rejected) == 0


def test_validate_rejects_invalid_regex(tmp_path: Path) -> None:
    validator = RuleValidator(tmp_path)
    candidates = [_make_candidate(patterns=["[invalid"])]
    accepted, rejected = validator.validate(candidates)
    assert len(accepted) == 0
    assert len(rejected) == 1


def test_validate_rejects_empty_patterns(tmp_path: Path) -> None:
    validator = RuleValidator(tmp_path)
    candidates = [_make_candidate(patterns=[])]
    accepted, rejected = validator.validate(candidates)
    assert len(accepted) == 0
    assert len(rejected) == 1


def test_validate_rejects_overly_broad_patterns(tmp_path: Path) -> None:
    rd = tmp_path / ".spec_orch_runs" / "V1"
    _write_report(rd, {"mergeable": True, "failed_conditions": []})
    _write_builder_events(rd, [{"text": f"event line {i}"} for i in range(10)])

    validator = RuleValidator(tmp_path)
    candidates = [_make_candidate(patterns=[r"event"])]
    accepted, rejected = validator.validate(candidates, max_false_positive_rate=0.1)
    assert len(accepted) == 0
    assert len(rejected) == 1


# ------------------------------------------------------------------
# RuleValidator.apply
# ------------------------------------------------------------------


def test_apply_merges_rules(tmp_path: Path) -> None:
    contracts_path = tmp_path / "compliance.contracts.yaml"
    contracts_path.write_text(
        yaml.dump(
            {
                "contracts": [
                    {"id": "existing-rule", "name": "Existing Rule", "severity": "warning"},
                ]
            }
        )
    )

    validator = RuleValidator(tmp_path)
    accepted = [_make_candidate(id="new-rule", name="New Rule")]
    summary = validator.apply(accepted, contracts_path)

    assert "Adding 1 rule(s)" in summary
    assert "new-rule" in summary

    reloaded = yaml.safe_load(contracts_path.read_text())
    assert len(reloaded["contracts"]) == 2
    ids = [c["id"] for c in reloaded["contracts"]]
    assert "existing-rule" in ids
    assert "new-rule" in ids


def test_apply_dry_run_no_modification(tmp_path: Path) -> None:
    contracts_path = tmp_path / "compliance.contracts.yaml"
    original_content = yaml.dump(
        {
            "contracts": [
                {"id": "existing-rule", "name": "Existing Rule", "severity": "warning"},
            ]
        }
    )
    contracts_path.write_text(original_content)

    validator = RuleValidator(tmp_path)
    accepted = [_make_candidate(id="new-rule", name="New Rule")]
    summary = validator.apply(accepted, contracts_path, dry_run=True)

    assert "[dry-run]" in summary
    assert "Adding 1 rule(s)" in summary

    reloaded = yaml.safe_load(contracts_path.read_text())
    assert len(reloaded["contracts"]) == 1


def test_apply_skips_duplicate_ids(tmp_path: Path) -> None:
    contracts_path = tmp_path / "compliance.contracts.yaml"
    contracts_path.write_text(
        yaml.dump(
            {
                "contracts": [
                    {"id": "test-rule", "name": "Test Rule", "severity": "warning"},
                ]
            }
        )
    )

    validator = RuleValidator(tmp_path)
    accepted = [_make_candidate(id="test-rule", name="Test Rule")]
    summary = validator.apply(accepted, contracts_path)

    assert "already exist" in summary


def test_validate_rejects_non_string_pattern(tmp_path: Path) -> None:
    validator = RuleValidator(tmp_path)
    candidates = [_make_candidate(patterns=[123, None])]
    accepted, rejected = validator.validate(candidates)
    assert len(accepted) == 0
    assert len(rejected) == 1


def test_parse_response_non_string(tmp_path: Path) -> None:
    synth = HarnessSynthesizer(tmp_path)
    result = synth._parse_response(None, [])
    assert result == []


def test_to_contract_dict_preserves_provenance() -> None:
    c = _make_candidate(
        id="prov-test",
        name="Prov Test",
        generated_at="2026-03-10T00:00:00Z",
        source_runs=["RUN-1", "RUN-2"],
    )
    d = c.to_contract_dict()
    assert d["source"] == "harness-synthesizer"
    assert d["generated_at"] == "2026-03-10T00:00:00Z"
    assert d["source_runs"] == ["RUN-1", "RUN-2"]


def test_synthesize_sends_system_prompt(tmp_path: Path) -> None:
    rd = tmp_path / ".spec_orch_runs" / "SP-1"
    _write_report(rd, {"mergeable": False, "failed_conditions": ["verification"]})
    (tmp_path / "compliance.contracts.yaml").write_text(yaml.dump({"contracts": []}))

    planner = MagicMock()
    planner.brainstorm.return_value = "[]"

    synth = HarnessSynthesizer(tmp_path, planner=planner)
    synth.synthesize()

    call_args = planner.brainstorm.call_args
    history = call_args.kwargs["conversation_history"]
    assert history[0]["role"] == "system"
    assert "compliance-rule engineer" in history[0]["content"]
    assert history[1]["role"] == "user"


# ------------------------------------------------------------------
# CLI smoke tests
# ------------------------------------------------------------------


def test_harness_synthesize_cli_no_planner(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["harness", "synthesize", "--repo-root", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert "No candidate rules generated" in result.output


def test_harness_validate_cli(tmp_path: Path) -> None:
    candidates_file = tmp_path / "candidates.yaml"
    candidates_file.write_text(
        yaml.dump(
            {
                "contracts": [
                    {
                        "id": "cli-test-rule",
                        "name": "CLI Test Rule",
                        "severity": "warning",
                        "patterns": [r"\bcli_test\b"],
                        "check_fields": ["text"],
                    }
                ]
            }
        )
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["harness", "validate", "--input", str(candidates_file), "--repo-root", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert "Accepted" in result.output
    assert "cli-test-rule" in result.output


def test_harness_apply_cli_dry_run(tmp_path: Path) -> None:
    contracts_path = tmp_path / "compliance.contracts.yaml"
    contracts_path.write_text(yaml.dump({"contracts": []}))

    candidates_file = tmp_path / "candidates.yaml"
    candidates_file.write_text(
        yaml.dump(
            {
                "contracts": [
                    {
                        "id": "apply-test",
                        "name": "Apply Test",
                        "severity": "warning",
                        "patterns": [r"\bapply\b"],
                        "check_fields": ["text"],
                    }
                ]
            }
        )
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "harness",
            "apply",
            "--input",
            str(candidates_file),
            "--contracts",
            str(contracts_path),
            "--dry-run",
            "--repo-root",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0
    assert "[dry-run]" in result.output

    reloaded = yaml.safe_load(contracts_path.read_text())
    assert len(reloaded["contracts"]) == 0
