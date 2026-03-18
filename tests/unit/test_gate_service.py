from __future__ import annotations

from pathlib import Path

from spec_orch.domain.models import GateInput, ReviewSummary, VerificationSummary
from spec_orch.services.gate_service import GatePolicy, GateService


def test_default_policy_blocks_all_by_default() -> None:
    svc = GateService()
    result = svc.evaluate(GateInput())
    assert not result.mergeable
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


# ── Flow promotion detection (T3.3 contract) ──


def test_promotion_required_when_hotfix_has_code_changes() -> None:
    """C2: hotfix + code file in diff → promotion to standard."""
    svc = GateService(policy=GatePolicy(required_conditions=set()))
    result = svc.evaluate(GateInput(claimed_flow="hotfix", diff_stats={".py": 1}))
    assert result.promotion_required is True
    assert result.promotion_target == "standard"


def test_no_promotion_when_standard_doc_only() -> None:
    """C3: standard + only doc files → no promotion."""
    svc = GateService(policy=GatePolicy(required_conditions=set()))
    result = svc.evaluate(GateInput(claimed_flow="standard", diff_stats={".md": 2, ".txt": 1}))
    assert result.promotion_required is False
    assert result.promotion_target is None


def test_promotion_to_full_when_standard_has_code() -> None:
    """C4: standard + code files → promotion to full."""
    svc = GateService(policy=GatePolicy(required_conditions=set()))
    result = svc.evaluate(
        GateInput(
            claimed_flow="standard",
            diff_stats={".py": 5, ".md": 1},
        )
    )
    assert result.promotion_required is True
    assert result.promotion_target == "full"


def test_no_promotion_when_already_full() -> None:
    """C5: full flow → never promote (already highest)."""
    svc = GateService(policy=GatePolicy(required_conditions=set()))
    result = svc.evaluate(GateInput(claimed_flow="full", diff_stats={".py": 10}))
    assert result.promotion_required is False
    assert result.promotion_target is None


def test_no_promotion_when_claimed_flow_is_none() -> None:
    """C1: no claimed flow → no promotion (backward compatible)."""
    svc = GateService(policy=GatePolicy(required_conditions=set()))
    result = svc.evaluate(GateInput(claimed_flow=None, diff_stats={".py": 3}))
    assert result.promotion_required is False
    assert result.promotion_target is None


def test_promotion_does_not_affect_mergeable() -> None:
    """C6: promotion_required=True must NOT change mergeable."""
    policy = GatePolicy(required_conditions={"builder", "verification"})
    svc = GateService(policy=policy)
    result = svc.evaluate(
        GateInput(
            builder_succeeded=True,
            verification=VerificationSummary(
                lint_passed=True,
                typecheck_passed=True,
                test_passed=True,
                build_passed=True,
            ),
            claimed_flow="hotfix",
            diff_stats={".py": 1},
        )
    )
    assert result.mergeable is True
    assert result.promotion_required is True


def test_no_promotion_when_diff_stats_empty() -> None:
    """C7: empty diff_stats → no promotion (safe default)."""
    svc = GateService(policy=GatePolicy(required_conditions=set()))
    result = svc.evaluate(GateInput(claimed_flow="hotfix", diff_stats={}))
    assert result.promotion_required is False
    assert result.promotion_target is None


# ── T3.2: backtrack_reason inference ──


def test_backtrack_recoverable_on_builder_failure() -> None:
    svc = GateService(policy=GatePolicy(required_conditions={"builder", "verification"}))
    result = svc.evaluate(GateInput(builder_succeeded=False))
    assert result.mergeable is False
    assert result.backtrack_reason == "recoverable"


def test_backtrack_needs_redesign_on_spec_failure() -> None:
    svc = GateService(policy=GatePolicy(required_conditions={"spec_exists"}))
    result = svc.evaluate(GateInput(spec_exists=False))
    assert result.mergeable is False
    assert result.backtrack_reason == "needs_redesign"


def test_backtrack_none_when_all_pass() -> None:
    policy = GatePolicy(required_conditions={"builder"})
    svc = GateService(policy=policy)
    result = svc.evaluate(GateInput(builder_succeeded=True))
    assert result.mergeable is True
    assert result.backtrack_reason is None


def test_backtrack_needs_redesign_takes_priority() -> None:
    svc = GateService(
        policy=GatePolicy(required_conditions={"spec_exists", "builder", "verification"})
    )
    result = svc.evaluate(GateInput(spec_exists=False, builder_succeeded=False))
    assert result.backtrack_reason == "needs_redesign"


# ── T3.4: demotion_suggested ──


def test_demotion_suggested_when_conductor_proposes() -> None:
    svc = GateService(policy=GatePolicy(required_conditions=set()))
    result = svc.evaluate(
        GateInput(
            claimed_flow="full",
            demotion_proposed_by_conductor=True,
            diff_stats={".md": 2},
        )
    )
    assert result.demotion_suggested is True
    assert result.demotion_target == "standard"


def test_no_demotion_without_conductor_proposal() -> None:
    svc = GateService(policy=GatePolicy(required_conditions=set()))
    result = svc.evaluate(
        GateInput(
            claimed_flow="full",
            demotion_proposed_by_conductor=False,
            diff_stats={".md": 1},
        )
    )
    assert result.demotion_suggested is False


def test_no_demotion_when_diff_exceeds_threshold() -> None:
    svc = GateService(policy=GatePolicy(required_conditions=set()))
    result = svc.evaluate(
        GateInput(
            claimed_flow="full",
            demotion_proposed_by_conductor=True,
            diff_stats={".py": 10},
        )
    )
    assert result.demotion_suggested is False


def test_no_demotion_from_hotfix() -> None:
    svc = GateService(policy=GatePolicy(required_conditions=set()))
    result = svc.evaluate(
        GateInput(
            claimed_flow="hotfix",
            demotion_proposed_by_conductor=True,
            diff_stats={".md": 1},
        )
    )
    assert result.demotion_suggested is False


def test_demotion_standard_to_hotfix() -> None:
    svc = GateService(policy=GatePolicy(required_conditions=set()))
    result = svc.evaluate(
        GateInput(
            claimed_flow="standard",
            demotion_proposed_by_conductor=True,
            diff_stats={".md": 1},
        )
    )
    assert result.demotion_suggested is True
    assert result.demotion_target == "hotfix"
