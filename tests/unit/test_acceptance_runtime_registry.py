from __future__ import annotations

from spec_orch.acceptance_core.routing import AcceptanceGraphProfile


def test_graph_registry_exposes_canonical_verify_contract_graph() -> None:
    from spec_orch.acceptance_runtime.graph_registry import graph_definition_for

    definition = graph_definition_for(AcceptanceGraphProfile.VERIFY_CONTRACT)

    assert definition.profile == AcceptanceGraphProfile.VERIFY_CONTRACT
    assert [step.key for step in definition.steps] == [
        "contract_brief",
        "route_replay",
        "assert_contract",
        "summarize_judgment",
    ]
    assert definition.expected_step_artifacts == [
        "01-contract_brief.json",
        "02-route_replay.json",
        "03-assert_contract.json",
        "04-summarize_judgment.json",
    ]


def test_graph_registry_exposes_tuned_exploratory_graph() -> None:
    from spec_orch.acceptance_runtime.graph_registry import graph_definition_for

    definition = graph_definition_for(AcceptanceGraphProfile.TUNED_EXPLORATORY)

    assert [step.key for step in definition.steps] == [
        "surface_scan",
        "guided_probe",
        "candidate_review",
        "summarize_judgment",
    ]
    assert definition.supports_compare_overlay is True
    assert definition.loop_step_key == "guided_probe"


def test_graph_registry_maps_tuned_dashboard_compare_to_replay_shape() -> None:
    from spec_orch.acceptance_runtime.graph_registry import graph_definition_for

    definition = graph_definition_for(AcceptanceGraphProfile.TUNED_DASHBOARD_COMPARE)

    assert [step.key for step in definition.steps] == [
        "baseline_brief",
        "route_replay",
        "compare_evidence",
        "summarize_judgment",
    ]
    assert definition.supports_compare_overlay is True
