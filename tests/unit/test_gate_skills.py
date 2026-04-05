"""Tests for Gate dynamic check skills (Change 06 — SON-103)."""

from __future__ import annotations

from spec_orch.domain.models import (
    GateInput,
    ReviewSummary,
    VerificationDetail,
    VerificationSummary,
)
from spec_orch.services.gate_builtin_skills import (
    BuilderSkill,
    ComplianceSkill,
    PreviewSkill,
    ReviewSkill,
    SpecExistsSkill,
    VerificationSkill,
    build_default_registry,
)
from spec_orch.services.gate_service import GatePolicy, GateService
from spec_orch.services.gate_skill_protocol import (
    CheckResult,
    GateSkillRegistry,
)


class TestBuiltinSkills:
    def test_spec_exists_pass(self) -> None:
        r = SpecExistsSkill().run(GateInput(spec_exists=True))
        assert r.passed

    def test_spec_exists_fail(self) -> None:
        r = SpecExistsSkill().run(GateInput(spec_exists=False))
        assert not r.passed
        assert "not found" in r.reason

    def test_builder_pass(self) -> None:
        r = BuilderSkill().run(GateInput(builder_succeeded=True))
        assert r.passed

    def test_verification_fail(self) -> None:
        summary = VerificationSummary()
        summary.details["lint"] = VerificationDetail(
            command=["ruff", "check"], exit_code=1, stdout="", stderr="error"
        )
        r = VerificationSkill().run(GateInput(verification=summary))
        assert not r.passed

    def test_verification_skip_does_not_pass(self) -> None:
        summary = VerificationSummary()
        summary.details["lint"] = VerificationDetail(
            command=[], exit_code=0, stdout="", stderr="not configured — skipped"
        )
        summary.set_step_outcome("lint", "skipped")
        r = VerificationSkill().run(GateInput(verification=summary))
        assert not r.passed
        assert "skipped" in r.reason

    def test_review_pass(self) -> None:
        r = ReviewSkill().run(GateInput(review=ReviewSummary(verdict="pass")))
        assert r.passed

    def test_preview_not_required(self) -> None:
        r = PreviewSkill().run(GateInput(preview_required=False))
        assert r.passed

    def test_compliance_fail(self) -> None:
        r = ComplianceSkill().run(GateInput(compliance_passed=False))
        assert not r.passed


class TestGateSkillRegistry:
    def test_register_and_get(self) -> None:
        registry = GateSkillRegistry()

        class DummySkill:
            @property
            def id(self) -> str:
                return "dummy"

            @property
            def description(self) -> str:
                return "test"

            def run(self, gate_input: GateInput) -> CheckResult:
                return CheckResult(passed=True, condition_id="dummy")

        skill = DummySkill()
        registry.register(skill)
        assert registry.get("dummy") is skill
        assert "dummy" in registry.all_ids()

    def test_builtin_priority(self) -> None:
        registry = build_default_registry()
        assert registry.get("spec_exists") is not None
        assert registry.get("builder") is not None
        assert len(registry.all_ids()) == 10


class TestGateServiceWithSkills:
    def test_all_pass(self) -> None:
        policy = GatePolicy(required_conditions={"builder"})
        svc = GateService(policy=policy)
        v = svc.evaluate(GateInput(builder_succeeded=True))
        assert v.mergeable
        assert not v.failed_conditions

    def test_custom_skill_fail(self) -> None:
        registry = build_default_registry()

        class SecurityScanSkill:
            @property
            def id(self) -> str:
                return "security-scan"

            @property
            def description(self) -> str:
                return "Security scan"

            def run(self, gate_input: GateInput) -> CheckResult:
                return CheckResult(
                    passed=False, reason="vulnerabilities found", condition_id="security-scan"
                )

        registry.register(SecurityScanSkill())
        policy = GatePolicy(required_conditions={"builder", "security-scan"})
        svc = GateService(policy=policy, registry=registry)
        v = svc.evaluate(GateInput(builder_succeeded=True))
        assert not v.mergeable
        assert "security-scan" in v.failed_conditions

    def test_unknown_condition_warns(self) -> None:
        policy = GatePolicy(required_conditions={"nonexistent"})
        svc = GateService(policy=policy)
        v = svc.evaluate(GateInput())
        assert v.mergeable

    def test_backward_compat_all_builtin(self) -> None:
        """Default policy with all conditions should work like before."""
        svc = GateService()
        gi = GateInput(
            spec_exists=True,
            spec_approved=True,
            within_boundaries=True,
            builder_succeeded=True,
            verification=VerificationSummary(
                lint_passed=True, typecheck_passed=True, test_passed=True, build_passed=True
            ),
            review=ReviewSummary(verdict="pass"),
            human_acceptance=True,
        )
        v = svc.evaluate(gi)
        assert v.mergeable
