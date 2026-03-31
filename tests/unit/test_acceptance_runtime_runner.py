from __future__ import annotations

import json

from spec_orch.acceptance_core.routing import AcceptanceGraphProfile
from spec_orch.runtime_chain.store import read_chain_events


def test_run_acceptance_graph_executes_steps_and_persists_trace(tmp_path) -> None:
    from spec_orch.acceptance_runtime.graph_registry import graph_definition_for
    from spec_orch.acceptance_runtime.runner import run_acceptance_graph

    seen_steps: list[str] = []

    def _invoke(system_prompt: str, user_prompt: str) -> str:
        payload = json.loads(user_prompt.split("\n", 3)[-1])
        step_key = payload["step_key"]
        seen_steps.append(step_key)
        next_transition = {
            "surface_scan": "guided_probe",
            "guided_probe": "candidate_review",
            "candidate_review": "summarize_judgment",
            "summarize_judgment": "",
        }[step_key]
        return json.dumps(
            {
                "decision": "continue" if next_transition else "complete",
                "outputs": (
                    {
                        f"{step_key}_notes": f"artifact for {step_key}",
                        "observations": [{"claim": "review me"}],
                    }
                    if step_key == "guided_probe"
                    else {f"{step_key}_notes": f"artifact for {step_key}"}
                ),
                "next_transition": next_transition,
                "warnings": [],
                "review_markdown": f"## {step_key}\n- ok",
            }
        )

    definition = graph_definition_for(AcceptanceGraphProfile.TUNED_EXPLORATORY)
    result = run_acceptance_graph(
        base_dir=tmp_path,
        run_id="agr-1",
        graph=definition,
        mission_id="mission-1",
        round_id=1,
        goal="Dogfood transcript UX",
        target="/?mission=mission-1&tab=transcript",
        evidence={"browser_evidence": {"tested_routes": ["/"]}},
        compare_overlay=False,
        invoke=_invoke,
    )

    assert seen_steps == [
        "surface_scan",
        "guided_probe",
        "candidate_review",
        "summarize_judgment",
    ]
    assert result["graph_profile"] == "tuned_exploratory_graph"
    assert len(result["step_artifacts"]) == 4
    assert result["step_artifacts"][0].endswith("01-surface_scan.json")
    assert (tmp_path / "acceptance_graph_runs" / "agr-1" / "graph_run.json").exists()
    assert (
        tmp_path / "acceptance_graph_runs" / "agr-1" / "steps" / "04-summarize_judgment.json"
    ).exists()


def test_run_acceptance_graph_allows_bounded_guided_probe_loop(tmp_path) -> None:
    from spec_orch.acceptance_runtime.graph_registry import graph_definition_for
    from spec_orch.acceptance_runtime.runner import run_acceptance_graph

    seen_steps: list[str] = []
    guided_probe_calls = 0

    def _invoke(system_prompt: str, user_prompt: str) -> str:
        nonlocal guided_probe_calls
        payload = json.loads(user_prompt.split("\n", 3)[-1])
        step_key = payload["step_key"]
        seen_steps.append(step_key)
        if step_key == "surface_scan":
            return json.dumps(
                {
                    "decision": "continue",
                    "outputs": {"surface_scan_notes": "start"},
                    "next_transition": "guided_probe",
                    "warnings": [],
                    "review_markdown": "## surface_scan",
                }
            )
        if step_key == "guided_probe":
            guided_probe_calls += 1
            if guided_probe_calls == 1:
                return json.dumps(
                    {
                        "decision": "loop",
                        "outputs": {
                            "observations": [{"claim": "first pass"}],
                            "continue_loop": True,
                        },
                        "next_transition": "guided_probe",
                        "warnings": [],
                        "review_markdown": "## guided_probe loop",
                    }
                )
            return json.dumps(
                {
                    "decision": "continue",
                    "outputs": {
                        "observations": [{"claim": "second pass"}],
                        "continue_loop": False,
                    },
                    "next_transition": "candidate_review",
                    "warnings": [],
                    "review_markdown": "## guided_probe complete",
                }
            )
        if step_key == "candidate_review":
            return json.dumps(
                {
                    "decision": "continue",
                    "outputs": {"candidate_ids": ["cf-1"]},
                    "next_transition": "summarize_judgment",
                    "warnings": [],
                    "review_markdown": "## candidate_review",
                }
            )
        return json.dumps(
            {
                "decision": "complete",
                "outputs": {},
                "next_transition": "",
                "warnings": [],
                "review_markdown": "## summarize_judgment",
            }
        )

    definition = graph_definition_for(AcceptanceGraphProfile.TUNED_EXPLORATORY)
    result = run_acceptance_graph(
        base_dir=tmp_path,
        run_id="agr-loop",
        graph=definition,
        mission_id="mission-1",
        round_id=1,
        goal="Dogfood transcript UX",
        target="/?mission=mission-1&tab=transcript",
        evidence={"browser_evidence": {"tested_routes": ["/"]}},
        compare_overlay=False,
        invoke=_invoke,
        loop_budget=2,
    )

    assert seen_steps == [
        "surface_scan",
        "guided_probe",
        "guided_probe",
        "candidate_review",
        "summarize_judgment",
    ]
    assert len(result["step_artifacts"]) == 5
    assert "guided_probe->guided_probe" in result["graph_transitions"]


def test_run_acceptance_graph_skips_candidate_review_without_reviewable_observations(
    tmp_path,
) -> None:
    from spec_orch.acceptance_runtime.graph_registry import graph_definition_for
    from spec_orch.acceptance_runtime.runner import run_acceptance_graph

    seen_steps: list[str] = []

    def _invoke(system_prompt: str, user_prompt: str) -> str:
        payload = json.loads(user_prompt.split("\n", 3)[-1])
        step_key = payload["step_key"]
        seen_steps.append(step_key)
        next_transition = {
            "surface_scan": "guided_probe",
            "guided_probe": "candidate_review",
            "summarize_judgment": "",
        }[step_key]
        outputs = {"surface_scan_notes": "start"} if step_key == "surface_scan" else {}
        return json.dumps(
            {
                "decision": "continue" if next_transition else "complete",
                "outputs": outputs,
                "next_transition": next_transition,
                "warnings": [],
                "review_markdown": f"## {step_key}",
            }
        )

    definition = graph_definition_for(AcceptanceGraphProfile.TUNED_EXPLORATORY)
    result = run_acceptance_graph(
        base_dir=tmp_path,
        run_id="agr-skip",
        graph=definition,
        mission_id="mission-1",
        round_id=1,
        goal="Dogfood transcript UX",
        target="/?mission=mission-1&tab=transcript",
        evidence={"browser_evidence": {"tested_routes": ["/"]}},
        compare_overlay=False,
        invoke=_invoke,
    )

    assert seen_steps == [
        "surface_scan",
        "guided_probe",
        "summarize_judgment",
    ]
    assert "guided_probe->candidate_review" not in result["graph_transitions"]
    assert len(result["step_artifacts"]) == 3


def test_run_acceptance_graph_emits_runtime_chain_events(tmp_path) -> None:
    from spec_orch.acceptance_runtime.graph_registry import graph_definition_for
    from spec_orch.acceptance_runtime.runner import run_acceptance_graph

    def _invoke(system_prompt: str, user_prompt: str) -> str:
        payload = json.loads(user_prompt.split("\n", 3)[-1])
        step_key = payload["step_key"]
        next_transition = {
            "contract_brief": "route_replay",
            "route_replay": "assert_contract",
            "assert_contract": "summarize_judgment",
            "summarize_judgment": "",
        }[step_key]
        return json.dumps(
            {
                "decision": "continue" if next_transition else "complete",
                "outputs": {f"{step_key}_notes": f"artifact for {step_key}"},
                "next_transition": next_transition,
                "warnings": [],
                "review_markdown": f"## {step_key}\n- ok",
            }
        )

    definition = graph_definition_for(AcceptanceGraphProfile.VERIFY_CONTRACT)
    chain_root = tmp_path / "operator" / "runtime_chain"
    run_acceptance_graph(
        base_dir=tmp_path,
        run_id="agr-chain",
        graph=definition,
        mission_id="mission-1",
        round_id=1,
        goal="Verify contract",
        target="/?mission=mission-1&tab=transcript",
        evidence={"browser_evidence": {"tested_routes": ["/"]}},
        compare_overlay=False,
        invoke=_invoke,
        chain_root=chain_root,
        chain_id="chain-mission-1",
        span_id="span-round-01-acceptance-graph",
        parent_span_id="span-round-01-acceptance",
    )

    events = read_chain_events(chain_root)

    assert [event.phase.value for event in events] == ["started", "completed"]
    assert all(event.subject_kind.value == "acceptance" for event in events)
