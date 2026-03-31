from __future__ import annotations

from pathlib import Path

import pytest


def test_routing_maps_compare_to_overlay_and_recon_is_first_class() -> None:
    from spec_orch.acceptance_core.models import AcceptanceRunMode
    from spec_orch.acceptance_core.routing import (
        AcceptanceRequest,
        build_acceptance_routing_decision,
    )

    request = AcceptanceRequest(
        goal="Compare this dashboard run to the previous known-good baseline.",
        target="mission:demo",
        constraints=["compare with previous run", "dashboard only"],
    )

    decision = build_acceptance_routing_decision(
        request,
        contract_strength="strong",
        surface_familiarity="known",
        baseline_available=True,
    )

    assert decision.base_run_mode is AcceptanceRunMode.REPLAY
    assert decision.run_mode is AcceptanceRunMode.REPLAY
    assert decision.compare_overlay is True
    assert decision.budget_profile == "replay_compare"
    assert decision.graph_profile == "baseline_replay_graph"
    assert decision.evidence_plan == [
        "baseline_artifacts",
        "route_replay_trace",
        "acceptance_review",
    ]
    assert decision.risk_posture == "cautious_compare"
    assert decision.recon_fallback_reason == ""


def test_routing_uses_recon_when_contract_and_surface_are_weak() -> None:
    from spec_orch.acceptance_core.models import AcceptanceRunMode
    from spec_orch.acceptance_core.routing import (
        AcceptanceRequest,
        build_acceptance_routing_decision,
    )

    request = AcceptanceRequest(
        goal="Take a look and tell me what this surface is doing.",
        target="artifact-bundle:unknown",
        constraints=[],
    )

    decision = build_acceptance_routing_decision(
        request,
        contract_strength="weak",
        surface_familiarity="unknown",
        baseline_available=False,
    )

    assert decision.base_run_mode is AcceptanceRunMode.RECON
    assert decision.run_mode is AcceptanceRunMode.RECON
    assert decision.compare_overlay is False
    assert decision.graph_profile == "recon_probe_graph"
    assert decision.budget_profile == "recon_bounded"
    assert decision.risk_posture == "conservative"
    assert decision.recon_fallback_reason == "weak_contract_or_unknown_surface"


def test_round_orchestrator_builds_acceptance_routing_decision_from_legacy_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from spec_orch.acceptance_core.models import AcceptanceRunMode
    from spec_orch.services.round_orchestrator import RoundOrchestrator
    from spec_orch.services.workers.in_memory_worker_handle_factory import (
        InMemoryWorkerHandleFactory,
    )

    monkeypatch.setenv("SPEC_ORCH_ACCEPTANCE_MODE", "workflow")

    class StubSupervisor:
        ADAPTER_NAME = "stub"

    class StubAssembler:
        def assemble(self, *args, **kwargs):
            return {}

    orchestrator = RoundOrchestrator(
        repo_root=tmp_path,
        supervisor=StubSupervisor(),
        worker_factory=InMemoryWorkerHandleFactory(creator=lambda session_id, workspace: None),
        context_assembler=StubAssembler(),
    )

    decision = orchestrator._build_acceptance_routing_decision(  # noqa: SLF001
        mission_id="mission-1",
        artifacts={"review_routes": {"overview": "/?mission=mission-1&tab=overview"}},
    )

    assert decision.base_run_mode is AcceptanceRunMode.REPLAY
    assert decision.surface_pack_ref is not None
    assert decision.surface_pack_ref.subject_id == "mission-1"


def test_round_orchestrator_routes_unknown_surface_to_recon_when_review_routes_missing(
    tmp_path: Path,
) -> None:
    from spec_orch.acceptance_core.models import AcceptanceRunMode
    from spec_orch.services.round_orchestrator import RoundOrchestrator
    from spec_orch.services.workers.in_memory_worker_handle_factory import (
        InMemoryWorkerHandleFactory,
    )

    class StubSupervisor:
        ADAPTER_NAME = "stub"

    class StubAssembler:
        def assemble(self, *args, **kwargs):
            return {}

    orchestrator = RoundOrchestrator(
        repo_root=tmp_path,
        supervisor=StubSupervisor(),
        worker_factory=InMemoryWorkerHandleFactory(creator=lambda session_id, workspace: None),
        context_assembler=StubAssembler(),
    )

    decision = orchestrator._build_acceptance_routing_decision(  # noqa: SLF001
        mission_id="mission-2",
        artifacts={},
        mode_override=None,
    )

    assert decision.base_run_mode is AcceptanceRunMode.RECON
    assert decision.recon_fallback_reason == "weak_contract_or_unknown_surface"


def test_routing_surfaces_internal_inputs_and_workflow_tuning_profile() -> None:
    from spec_orch.acceptance_core.routing import (
        AcceptanceRequest,
        build_acceptance_routing_decision,
    )

    decision = build_acceptance_routing_decision(
        AcceptanceRequest(
            goal="Compare this operator workflow with the last accepted baseline.",
            target="mission:demo",
            constraints=["dashboard only", "bounded budget"],
        ),
        contract_strength="strong",
        surface_familiarity="known",
        baseline_available=True,
        judgment_risk="high",
        mutation_risk="medium",
        workflow_tuning_availability="tuned_graph",
    )

    assert decision.routing_inputs.workflow_tuning_availability == "tuned_graph"
    assert decision.routing_inputs.judgment_risk == "high"
    assert decision.graph_profile == "tuned_dashboard_compare_graph"
    assert decision.surface_pack_ref is None


def test_compare_overlay_requires_relevant_baseline_signal() -> None:
    from spec_orch.acceptance_core.models import AcceptanceRunMode
    from spec_orch.acceptance_core.routing import (
        AcceptanceRequest,
        build_acceptance_routing_decision,
    )

    decision = build_acceptance_routing_decision(
        AcceptanceRequest(
            goal="Compare this new surface with something older.",
            target="mission:demo",
            constraints=["dashboard only"],
        ),
        contract_strength="strong",
        surface_familiarity="known",
        baseline_available=False,
    )

    assert decision.compare_overlay is False
    assert decision.base_run_mode is AcceptanceRunMode.VERIFY
    assert decision.budget_profile == "verify_tight"


def test_high_mutation_risk_forces_conservative_recon_fallback() -> None:
    from spec_orch.acceptance_core.models import AcceptanceRunMode
    from spec_orch.acceptance_core.routing import (
        AcceptanceRequest,
        build_acceptance_routing_decision,
    )

    decision = build_acceptance_routing_decision(
        AcceptanceRequest(
            goal="Dogfood this approval panel from an operator perspective.",
            target="mission:demo",
            constraints=["write surface"],
        ),
        contract_strength="medium",
        surface_familiarity="known",
        baseline_available=False,
        mutation_risk="high",
        workflow_tuning_availability="tuned_graph",
    )

    assert decision.base_run_mode is AcceptanceRunMode.RECON
    assert decision.risk_posture == "conservative"
    assert decision.recon_fallback_reason == "high_mutation_risk"
    assert "surface_scan" in decision.evidence_plan


def test_launcher_exposes_fresh_acpx_surface_pack_ref() -> None:
    from spec_orch.dashboard.launcher import _fresh_acpx_acceptance_surface_pack_ref

    ref = _fresh_acpx_acceptance_surface_pack_ref("fresh-acpx-demo")

    assert ref.pack_key == "dashboard_surface_pack_v1"
    assert ref.subject_kind == "mission"
    assert ref.subject_id == "fresh-acpx-demo"
