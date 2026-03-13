from __future__ import annotations

from pathlib import Path

from spec_orch.domain.models import GateInput, ReviewSummary, VerificationSummary
from spec_orch.services.gate_service import GatePolicy, GateService


def test_default_policy_blocks_all_by_default() -> None:
    svc = GateService()
    result = svc.evaluate(GateInput())
    assert not result.mergeable
    assert "verification" in result.failed_conditions
    assert "review" in result.failed_conditions
    assert "human_acceptance" in result.failed_conditions


def test_custom_policy_removes_human_acceptance() -> None:
    policy = GatePolicy(required_conditions={"builder", "verification", "review"})
    svc = GateService(policy=policy)

    gate_input = GateInput(
        builder_succeeded=True,
        verification=VerificationSummary(
            lint_passed=True, typecheck_passed=True, test_passed=True, build_passed=True
        ),
        review=ReviewSummary(verdict="pass", reviewed_by="alice"),
        human_acceptance=False,
    )
    result = svc.evaluate(gate_input)
    assert result.mergeable
    assert result.failed_conditions == []


def test_policy_from_yaml(tmp_path: Path) -> None:
    policy_file = tmp_path / "gate.policy.yaml"
    policy_file.write_text(
        """\
conditions:
  builder:
    required: true
    description: "Builder must pass"
  verification:
    required: true
    description: "Verification must pass"
  review:
    required: false
    description: "Review is optional"
  human_acceptance:
    required: false
    description: "Human acceptance is optional"

auto_merge: true
"""
    )
    policy = GatePolicy.from_yaml(policy_file)
    assert policy.required_conditions == {"builder", "verification"}
    assert policy.auto_merge is True

    svc = GateService(policy=policy)
    gate_input = GateInput(
        builder_succeeded=True,
        verification=VerificationSummary(
            lint_passed=True, typecheck_passed=True, test_passed=True, build_passed=True
        ),
    )
    result = svc.evaluate(gate_input)
    assert result.mergeable


def test_describe_policy_output() -> None:
    svc = GateService()
    desc = svc.describe_policy()
    assert "Gate Policy:" in desc
    assert "auto_merge:" in desc


def test_preview_condition_only_blocks_when_required_and_needed() -> None:
    policy = GatePolicy(required_conditions={"preview"})
    svc = GateService(policy=policy)

    result_not_required = svc.evaluate(GateInput(preview_required=False))
    assert result_not_required.mergeable

    result_required_not_passed = svc.evaluate(
        GateInput(preview_required=True, preview_passed=False)
    )
    assert not result_required_not_passed.mergeable
    assert "preview" in result_required_not_passed.failed_conditions

    result_required_passed = svc.evaluate(GateInput(preview_required=True, preview_passed=True))
    assert result_required_passed.mergeable
