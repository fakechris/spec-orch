"""Tests for configurable compliance engine."""
from __future__ import annotations

from pathlib import Path

from spec_orch.domain.models import BuilderEvent
from spec_orch.services.compliance_engine import (
    ComplianceContract,
    ComplianceReport,
    ConfigurableComplianceEngine,
    load_contracts,
)


def _evt(kind: str, text: str) -> BuilderEvent:
    return BuilderEvent(timestamp="2026-01-01T00:00:00Z", kind=kind, text=text)


def test_load_contracts_from_yaml(tmp_path: Path) -> None:
    yaml_content = """\
contracts:
  - id: test-rule
    name: Test Rule
    severity: error
    patterns:
      - "bad_pattern"
    check_fields:
      - text
"""
    yaml_path = tmp_path / "contracts.yaml"
    yaml_path.write_text(yaml_content)
    contracts = load_contracts(yaml_path)
    assert len(contracts) == 1
    assert contracts[0].id == "test-rule"
    assert contracts[0].severity == "error"
    assert contracts[0].patterns == ["bad_pattern"]


def test_load_contracts_missing_file(tmp_path: Path) -> None:
    assert load_contracts(tmp_path / "nope.yaml") == []


def test_pattern_contract_detects_violation() -> None:
    contract = ComplianceContract(
        id="no-force-push",
        name="No Force Push",
        severity="error",
        patterns=[r"git\s+push\s+--force"],
        check_fields=["text"],
    )
    engine = ConfigurableComplianceEngine(contracts=[contract])
    events = [_evt("command_start", "git push --force origin main")]
    report = engine.evaluate(events)
    assert not report.compliant
    assert report.error_count == 1
    assert len(report.results[0].violations) == 1


def test_pattern_contract_passes_clean_events() -> None:
    contract = ComplianceContract(
        id="no-force-push",
        name="No Force Push",
        severity="error",
        patterns=[r"git\s+push\s+--force"],
        check_fields=["text"],
    )
    engine = ConfigurableComplianceEngine(contracts=[contract])
    events = [_evt("command_start", "git push origin main")]
    report = engine.evaluate(events)
    assert report.compliant
    assert report.error_count == 0


def test_builtin_pre_action_narration() -> None:
    contract = ComplianceContract(
        id="pre-action-narration",
        name="Pre-Action Narration",
        severity="warning",
        builtin=True,
    )
    engine = ConfigurableComplianceEngine(contracts=[contract])
    events = [
        _evt("message", "I will now plan my approach for this task"),
        _evt("command_start", "ls -la"),
    ]
    report = engine.evaluate(events)
    assert report.compliant  # warning-only, still compliant
    assert report.warning_count == 1


def test_report_serialization(tmp_path: Path) -> None:
    contract = ComplianceContract(
        id="test",
        name="Test",
        severity="error",
        patterns=["danger"],
        check_fields=["text"],
    )
    engine = ConfigurableComplianceEngine(contracts=[contract])
    events = [_evt("message", "danger zone")]
    report = engine.evaluate(events)

    out = tmp_path / "compliance_report.json"
    report.save(out)
    assert out.exists()

    loaded = ComplianceReport.load(out)
    assert loaded.error_count == 1
    assert not loaded.compliant


def test_report_compliant_with_warnings_only() -> None:
    contract = ComplianceContract(
        id="warn-test",
        name="Warning Test",
        severity="warning",
        patterns=["minor_issue"],
        check_fields=["text"],
    )
    engine = ConfigurableComplianceEngine(contracts=[contract])
    events = [_evt("message", "found minor_issue here")]
    report = engine.evaluate(events)
    assert report.compliant
    assert report.warning_count == 1


def test_multiple_contracts() -> None:
    contracts = [
        ComplianceContract(
            id="c1", name="C1", severity="error",
            patterns=["error_pattern"], check_fields=["text"],
        ),
        ComplianceContract(
            id="c2", name="C2", severity="warning",
            patterns=["warn_pattern"], check_fields=["text"],
        ),
    ]
    engine = ConfigurableComplianceEngine(contracts=contracts)
    events = [_evt("message", "has warn_pattern only")]
    report = engine.evaluate(events)
    assert report.compliant
    assert report.warning_count == 1
    assert report.error_count == 0


def test_from_yaml_integration(tmp_path: Path) -> None:
    yaml_path = tmp_path / "compliance.contracts.yaml"
    yaml_path.write_text(
        "contracts:\n"
        "  - id: no-secrets\n"
        "    name: No Secrets\n"
        "    severity: error\n"
        "    patterns:\n"
        "      - 'api_key\\s*=\\s*[A-Za-z0-9]{20,}'\n"
        "    check_fields:\n"
        "      - text\n"
    )
    engine = ConfigurableComplianceEngine.from_yaml(yaml_path)
    events = [_evt("message", "api_key = abcdefghijklmnopqrstuvwxyz")]
    report = engine.evaluate(events)
    assert not report.compliant
    assert report.error_count == 1


def test_gate_policy_compliance_condition() -> None:
    from spec_orch.services.gate_service import ALL_KNOWN_CONDITIONS

    assert "compliance" in ALL_KNOWN_CONDITIONS


def test_gate_evaluates_compliance_condition() -> None:
    from spec_orch.domain.models import GateInput
    from spec_orch.services.gate_service import GatePolicy, GateService

    policy = GatePolicy(required_conditions={"compliance"})
    svc = GateService(policy=policy)

    passing = GateInput(compliance_passed=True)
    assert svc.evaluate(passing).mergeable

    failing = GateInput(compliance_passed=False)
    verdict = svc.evaluate(failing)
    assert not verdict.mergeable
    assert "compliance" in verdict.failed_conditions


def test_unknown_builtin_fails() -> None:
    contract = ComplianceContract(
        id="nonexistent-builtin",
        name="Unknown",
        severity="error",
        builtin=True,
    )
    engine = ConfigurableComplianceEngine(contracts=[contract])
    report = engine.evaluate([])
    assert not report.compliant
    assert report.error_count == 1
