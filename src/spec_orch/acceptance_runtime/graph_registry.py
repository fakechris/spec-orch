"""Registry of bounded acceptance graph profiles."""

from __future__ import annotations

from spec_orch.acceptance_core.routing import AcceptanceGraphProfile
from spec_orch.acceptance_runtime.graph_models import (
    AcceptanceGraphProfileDefinition,
    AcceptanceGraphStep,
)


def _verify_contract_graph() -> AcceptanceGraphProfileDefinition:
    return AcceptanceGraphProfileDefinition(
        profile=AcceptanceGraphProfile.VERIFY_CONTRACT,
        supports_compare_overlay=False,
        steps=[
            AcceptanceGraphStep("contract_brief", "Summarize the contract and success conditions."),
            AcceptanceGraphStep(
                "route_replay", "Replay the declared route and capture contract evidence."
            ),
            AcceptanceGraphStep("assert_contract", "Assert whether the contract still holds."),
            AcceptanceGraphStep("summarize_judgment", "Summarize the final judgment."),
        ],
        expected_step_artifacts=[
            "01-contract_brief.json",
            "02-route_replay.json",
            "03-assert_contract.json",
            "04-summarize_judgment.json",
        ],
    )


def _baseline_replay_graph(profile: AcceptanceGraphProfile) -> AcceptanceGraphProfileDefinition:
    return AcceptanceGraphProfileDefinition(
        profile=profile,
        supports_compare_overlay=True,
        steps=[
            AcceptanceGraphStep("baseline_brief", "Load the baseline and compare target."),
            AcceptanceGraphStep(
                "route_replay", "Replay the established route against the current target."
            ),
            AcceptanceGraphStep(
                "compare_evidence", "Compare current evidence against the known baseline."
            ),
            AcceptanceGraphStep("summarize_judgment", "Summarize the final judgment."),
        ],
        expected_step_artifacts=[
            "01-baseline_brief.json",
            "02-route_replay.json",
            "03-compare_evidence.json",
            "04-summarize_judgment.json",
        ],
    )


def _exploratory_graph(
    profile: AcceptanceGraphProfile, *, tuned: bool
) -> AcceptanceGraphProfileDefinition:
    return AcceptanceGraphProfileDefinition(
        profile=profile,
        supports_compare_overlay=tuned,
        loop_step_key="guided_probe",
        steps=[
            AcceptanceGraphStep(
                "surface_scan", "Scan the surface and identify high-value evidence slices."
            ),
            AcceptanceGraphStep(
                "guided_probe", "Probe the surface using bounded exploratory steps."
            ),
            AcceptanceGraphStep(
                "candidate_review", "Review observations and form candidate findings."
            ),
            AcceptanceGraphStep("summarize_judgment", "Summarize the final exploratory judgment."),
        ],
        expected_step_artifacts=[
            "01-surface_scan.json",
            "02-guided_probe.json",
            "03-candidate_review.json",
            "04-summarize_judgment.json",
        ],
    )


def _recon_probe_graph() -> AcceptanceGraphProfileDefinition:
    return AcceptanceGraphProfileDefinition(
        profile=AcceptanceGraphProfile.RECON_PROBE,
        supports_compare_overlay=False,
        steps=[
            AcceptanceGraphStep("surface_scan", "Perform a conservative surface scan."),
            AcceptanceGraphStep(
                "route_seed_probe", "Check only trusted route seeds without broad exploration."
            ),
            AcceptanceGraphStep("summarize_judgment", "Summarize conservative recon findings."),
        ],
        expected_step_artifacts=[
            "01-surface_scan.json",
            "02-route_seed_probe.json",
            "03-summarize_judgment.json",
        ],
    )


def build_default_graph_registry() -> dict[
    AcceptanceGraphProfile, AcceptanceGraphProfileDefinition
]:
    return {
        AcceptanceGraphProfile.VERIFY_CONTRACT: _verify_contract_graph(),
        AcceptanceGraphProfile.BASELINE_REPLAY: _baseline_replay_graph(
            AcceptanceGraphProfile.BASELINE_REPLAY
        ),
        AcceptanceGraphProfile.TUNED_DASHBOARD_COMPARE: _baseline_replay_graph(
            AcceptanceGraphProfile.TUNED_DASHBOARD_COMPARE
        ),
        AcceptanceGraphProfile.EXPLORATORY_PROBE: _exploratory_graph(
            AcceptanceGraphProfile.EXPLORATORY_PROBE,
            tuned=False,
        ),
        AcceptanceGraphProfile.TUNED_EXPLORATORY: _exploratory_graph(
            AcceptanceGraphProfile.TUNED_EXPLORATORY,
            tuned=True,
        ),
        AcceptanceGraphProfile.RECON_PROBE: _recon_probe_graph(),
    }


def graph_definition_for(profile: AcceptanceGraphProfile) -> AcceptanceGraphProfileDefinition:
    registry = build_default_graph_registry()
    return registry[profile]
