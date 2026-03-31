"""Acceptance intake and routing primitives."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TypeVar

from spec_orch.acceptance_core.models import AcceptanceRunMode


class ContractStrength(StrEnum):
    STRONG = "strong"
    MEDIUM = "medium"
    WEAK = "weak"


class SurfaceFamiliarity(StrEnum):
    KNOWN = "known"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class JudgmentRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class MutationRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class WorkflowTuningAvailability(StrEnum):
    NONE = "none"
    HEURISTIC = "heuristic"
    TUNED_GRAPH = "tuned_graph"


class AcceptanceBudgetProfile(StrEnum):
    VERIFY_TIGHT = "verify_tight"
    REPLAY_STANDARD = "replay_standard"
    REPLAY_COMPARE = "replay_compare"
    EXPLORE_BOUNDED = "explore_bounded"
    RECON_BOUNDED = "recon_bounded"


class AcceptanceGraphProfile(StrEnum):
    VERIFY_CONTRACT = "verify_contract_graph"
    BASELINE_REPLAY = "baseline_replay_graph"
    TUNED_DASHBOARD_COMPARE = "tuned_dashboard_compare_graph"
    EXPLORATORY_PROBE = "exploratory_probe_graph"
    TUNED_EXPLORATORY = "tuned_exploratory_graph"
    RECON_PROBE = "recon_probe_graph"


class AcceptanceRiskPosture(StrEnum):
    STANDARD = "standard"
    CAUTIOUS_COMPARE = "cautious_compare"
    BOUNDED_EXPLORATION = "bounded_exploration"
    CONSERVATIVE = "conservative"


_EnumT = TypeVar("_EnumT", bound=StrEnum)


def _coerce_enum(enum_cls: type[_EnumT], value: _EnumT | str) -> _EnumT:
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(str(value).strip().lower())
    except ValueError:
        return list(enum_cls)[0]


@dataclass(slots=True)
class AcceptanceRequest:
    goal: str
    target: str
    constraints: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AcceptanceSurfacePackRef:
    pack_key: str
    subject_kind: str
    subject_id: str


@dataclass(slots=True)
class AcceptanceRoutingInputs:
    contract_strength: ContractStrength
    surface_familiarity: SurfaceFamiliarity
    baseline_availability: bool
    judgment_risk: JudgmentRisk = JudgmentRisk.MEDIUM
    mutation_risk: MutationRisk = MutationRisk.MEDIUM
    workflow_tuning_availability: WorkflowTuningAvailability = WorkflowTuningAvailability.NONE

    def __post_init__(self) -> None:
        self.contract_strength = _coerce_enum(ContractStrength, self.contract_strength)
        self.surface_familiarity = _coerce_enum(SurfaceFamiliarity, self.surface_familiarity)
        self.judgment_risk = _coerce_enum(JudgmentRisk, self.judgment_risk)
        self.mutation_risk = _coerce_enum(MutationRisk, self.mutation_risk)
        self.workflow_tuning_availability = _coerce_enum(
            WorkflowTuningAvailability,
            self.workflow_tuning_availability,
        )


@dataclass(slots=True)
class AcceptanceRoutingDecision:
    base_run_mode: AcceptanceRunMode
    compare_overlay: bool = False
    budget_profile: AcceptanceBudgetProfile = AcceptanceBudgetProfile.VERIFY_TIGHT
    graph_profile: AcceptanceGraphProfile = AcceptanceGraphProfile.VERIFY_CONTRACT
    evidence_plan: list[str] = field(default_factory=list)
    risk_posture: AcceptanceRiskPosture = AcceptanceRiskPosture.STANDARD
    route_budget: int = 0
    action_budget: str = ""
    recon_fallback_reason: str = ""
    surface_pack_ref: AcceptanceSurfacePackRef | None = None
    routing_inputs: AcceptanceRoutingInputs | None = None

    @property
    def run_mode(self) -> AcceptanceRunMode:
        return self.base_run_mode


def build_acceptance_routing_decision(
    request: AcceptanceRequest,
    *,
    contract_strength: str,
    surface_familiarity: str,
    baseline_available: bool,
    judgment_risk: str = "medium",
    mutation_risk: str = "medium",
    workflow_tuning_availability: str = "none",
    surface_pack_ref: AcceptanceSurfacePackRef | None = None,
) -> AcceptanceRoutingDecision:
    goal = request.goal.lower()
    constraints = " ".join(request.constraints).lower()
    routing_inputs = AcceptanceRoutingInputs(
        contract_strength=contract_strength,
        surface_familiarity=surface_familiarity,
        baseline_availability=baseline_available,
        judgment_risk=judgment_risk,
        mutation_risk=mutation_risk,
        workflow_tuning_availability=workflow_tuning_availability,
    )
    compare_requested = any(
        token in f"{goal} {constraints}"
        for token in (
            "compare",
            "baseline",
            "known-good",
            "known good",
            "regression",
            "previous accepted",
            "last successful",
        )
    )
    compare_overlay = routing_inputs.baseline_availability and compare_requested

    if (
        routing_inputs.contract_strength is ContractStrength.WEAK
        or routing_inputs.surface_familiarity is SurfaceFamiliarity.UNKNOWN
    ):
        run_mode = AcceptanceRunMode.RECON
        recon_reason = "weak_contract_or_unknown_surface"
    elif routing_inputs.mutation_risk is MutationRisk.HIGH:
        run_mode = AcceptanceRunMode.RECON
        recon_reason = "high_mutation_risk"
    elif any(term in goal for term in ("confusing", "discoverability", "friction", "dogfood")):
        run_mode = AcceptanceRunMode.EXPLORE
        recon_reason = ""
    elif routing_inputs.baseline_availability and (
        compare_overlay
        or "workflow" in goal
        or "continuity" in goal
        or "baseline" in goal
        or "regression" in goal
    ):
        run_mode = AcceptanceRunMode.REPLAY
        recon_reason = ""
    else:
        run_mode = AcceptanceRunMode.VERIFY
        recon_reason = ""

    route_budget = {
        AcceptanceRunMode.VERIFY: 2,
        AcceptanceRunMode.REPLAY: 3,
        AcceptanceRunMode.EXPLORE: 4,
        AcceptanceRunMode.RECON: 2,
    }[run_mode]
    action_budget = {
        AcceptanceRunMode.VERIFY: "tight",
        AcceptanceRunMode.REPLAY: "moderate",
        AcceptanceRunMode.EXPLORE: "wide",
        AcceptanceRunMode.RECON: "bounded",
    }[run_mode]
    budget_profile = {
        AcceptanceRunMode.VERIFY: AcceptanceBudgetProfile.VERIFY_TIGHT,
        AcceptanceRunMode.REPLAY: (
            AcceptanceBudgetProfile.REPLAY_COMPARE
            if compare_overlay
            else AcceptanceBudgetProfile.REPLAY_STANDARD
        ),
        AcceptanceRunMode.EXPLORE: AcceptanceBudgetProfile.EXPLORE_BOUNDED,
        AcceptanceRunMode.RECON: AcceptanceBudgetProfile.RECON_BOUNDED,
    }[run_mode]
    if run_mode is AcceptanceRunMode.RECON:
        graph_profile = AcceptanceGraphProfile.RECON_PROBE
    elif run_mode is AcceptanceRunMode.REPLAY:
        graph_profile = (
            AcceptanceGraphProfile.TUNED_DASHBOARD_COMPARE
            if routing_inputs.workflow_tuning_availability is WorkflowTuningAvailability.TUNED_GRAPH
            else AcceptanceGraphProfile.BASELINE_REPLAY
        )
    elif run_mode is AcceptanceRunMode.EXPLORE:
        graph_profile = (
            AcceptanceGraphProfile.TUNED_EXPLORATORY
            if routing_inputs.workflow_tuning_availability is WorkflowTuningAvailability.TUNED_GRAPH
            else AcceptanceGraphProfile.EXPLORATORY_PROBE
        )
    else:
        graph_profile = AcceptanceGraphProfile.VERIFY_CONTRACT
    evidence_plan = {
        AcceptanceRunMode.VERIFY: [
            "contract_assertions",
            "acceptance_review",
        ],
        AcceptanceRunMode.REPLAY: [
            "baseline_artifacts",
            "route_replay_trace",
            "acceptance_review",
        ],
        AcceptanceRunMode.EXPLORE: [
            "surface_observations",
            "step_artifacts",
            "acceptance_review",
        ],
        AcceptanceRunMode.RECON: [
            "surface_scan",
            "route_seed_notes",
            "conservative_recon_summary",
        ],
    }[run_mode]
    if (
        run_mode is AcceptanceRunMode.RECON
        or routing_inputs.judgment_risk is JudgmentRisk.HIGH
        or routing_inputs.mutation_risk is MutationRisk.HIGH
    ):
        risk_posture = AcceptanceRiskPosture.CONSERVATIVE
    elif compare_overlay:
        risk_posture = AcceptanceRiskPosture.CAUTIOUS_COMPARE
    elif run_mode is AcceptanceRunMode.EXPLORE:
        risk_posture = AcceptanceRiskPosture.BOUNDED_EXPLORATION
    else:
        risk_posture = AcceptanceRiskPosture.STANDARD
    return AcceptanceRoutingDecision(
        base_run_mode=run_mode,
        compare_overlay=compare_overlay,
        budget_profile=budget_profile,
        graph_profile=graph_profile,
        evidence_plan=evidence_plan,
        risk_posture=risk_posture,
        route_budget=route_budget,
        action_budget=action_budget,
        recon_fallback_reason=recon_reason,
        surface_pack_ref=surface_pack_ref,
        routing_inputs=routing_inputs,
    )


__all__ = [
    "AcceptanceRequest",
    "AcceptanceBudgetProfile",
    "AcceptanceGraphProfile",
    "AcceptanceRiskPosture",
    "AcceptanceRoutingDecision",
    "AcceptanceRoutingInputs",
    "AcceptanceSurfacePackRef",
    "ContractStrength",
    "JudgmentRisk",
    "MutationRisk",
    "SurfaceFamiliarity",
    "WorkflowTuningAvailability",
    "build_acceptance_routing_decision",
]
