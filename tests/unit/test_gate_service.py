from spec_orch.domain.models import GateInput, ReviewSummary, VerificationSummary
from spec_orch.services.gate_service import GateService


def test_gate_service_marks_mergeable_when_required_conditions_pass() -> None:
    service = GateService()

    result = service.evaluate(
        GateInput(
            spec_exists=True,
            spec_approved=True,
            within_boundaries=True,
            verification=VerificationSummary(
                lint_passed=True,
                typecheck_passed=True,
                test_passed=True,
                build_passed=True,
            ),
            review=ReviewSummary(verdict="pass"),
            human_acceptance=True,
        )
    )

    assert result.mergeable is True
    assert result.failed_conditions == []


def test_gate_service_blocks_when_builder_failed() -> None:
    service = GateService()

    result = service.evaluate(
        GateInput(
            spec_exists=True,
            spec_approved=True,
            within_boundaries=True,
            builder_succeeded=False,
            verification=VerificationSummary(
                lint_passed=True,
                typecheck_passed=True,
                test_passed=True,
                build_passed=True,
            ),
            review=ReviewSummary(verdict="pass"),
            human_acceptance=True,
        )
    )

    assert result.mergeable is False
    assert "builder" in result.failed_conditions
