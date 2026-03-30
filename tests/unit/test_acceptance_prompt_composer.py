from __future__ import annotations

import json
from pathlib import Path

from spec_orch.domain.models import (
    AcceptanceCampaign,
    AcceptanceInteractionStep,
    AcceptanceMode,
    BuilderResult,
    WorkPacket,
)


def _worker_result(tmp_path: Path) -> tuple[WorkPacket, BuilderResult]:
    packet = WorkPacket(packet_id="pkt-1", title="Operator Console Dogfood")
    result = BuilderResult(
        succeeded=True,
        command=["echo", "ok"],
        stdout="ok",
        stderr="",
        report_path=tmp_path / "builder_report.json",
        adapter="stub",
        agent="stub",
    )
    return packet, result


def test_compose_acceptance_prompt_includes_mode_specific_instructions(tmp_path: Path) -> None:
    from spec_orch.services.acceptance.prompt_composer import compose_acceptance_prompt

    prompt = compose_acceptance_prompt(
        mission_id="mission-1",
        round_id=1,
        round_dir=tmp_path / "docs/specs/mission-1/rounds/round-01",
        worker_results=[_worker_result(tmp_path)],
        artifacts={
            "mission": {"mission_id": "mission-1", "title": "Mission 1"},
            "browser_evidence": {"tested_routes": ["/"]},
        },
        repo_root=tmp_path,
        campaign=AcceptanceCampaign(
            mode=AcceptanceMode.FEATURE_SCOPED,
            goal="Verify a single mission launcher interaction.",
            primary_routes=["/launcher"],
            related_routes=["/"],
            interaction_plans={
                "/launcher": [AcceptanceInteractionStep(action="click_text", target="Transcript")]
            },
            coverage_expectations=["launcher create flow"],
            required_interactions=["open launcher"],
            min_primary_routes=1,
            related_route_budget=1,
            interaction_budget="tight",
            filing_policy="in_scope_only",
            exploration_budget="tight",
        ),
    )

    assert "Mode: feature_scoped" in prompt
    assert "Verify only the declared feature and its immediately adjacent states." in prompt
    assert '"coverage_expectations"' in prompt
    assert '"primary_routes"' in prompt
    assert '"required_interactions"' in prompt
    assert '"min_primary_routes"' in prompt


def test_compose_acceptance_prompt_marks_exploratory_runs_as_user_perspective(
    tmp_path: Path,
) -> None:
    from spec_orch.services.acceptance.prompt_composer import compose_acceptance_prompt

    prompt = compose_acceptance_prompt(
        mission_id="mission-2",
        round_id=2,
        round_dir=tmp_path / "docs/specs/mission-2/rounds/round-02",
        worker_results=[_worker_result(tmp_path)],
        artifacts={
            "mission": {"mission_id": "mission-2", "title": "Mission 2"},
            "browser_evidence": {"tested_routes": ["/", "/?mode=inbox"]},
        },
        repo_root=tmp_path,
        campaign=AcceptanceCampaign(
            mode=AcceptanceMode.EXPLORATORY,
            goal="Dogfood the operator console from a real operator perspective.",
            primary_routes=["/", "/?mission=mission-2&mode=missions&tab=overview"],
            related_routes=[
                "/?mission=mission-2&mode=missions&tab=transcript",
                "/?mission=mission-2&mode=missions&tab=acceptance",
            ],
            interaction_plans={
                "/?mission=mission-2&mode=missions&tab=transcript": [
                    AcceptanceInteractionStep(action="click_text", target="All Missions")
                ]
            },
            coverage_expectations=["mission control", "transcript"],
            required_interactions=["switch mission mode", "inspect transcript"],
            min_primary_routes=1,
            related_route_budget=4,
            interaction_budget="wide",
            filing_policy="auto_file_broken_flows_only",
            exploration_budget="wide",
            seed_routes=["/", "/?mission=mission-2&mode=missions&tab=overview"],
            allowed_expansions=[
                "/?mission=mission-2&mode=missions&tab=transcript",
                "/?mission=mission-2&mode=missions&tab=acceptance",
                "/?mission=mission-2&mode=missions&tab=costs",
            ],
            critique_focus=[
                "information architecture confusion",
                "ambiguous terminology",
                "discoverability gaps",
            ],
            stop_conditions=[
                "stop when the route budget is exhausted",
                "stop when no adjacent surface adds new operator evidence",
            ],
            evidence_budget="bounded",
        ),
    )

    assert "Mode: exploratory" in prompt
    assert (
        "Act as an independent operator using the product to complete the intended task." in prompt
    )
    assert "Do not assume the mission framing or UI structure is correct." in prompt
    assert "## Adversarial Rubric" in prompt
    assert "Treat the current implementation and mission framing as falsifiable." in prompt
    assert "Do not auto-file broad UX criticism unless the flow is materially broken." in prompt
    assert "## Exploratory Contract" in prompt
    assert "Seed routes: /, /?mission=mission-2&mode=missions&tab=overview" in prompt
    assert (
        "Allowed expansions: /?mission=mission-2&mode=missions&tab=transcript, /?mission=mission-2&mode=missions&tab=acceptance, /?mission=mission-2&mode=missions&tab=costs"
        in prompt
    )
    assert (
        "Critique focus: information architecture confusion, ambiguous terminology, discoverability gaps"
        in prompt
    )
    assert "Evidence budget: bounded" in prompt
    assert "Confusing but operable UX is still valid exploratory evidence." in prompt
    assert "surface orientation" in prompt
    assert "evidence discoverability" in prompt
    assert "terminology clarity" in prompt
    assert "task continuity" in prompt
    assert "operator confidence / trust signaling" in prompt
    assert (
        "Treat inherited workflow proof artifacts as prior context, not as contradictions to the current exploratory replay"
        in prompt
    )
    assert (
        "If you return zero findings and zero issue proposals, the summary must explain why no critique candidate cleared the evidence threshold."
        in prompt
    )


def test_compose_acceptance_prompt_embeds_structured_payload(tmp_path: Path) -> None:
    from spec_orch.services.acceptance.prompt_composer import compose_acceptance_prompt

    prompt = compose_acceptance_prompt(
        mission_id="mission-3",
        round_id=3,
        round_dir=tmp_path / "docs/specs/mission-3/rounds/round-03",
        worker_results=[_worker_result(tmp_path)],
        artifacts={
            "mission": {"mission_id": "mission-3", "title": "Mission 3"},
            "browser_evidence": {"tested_routes": ["/settings"]},
            "review_routes": {"transcript": "/?mission=mission-3&tab=transcript"},
        },
        repo_root=tmp_path,
        campaign=AcceptanceCampaign(
            mode=AcceptanceMode.IMPACT_SWEEP,
            goal="Sweep related routes for dashboard regressions.",
            primary_routes=["/settings"],
            related_routes=["/", "/?mission=mission-3&tab=transcript"],
            interaction_plans={
                "/?mission=mission-3&tab=transcript": [
                    AcceptanceInteractionStep(action="click_text", target="Visual QA")
                ]
            },
            coverage_expectations=["settings", "mission transcript"],
            required_interactions=["switch transcript tab", "inspect settings state"],
            min_primary_routes=1,
            related_route_budget=2,
            interaction_budget="moderate",
            filing_policy="auto_file_regressions_only",
            exploration_budget="medium",
        ),
    )

    payload = json.loads(prompt.split("## Evidence Payload\n", 1)[1])
    assert payload["mission_id"] == "mission-3"
    assert payload["campaign"]["mode"] == "impact_sweep"
    assert payload["campaign"]["related_route_budget"] == 2
    assert (
        payload["campaign"]["interaction_plans"]["/?mission=mission-3&tab=transcript"][0]["target"]
        == "Visual QA"
    )
    assert (
        payload["artifacts"]["review_routes"]["transcript"] == "/?mission=mission-3&tab=transcript"
    )


def test_compose_acceptance_prompt_adds_mode_specific_filing_policy_guidance(
    tmp_path: Path,
) -> None:
    from spec_orch.services.acceptance.prompt_composer import compose_acceptance_prompt

    prompt = compose_acceptance_prompt(
        mission_id="mission-4",
        round_id=4,
        round_dir=tmp_path / "docs/specs/mission-4/rounds/round-04",
        worker_results=[_worker_result(tmp_path)],
        artifacts={"mission": {"mission_id": "mission-4", "title": "Mission 4"}},
        repo_root=tmp_path,
        campaign=AcceptanceCampaign(
            mode=AcceptanceMode.FEATURE_SCOPED,
            goal="Verify a targeted launcher fix.",
            primary_routes=["/launcher"],
            related_routes=["/"],
            coverage_expectations=["launcher fix"],
            required_interactions=["open launcher"],
            min_primary_routes=1,
            related_route_budget=1,
            interaction_budget="tight",
            filing_policy="in_scope_only",
            exploration_budget="tight",
        ),
    )

    assert "## Filing Policy" in prompt
    assert "Only propose auto-file issues for in-scope regressions" in prompt
    assert "If coverage is missing or partial, lower confidence and explain the gap." in prompt


def test_compose_acceptance_prompt_marks_workflow_runs_as_flow_verification(
    tmp_path: Path,
) -> None:
    from spec_orch.services.acceptance.prompt_composer import compose_acceptance_prompt

    prompt = compose_acceptance_prompt(
        mission_id="mission-5",
        round_id=5,
        round_dir=tmp_path / "docs/specs/mission-5/rounds/round-05",
        worker_results=[_worker_result(tmp_path)],
        artifacts={
            "mission": {"mission_id": "mission-5", "title": "Mission 5"},
            "browser_evidence": {"tested_routes": ["/", "/?mission=workflow-smoke&tab=transcript"]},
        },
        repo_root=tmp_path,
        campaign=AcceptanceCampaign(
            mode=AcceptanceMode.WORKFLOW,
            goal="Verify the operator can complete launcher and mission-control steps end-to-end.",
            primary_routes=["/", "/?mission=workflow-smoke&mode=missions&tab=overview"],
            related_routes=["/?mission=workflow-smoke&mode=missions&tab=transcript"],
            interaction_plans={
                "/": [
                    AcceptanceInteractionStep(
                        action="click_selector",
                        target='[data-automation-target="mission-card"][data-mission-id="workflow-smoke"]',
                    )
                ]
            },
            coverage_expectations=["launcher", "mission detail", "transcript"],
            required_interactions=[
                "select mission",
                "open transcript tab",
                "verify mission detail",
            ],
            min_primary_routes=2,
            related_route_budget=1,
            interaction_budget="moderate",
            filing_policy="auto_file_broken_flows_only",
            exploration_budget="bounded",
        ),
    )

    assert "Mode: workflow" in prompt
    assert "Verify that a real operator workflow can be completed end-to-end." in prompt
    assert "Treat end-to-end task completion as the primary contract for this review." in prompt
    assert (
        "Prefer step-level breakage, blocked transitions, and missing actionability over broad product critique."
        in prompt
    )
    assert "Use issue proposals for clearly broken or blocked operator flows" in prompt
    assert "## Workflow Contract" in prompt
    assert (
        "Required interactions: select mission, open transcript tab, verify mission detail"
        in prompt
    )
