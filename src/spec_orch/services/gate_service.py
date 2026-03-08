from __future__ import annotations

from spec_orch.domain.models import GateInput, GateVerdict


class GateService:
    def evaluate(self, gate_input: GateInput) -> GateVerdict:
        failed_conditions: list[str] = []

        if not gate_input.spec_exists:
            failed_conditions.append("spec_exists")
        if not gate_input.spec_approved:
            failed_conditions.append("spec_approved")
        if not gate_input.within_boundaries:
            failed_conditions.append("within_boundaries")
        if not gate_input.builder_succeeded:
            failed_conditions.append("builder")
        if not gate_input.verification.all_passed:
            failed_conditions.append("verification")
        if gate_input.review.verdict != "pass":
            failed_conditions.append("review")
        if gate_input.preview_required and not gate_input.preview_passed:
            failed_conditions.append("preview")
        if not gate_input.human_acceptance:
            failed_conditions.append("human_acceptance")

        return GateVerdict(
            mergeable=not failed_conditions,
            failed_conditions=failed_conditions,
        )
