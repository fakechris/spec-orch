"""Gate-related domain models: GateInput, GateVerdict, GateFlowControl."""

from __future__ import annotations

from dataclasses import dataclass, field

from spec_orch.domain.issue import ReviewMeta, ReviewSummary, VerificationSummary


@dataclass(slots=True)
class GateInput:
    spec_exists: bool = False
    spec_approved: bool = False
    within_boundaries: bool = False
    builder_succeeded: bool = True
    verification: VerificationSummary = field(default_factory=VerificationSummary)
    review: ReviewSummary = field(default_factory=ReviewSummary)
    human_acceptance: bool = False
    preview_required: bool = False
    preview_passed: bool = False
    review_meta: ReviewMeta = field(default_factory=ReviewMeta)
    compliance_passed: bool = True
    claimed_flow: str | None = None
    demotion_proposed_by_conductor: bool = False
    diff_stats: dict[str, int] = field(default_factory=dict)
    issue_id: str = ""


@dataclass(slots=True)
class GateFlowControl:
    retry_recommended: bool = False
    escalation_required: bool = False
    promotion_required: bool = False
    promotion_target: str | None = None
    demotion_suggested: bool = False
    demotion_target: str | None = None
    backtrack_reason: str | None = None


@dataclass(slots=True)
class GateVerdict:
    mergeable: bool
    failed_conditions: list[str]
    mergeable_internal: bool = True
    mergeable_external: bool = True
    promotion_required: bool = False
    promotion_target: str | None = None
    demotion_suggested: bool = False
    demotion_target: str | None = None
    backtrack_reason: str | None = None
    flow_control: GateFlowControl = field(default_factory=GateFlowControl)

    def __post_init__(self) -> None:
        if self.flow_control == GateFlowControl():
            self.flow_control = GateFlowControl(
                promotion_required=self.promotion_required,
                promotion_target=self.promotion_target,
                demotion_suggested=self.demotion_suggested,
                demotion_target=self.demotion_target,
                backtrack_reason=self.backtrack_reason,
            )
        else:
            self.promotion_required = self.flow_control.promotion_required
            self.promotion_target = self.flow_control.promotion_target
            self.demotion_suggested = self.flow_control.demotion_suggested
            self.demotion_target = self.flow_control.demotion_target
            self.backtrack_reason = self.flow_control.backtrack_reason
