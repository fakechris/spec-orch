from __future__ import annotations

import json
from pathlib import Path

from spec_orch.domain.models import AcceptanceCampaign, AcceptanceMode, BuilderResult, WorkPacket


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
            coverage_expectations=["launcher create flow"],
            filing_policy="in_scope_only",
            exploration_budget="tight",
        ),
    )

    assert "Mode: feature_scoped" in prompt
    assert "Verify only the declared feature and its immediately adjacent states." in prompt
    assert '"coverage_expectations"' in prompt
    assert '"primary_routes"' in prompt


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
            primary_routes=["/"],
            related_routes=["/?mode=inbox"],
            coverage_expectations=["mission control", "transcript"],
            filing_policy="auto_file_broken_flows_only",
            exploration_budget="wide",
        ),
    )

    assert "Mode: exploratory" in prompt
    assert (
        "Act as an independent operator using the product to complete the intended task." in prompt
    )
    assert "Do not assume the mission framing or UI structure is correct." in prompt


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
            coverage_expectations=["settings", "mission transcript"],
            filing_policy="auto_file_regressions_only",
            exploration_budget="medium",
        ),
    )

    payload = json.loads(prompt.split("## Evidence Payload\n", 1)[1])
    assert payload["mission_id"] == "mission-3"
    assert payload["campaign"]["mode"] == "impact_sweep"
    assert (
        payload["artifacts"]["review_routes"]["transcript"] == "/?mission=mission-3&tab=transcript"
    )
