"""Tests for task contract generation, validation, and risk assessment."""

from __future__ import annotations

import pytest
import yaml

from spec_orch.contract_core.contracts import (
    TaskContract,
    assess_risk_level,
    generate_contract_from_issue,
)
from spec_orch.domain.models import Issue, IssueContext

# ── SON-149: Contract schema + validation ────────────────────────────


def test_contract_to_dict_and_back() -> None:
    """SON-149: Contract round-trips through dict serialization."""
    c = TaskContract(
        contract_id="c-1",
        issue_id="SPC-1",
        intent="Build the thing",
        risk_level="high",
        allowed_paths=["src/main.py"],
        completion_criteria=["Tests pass"],
        boundaries=["No changes to auth module"],
    )
    d = c.to_dict()
    c2 = TaskContract.from_dict(d)
    assert c2.contract_id == "c-1"
    assert c2.risk_level == "high"
    assert c2.allowed_paths == ["src/main.py"]
    assert c2.boundaries == ["No changes to auth module"]


def test_contract_validate_valid() -> None:
    """SON-149: Valid contract has no errors."""
    c = TaskContract(
        contract_id="c-1",
        issue_id="SPC-1",
        intent="Do stuff",
        risk_level="low",
        completion_criteria=["Works"],
    )
    assert c.validate() == []


def test_contract_validate_missing_fields() -> None:
    """SON-149: Missing required fields produce errors."""
    c = TaskContract(contract_id="", issue_id="", intent="", risk_level="invalid")
    errors = c.validate()
    assert len(errors) >= 4
    assert any("contract_id" in e for e in errors)
    assert any("issue_id" in e for e in errors)
    assert any("intent" in e for e in errors)
    assert any("risk_level" in e for e in errors)
    assert any("completion" in e.lower() for e in errors)


def test_contract_yaml_serialization() -> None:
    """SON-149: Contract can be serialized to YAML."""
    c = TaskContract(
        contract_id="c-yaml",
        issue_id="SPC-Y",
        intent="YAML test",
        completion_criteria=["Passes"],
    )
    text = yaml.dump(c.to_dict(), default_flow_style=False)
    loaded = yaml.safe_load(text)
    c2 = TaskContract.from_dict(loaded)
    assert c2.contract_id == "c-yaml"


# ── SON-150: generate-task-contract from issue ───────────────────────


def test_generate_contract_from_issue() -> None:
    """SON-150: generate_contract_from_issue produces a valid contract."""
    issue = Issue(
        issue_id="SPC-10",
        title="Add user dashboard",
        summary="Build a dashboard component",
        builder_prompt="Implement the user dashboard",
        context=IssueContext(
            files_to_read=["src/dashboard.py", "src/views.py"],
            constraints=["Must use existing UI framework"],
        ),
        acceptance_criteria=["Dashboard renders correctly", "Tests pass"],
        verification_commands={"test": ["pytest", "tests/"]},
    )
    contract = generate_contract_from_issue(issue)

    assert contract.issue_id == "SPC-10"
    assert contract.intent == "Implement the user dashboard"
    assert "src/dashboard.py" in contract.allowed_paths
    assert "Dashboard renders correctly" in contract.completion_criteria
    assert "Must use existing UI framework" in contract.boundaries
    assert contract.verification_commands.get("test") == ["pytest", "tests/"]
    assert contract.validate() == []


def test_generate_contract_no_acceptance_criteria() -> None:
    """SON-150: Default criteria when issue has none."""
    issue = Issue(
        issue_id="SPC-11",
        title="Fix typo",
        summary="Fix a small typo in readme",
        context=IssueContext(),
    )
    contract = generate_contract_from_issue(issue)
    assert len(contract.completion_criteria) >= 1


def test_generate_contract_custom_id() -> None:
    """SON-150: Custom contract_id is used."""
    issue = Issue(
        issue_id="SPC-12",
        title="task",
        summary="s",
        context=IssueContext(),
    )
    contract = generate_contract_from_issue(issue, contract_id="my-contract")
    assert contract.contract_id == "my-contract"


def test_generate_contract_rejects_non_issue() -> None:
    """SON-150: TypeError if input is not an Issue."""
    with pytest.raises(TypeError):
        generate_contract_from_issue({"issue_id": "x"})


# ── SON-151: Automatic risk assessment ───────────────────────────────


def test_risk_low_for_docs() -> None:
    """SON-151: Doc-only changes are low risk."""
    assert (
        assess_risk_level(
            title="Update README",
            summary="Fix typo in docs",
            files_in_scope=["README.md"],
        )
        == "low"
    )


def test_risk_high_for_auth() -> None:
    """SON-151: Auth-related changes are high risk."""
    assert (
        assess_risk_level(
            title="Add authentication middleware",
            summary="Implement JWT auth",
            files_in_scope=["src/auth.py"],
        )
        == "critical"
    )


def test_risk_critical_for_multiple_infra_files() -> None:
    """SON-151: Multiple infrastructure files → critical."""
    assert (
        assess_risk_level(
            title="Update deployment",
            summary="Change configs",
            files_in_scope=["deploy/k8s.yaml", "deploy/terraform.tf", "src/app.py"],
        )
        == "critical"
    )


def test_risk_medium_default() -> None:
    """SON-151: Default is medium for generic tasks."""
    assert (
        assess_risk_level(
            title="Add widget component",
            summary="Build a new widget",
            files_in_scope=["src/widget.py", "src/utils.py"],
        )
        == "medium"
    )


def test_risk_high_for_many_files() -> None:
    """SON-151: Many files → high risk."""
    files = [f"src/file_{i}.py" for i in range(12)]
    assert (
        assess_risk_level(
            title="Refactor everything",
            summary="Big refactor",
            files_in_scope=files,
        )
        == "high"
    )


def test_risk_low_for_style_changes() -> None:
    """SON-151: Style/lint changes are low risk."""
    assert (
        assess_risk_level(
            title="Fix lint warnings",
            summary="Format code",
            files_in_scope=["src/a.py"],
        )
        == "low"
    )
