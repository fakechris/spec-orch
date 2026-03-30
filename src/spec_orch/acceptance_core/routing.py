"""Acceptance intake and routing primitives."""

from __future__ import annotations

from dataclasses import dataclass, field

from spec_orch.acceptance_core.models import AcceptanceRunMode


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
    contract_strength: str
    surface_familiarity: str
    baseline_availability: bool
    judgment_risk: str = "medium"
    mutation_risk: str = "medium"
    workflow_tuning_availability: str = "none"


@dataclass(slots=True)
class AcceptanceRoutingDecision:
    base_run_mode: AcceptanceRunMode
    compare_overlay: bool = False
    budget_profile: str = ""
    graph_profile: str = ""
    evidence_plan: list[str] = field(default_factory=list)
    risk_posture: str = ""
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
    compare_overlay = "compare" in goal or "compare" in constraints
    routing_inputs = AcceptanceRoutingInputs(
        contract_strength=contract_strength,
        surface_familiarity=surface_familiarity,
        baseline_availability=baseline_available,
        judgment_risk=judgment_risk,
        mutation_risk=mutation_risk,
        workflow_tuning_availability=workflow_tuning_availability,
    )

    if contract_strength == "weak" or surface_familiarity == "unknown":
        run_mode = AcceptanceRunMode.RECON
        recon_reason = "weak_contract_or_unknown_surface"
    elif any(term in goal for term in ("confusing", "discoverability", "friction", "dogfood")):
        run_mode = AcceptanceRunMode.EXPLORE
        recon_reason = ""
    elif baseline_available and (
        compare_overlay or "workflow" in goal or "continuity" in goal or "baseline" in goal
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
        AcceptanceRunMode.VERIFY: "verify_tight",
        AcceptanceRunMode.REPLAY: "replay_compare" if compare_overlay else "replay_standard",
        AcceptanceRunMode.EXPLORE: "explore_bounded",
        AcceptanceRunMode.RECON: "recon_bounded",
    }[run_mode]
    if run_mode is AcceptanceRunMode.RECON:
        graph_profile = "recon_probe_graph"
    elif run_mode is AcceptanceRunMode.REPLAY:
        graph_profile = (
            "tuned_dashboard_compare_graph"
            if workflow_tuning_availability == "tuned_graph"
            else "baseline_replay_graph"
        )
    elif run_mode is AcceptanceRunMode.EXPLORE:
        graph_profile = (
            "tuned_exploratory_graph"
            if workflow_tuning_availability == "tuned_graph"
            else "exploratory_probe_graph"
        )
    else:
        graph_profile = "verify_contract_graph"
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
        ],
    }[run_mode]
    risk_posture = (
        "conservative"
        if run_mode is AcceptanceRunMode.RECON or judgment_risk == "high"
        else "cautious_compare"
        if compare_overlay
        else "bounded_exploration"
        if run_mode is AcceptanceRunMode.EXPLORE
        else "standard"
    )
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
    "AcceptanceRoutingDecision",
    "AcceptanceRoutingInputs",
    "AcceptanceSurfacePackRef",
    "build_acceptance_routing_decision",
]
