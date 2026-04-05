"""Builtin gate check skills — extracted from GateService.evaluate()."""

from __future__ import annotations

from spec_orch.domain.models import GateInput
from spec_orch.services.gate_skill_protocol import CheckResult, GateSkillRegistry


class _BuiltinSkill:
    """Base for builtin gate check skills."""

    _id: str = ""
    _description: str = ""

    @property
    def id(self) -> str:
        return self._id

    @property
    def description(self) -> str:
        return self._description


class SpecExistsSkill(_BuiltinSkill):
    _id = "spec_exists"
    _description = "Spec file exists on disk"

    def run(self, gate_input: GateInput) -> CheckResult:
        return CheckResult(
            passed=gate_input.spec_exists,
            reason="" if gate_input.spec_exists else "spec file not found",
            condition_id=self._id,
        )


class SpecApprovedSkill(_BuiltinSkill):
    _id = "spec_approved"
    _description = "Spec has been approved"

    def run(self, gate_input: GateInput) -> CheckResult:
        return CheckResult(
            passed=gate_input.spec_approved,
            reason="" if gate_input.spec_approved else "spec not approved",
            condition_id=self._id,
        )


class WithinBoundariesSkill(_BuiltinSkill):
    _id = "within_boundaries"
    _description = "Changes are within declared scope boundaries"

    def run(self, gate_input: GateInput) -> CheckResult:
        return CheckResult(
            passed=gate_input.within_boundaries,
            reason="" if gate_input.within_boundaries else "changes exceed boundaries",
            condition_id=self._id,
        )


class BuilderSkill(_BuiltinSkill):
    _id = "builder"
    _description = "Builder completed successfully"

    def run(self, gate_input: GateInput) -> CheckResult:
        return CheckResult(
            passed=gate_input.builder_succeeded,
            reason="" if gate_input.builder_succeeded else "builder failed",
            condition_id=self._id,
        )


class VerificationSkill(_BuiltinSkill):
    _id = "verification"
    _description = "All verification checks passed"

    def run(self, gate_input: GateInput) -> CheckResult:
        passed = gate_input.verification.all_passed
        reason = ""
        if not passed:
            steps = (
                gate_input.verification.details.keys()
                or gate_input.verification.step_outcomes.keys()
            )
            has_failed = any(
                gate_input.verification.get_step_outcome(step) == "fail" for step in steps
            )
            if has_failed:
                reason = "verification failed"
            elif gate_input.verification.has_skipped:
                reason = "verification skipped"
            else:
                reason = "verification failed"
        return CheckResult(
            passed=passed,
            reason=reason,
            condition_id=self._id,
        )


class ReviewSkill(_BuiltinSkill):
    _id = "review"
    _description = "Code review passed"

    def run(self, gate_input: GateInput) -> CheckResult:
        passed = gate_input.review.verdict == "pass"
        return CheckResult(
            passed=passed,
            reason="" if passed else f"review verdict: {gate_input.review.verdict}",
            condition_id=self._id,
        )


class PreviewSkill(_BuiltinSkill):
    _id = "preview"
    _description = "Preview deployment passed (when required)"

    def run(self, gate_input: GateInput) -> CheckResult:
        if not gate_input.preview_required:
            return CheckResult(passed=True, condition_id=self._id)
        return CheckResult(
            passed=gate_input.preview_passed,
            reason="" if gate_input.preview_passed else "preview not passed",
            condition_id=self._id,
        )


class HumanAcceptanceSkill(_BuiltinSkill):
    _id = "human_acceptance"
    _description = "Human acceptance received"

    def run(self, gate_input: GateInput) -> CheckResult:
        return CheckResult(
            passed=gate_input.human_acceptance,
            reason="" if gate_input.human_acceptance else "no human acceptance",
            condition_id=self._id,
        )


class FindingsSkill(_BuiltinSkill):
    _id = "findings"
    _description = "No blocking unresolved findings"

    def run(self, gate_input: GateInput) -> CheckResult:
        has_blocking = gate_input.review_meta.blocking_unresolved
        return CheckResult(
            passed=not has_blocking,
            reason="blocking unresolved findings" if has_blocking else "",
            condition_id=self._id,
        )


class ComplianceSkill(_BuiltinSkill):
    _id = "compliance"
    _description = "Builder output meets compliance contracts"

    def run(self, gate_input: GateInput) -> CheckResult:
        return CheckResult(
            passed=gate_input.compliance_passed,
            reason="" if gate_input.compliance_passed else "compliance failed",
            condition_id=self._id,
        )


def build_default_registry() -> GateSkillRegistry:
    """Create a registry pre-populated with all builtin gate check skills."""
    registry = GateSkillRegistry()
    for skill_cls in (
        SpecExistsSkill,
        SpecApprovedSkill,
        WithinBoundariesSkill,
        BuilderSkill,
        VerificationSkill,
        ReviewSkill,
        PreviewSkill,
        HumanAcceptanceSkill,
        FindingsSkill,
        ComplianceSkill,
    ):
        registry.register_builtin(skill_cls())
    return registry
