from __future__ import annotations

import json
from pathlib import Path
from urllib.error import HTTPError, URLError


def test_materialize_fresh_execution_artifacts_writes_proof_files(tmp_path: Path) -> None:
    from spec_orch.services.fresh_acpx_e2e import materialize_fresh_execution_artifacts

    repo_root = tmp_path
    operator_dir = repo_root / "docs" / "specs" / "fresh-acpx-1" / "operator"
    round_dir = repo_root / "docs" / "specs" / "fresh-acpx-1" / "rounds" / "round-01"
    operator_dir.mkdir(parents=True, exist_ok=True)
    round_dir.mkdir(parents=True, exist_ok=True)

    mission_bootstrap = {
        "mission_id": "fresh-acpx-1",
        "title": "Fresh ACPX Mission E2E Smoke",
    }
    launch = {
        "last_launch": {
            "state": {
                "mission_id": "fresh-acpx-1",
                "phase": "executing",
            }
        },
        "runner": {
            "status": "running",
        },
    }
    (operator_dir / "mission_bootstrap.json").write_text(
        json.dumps(mission_bootstrap) + "\n",
        encoding="utf-8",
    )
    (operator_dir / "launch.json").write_text(
        json.dumps(launch) + "\n",
        encoding="utf-8",
    )
    round_summary = {
        "round_id": 1,
        "wave_id": 0,
        "status": "decided",
        "worker_results": [{"packet_id": "pkt-1", "status": "completed"}],
    }
    (round_dir / "round_summary.json").write_text(
        json.dumps(round_summary) + "\n",
        encoding="utf-8",
    )

    proof = materialize_fresh_execution_artifacts(
        repo_root=repo_root,
        mission_id="fresh-acpx-1",
        round_dir=round_dir,
        launch_result={
            "background_runner_started": True,
            "state": {"mission_id": "fresh-acpx-1", "phase": "executing"},
        },
    )

    daemon_run = json.loads((operator_dir / "daemon_run.json").read_text(encoding="utf-8"))
    assert daemon_run["mission_id"] == "fresh-acpx-1"
    assert daemon_run["fresh_round_path"] == str(round_dir)
    assert daemon_run["runner_status"] == "running"

    fresh_round_summary = json.loads(
        (round_dir / "fresh_round_summary.json").read_text(encoding="utf-8")
    )
    assert fresh_round_summary["round_id"] == 1
    builder_execution_summary = json.loads(
        (round_dir / "builder_execution_summary.json").read_text(encoding="utf-8")
    )
    assert builder_execution_summary["worker_results"][0]["packet_id"] == "pkt-1"

    assert proof["proof_type"] == "fresh_execution"
    assert proof["daemon_run"]["fresh_round_path"] == str(round_dir)
    assert proof["builder_execution_summary"]["worker_results"][0]["packet_id"] == "pkt-1"


def test_materialize_fresh_execution_artifacts_tolerates_malformed_json(tmp_path: Path) -> None:
    from spec_orch.services.fresh_acpx_e2e import materialize_fresh_execution_artifacts

    repo_root = tmp_path
    operator_dir = repo_root / "docs" / "specs" / "fresh-acpx-1" / "operator"
    round_dir = repo_root / "docs" / "specs" / "fresh-acpx-1" / "rounds" / "round-01"
    operator_dir.mkdir(parents=True, exist_ok=True)
    round_dir.mkdir(parents=True, exist_ok=True)

    (operator_dir / "mission_bootstrap.json").write_text("{not-json\n", encoding="utf-8")
    (operator_dir / "launch.json").write_text("{not-json\n", encoding="utf-8")
    (round_dir / "round_summary.json").write_text("{not-json\n", encoding="utf-8")

    proof = materialize_fresh_execution_artifacts(
        repo_root=repo_root,
        mission_id="fresh-acpx-1",
        round_dir=round_dir,
        launch_result={
            "background_runner_started": True,
            "state": {"mission_id": "fresh-acpx-1", "phase": "executing"},
        },
    )

    daemon_run = json.loads((operator_dir / "daemon_run.json").read_text(encoding="utf-8"))
    assert daemon_run["runner_status"] == "started"
    assert daemon_run["launch_phase"] == "executing"
    assert proof["mission_bootstrap"] == {}
    assert proof["launch"] == {}
    assert proof["builder_execution_summary"]["worker_results"] == []


def test_write_fresh_acpx_mission_report_separates_proof_layers(tmp_path: Path) -> None:
    from spec_orch.domain.models import AcceptanceCampaign, AcceptanceMode, AcceptanceReviewResult
    from spec_orch.services.fresh_acpx_e2e import write_fresh_acpx_mission_report

    round_dir = tmp_path / "docs" / "specs" / "fresh-acpx-1" / "rounds" / "round-01"
    round_dir.mkdir(parents=True, exist_ok=True)
    result = AcceptanceReviewResult(
        status="pass",
        summary="Fresh mission execution and workflow replay both succeeded.",
        confidence=0.97,
        evaluator="litellm_acceptance",
        tested_routes=["/", "/?mission=fresh-acpx-1&mode=missions&tab=overview"],
        acceptance_mode="workflow",
        coverage_status="complete",
        campaign=AcceptanceCampaign(
            mode=AcceptanceMode.WORKFLOW,
            goal="Validate a fresh mission post-run workflow replay.",
            primary_routes=["/"],
        ),
    )

    report = write_fresh_acpx_mission_report(
        round_dir=round_dir,
        mission_id="fresh-acpx-1",
        dashboard_url="http://127.0.0.1:8426/?mission=fresh-acpx-1&mode=missions&tab=overview",
        fresh_execution={
            "proof_type": "fresh_execution",
            "mission_bootstrap": {
                "mission_id": "fresh-acpx-1",
                "metadata": {"fresh_variant": "multi_packet"},
            },
            "launch": {"last_launch": {"state": {"phase": "executing"}}},
            "daemon_run": {"fresh_round_path": str(round_dir)},
            "builder_execution_summary": {"worker_results": [{"packet_id": "pkt-1"}]},
            "fresh_round_path": str(round_dir),
        },
        workflow_replay={
            "proof_type": "workflow_replay",
            "review_routes": {
                "overview": "/?mission=fresh-acpx-1&mode=missions&tab=overview",
            },
        },
        acceptance_review=result,
    )

    markdown = (round_dir / "fresh_acpx_mission_e2e_report.md").read_text(encoding="utf-8")
    assert "fresh execution proof" in markdown.lower()
    assert "workflow replay proof" in markdown.lower()
    assert "remaining gaps" in markdown.lower()
    assert "fresh-acpx-1" in markdown

    report_json = json.loads(
        (round_dir / "fresh_acpx_mission_e2e_report.json").read_text(encoding="utf-8")
    )
    assert report_json["mission_id"] == "fresh-acpx-1"
    assert report_json["variant"] == "multi_packet"
    assert report_json["fresh_execution"]["daemon_run"]["fresh_round_path"] == str(round_dir)
    assert report_json["workflow_replay"]["review_routes"]["overview"].endswith("tab=overview")
    assert report_json["acceptance_review"]["status"] == "pass"
    assert report["markdown_path"].endswith("fresh_acpx_mission_e2e_report.md")


def test_run_fresh_exploratory_acceptance_review_uses_exploratory_campaign(
    tmp_path: Path, monkeypatch
) -> None:
    from spec_orch.domain.models import (
        AcceptanceCampaign,
        AcceptanceFinding,
        AcceptanceMode,
        AcceptanceReviewResult,
    )
    from spec_orch.services.fresh_acpx_e2e import run_fresh_exploratory_acceptance_review

    repo_root = tmp_path
    monkeypatch.delenv("SPEC_ORCH_LLM_API_KEY", raising=False)
    monkeypatch.delenv("SPEC_ORCH_LLM_API_BASE", raising=False)
    monkeypatch.setenv("MINIMAX_API_KEY", "sk-minimax")
    monkeypatch.setenv("MINIMAX_ANTHROPIC_BASE_URL", "https://api.minimaxi.com/anthropic")
    mission_id = "fresh-acpx-1"
    round_dir = repo_root / "docs" / "specs" / mission_id / "rounds" / "round-02"
    round_dir.mkdir(parents=True, exist_ok=True)
    (round_dir / "round_summary.json").write_text(
        json.dumps({"round_id": 2}) + "\n",
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "spec_orch.services.fresh_acpx_e2e.build_fresh_exploratory_artifacts",
        lambda **kwargs: {
            "mission": {"mission_id": mission_id},
            "browser_evidence": {"status": "ok"},
            "review_routes": {"overview": "/?mission=fresh-acpx-1&tab=overview"},
        },
    )

    class FakeOrchestrator:
        def __init__(self, *, repo_root: Path, **_: object) -> None:
            captured["orchestrator_repo_root"] = repo_root

        def _build_acceptance_campaign(self, *, mission_id: str, artifacts: dict, mode_override):
            captured["mode_override"] = mode_override
            captured["campaign_artifacts"] = artifacts
            return AcceptanceCampaign(
                mode=AcceptanceMode.EXPLORATORY,
                goal="Dogfood the output from an operator perspective.",
                primary_routes=["/"],
                critique_focus=["discoverability gaps"],
                filing_policy="hold_ux_concerns_for_operator_review",
            )

    class FakeEvaluator:
        def __init__(
            self,
            *,
            repo_root: Path,
            model: str,
            api_type: str,
            api_key: str | None = None,
            api_base: str | None = None,
        ) -> None:
            captured["evaluator_repo_root"] = repo_root
            captured["model"] = model
            captured["api_type"] = api_type
            captured["api_key"] = api_key
            captured["api_base"] = api_base

        def evaluate_acceptance(self, **kwargs):
            captured["campaign"] = kwargs["campaign"]
            return AcceptanceReviewResult(
                status="pass",
                summary="Found one operator-facing discoverability issue.",
                confidence=0.82,
                evaluator="fake_acceptance",
                findings=[
                    AcceptanceFinding(
                        severity="medium",
                        summary="Acceptance tab label is hard to discover.",
                        critique_axis="discoverability gaps",
                        operator_task="inspect mission acceptance evidence",
                        why_it_matters="Operators may miss deeper evidence surfaces.",
                    )
                ],
                acceptance_mode="exploratory",
                coverage_status="complete",
                recommended_next_step="Review mission tab labeling and hierarchy.",
            )

    monkeypatch.setattr(
        "spec_orch.services.round_orchestrator.RoundOrchestrator",
        FakeOrchestrator,
    )
    monkeypatch.setattr(
        "spec_orch.services.acceptance.litellm_acceptance_evaluator.LiteLLMAcceptanceEvaluator",
        FakeEvaluator,
    )

    report = run_fresh_exploratory_acceptance_review(
        repo_root=repo_root,
        mission_id=mission_id,
        round_dir=round_dir,
        mission_payload={"mission_id": mission_id, "title": "Fresh mission"},
        browser_evidence={"status": "ok"},
    )

    saved = json.loads(
        (round_dir / "exploratory_acceptance_review.json").read_text(encoding="utf-8")
    )
    assert report["status"] == "pass"
    assert saved["acceptance_mode"] == "exploratory"
    assert saved["findings"][0]["critique_axis"] == "discoverability gaps"
    assert saved["recommended_next_step"] == "Review mission tab labeling and hierarchy."
    assert captured["mode_override"] is AcceptanceMode.EXPLORATORY
    assert isinstance(captured["campaign"], AcceptanceCampaign)
    assert captured["campaign"].filing_policy == "hold_ux_concerns_for_operator_review"
    assert captured["api_key"] == "sk-minimax"
    assert captured["api_base"] == "https://api.minimaxi.com/anthropic"


def test_run_fresh_exploratory_acceptance_review_inherits_acceptance_api_base_from_config(
    tmp_path: Path, monkeypatch
) -> None:
    from spec_orch.domain.models import AcceptanceCampaign, AcceptanceMode, AcceptanceReviewResult
    from spec_orch.services.fresh_acpx_e2e import run_fresh_exploratory_acceptance_review

    repo_root = tmp_path
    (repo_root / "spec-orch.toml").write_text(
        """
[acceptance_evaluator]
adapter = "litellm"
model = "MiniMax-M2.7-highspeed"
api_type = "anthropic"
api_key_env = "MINIMAX_API_KEY"
api_base_env = "MINIMAX_ANTHROPIC_BASE_URL"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MINIMAX_API_KEY", "sk-minimax")
    monkeypatch.setenv("MINIMAX_ANTHROPIC_BASE_URL", "https://api.minimaxi.com/anthropic")

    mission_id = "fresh-acpx-1"
    round_dir = repo_root / "docs" / "specs" / mission_id / "rounds" / "round-02"
    round_dir.mkdir(parents=True, exist_ok=True)
    (round_dir / "round_summary.json").write_text('{"round_id": 2}\n', encoding="utf-8")

    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "spec_orch.services.fresh_acpx_e2e.build_fresh_exploratory_artifacts",
        lambda **kwargs: {"mission": {"mission_id": mission_id}, "browser_evidence": {}},
    )

    class FakeOrchestrator:
        def __init__(self, *, repo_root: Path, **_: object) -> None:
            pass

        def _build_acceptance_campaign(self, *, mission_id: str, artifacts: dict, mode_override):
            return AcceptanceCampaign(
                mode=AcceptanceMode.EXPLORATORY,
                goal="Dogfood the output from an operator perspective.",
                primary_routes=["/"],
            )

    class FakeEvaluator:
        def __init__(
            self,
            *,
            repo_root: Path,
            model: str,
            api_type: str,
            api_key: str | None = None,
            api_base: str | None = None,
        ) -> None:
            captured["model"] = model
            captured["api_type"] = api_type
            captured["api_key"] = api_key
            captured["api_base"] = api_base

        def evaluate_acceptance(self, **kwargs):
            return AcceptanceReviewResult(
                status="pass",
                summary="Exploratory review succeeded.",
                confidence=0.9,
                evaluator="fake_acceptance",
            )

    monkeypatch.setattr("spec_orch.services.round_orchestrator.RoundOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "spec_orch.services.acceptance.litellm_acceptance_evaluator.LiteLLMAcceptanceEvaluator",
        FakeEvaluator,
    )

    report = run_fresh_exploratory_acceptance_review(
        repo_root=repo_root,
        mission_id=mission_id,
        round_dir=round_dir,
        mission_payload={"mission_id": mission_id},
        browser_evidence={"status": "ok"},
    )

    assert report["status"] == "pass"
    assert captured["model"] == "anthropic/MiniMax-M2.7-highspeed"
    assert captured["api_type"] == "anthropic"
    assert captured["api_key"] == "sk-minimax"
    assert captured["api_base"] == "https://api.minimaxi.com/anthropic"


def test_run_fresh_exploratory_acceptance_review_reports_config_error_when_minimax_base_missing(
    tmp_path: Path, monkeypatch
) -> None:
    from spec_orch.domain.models import AcceptanceCampaign, AcceptanceMode
    from spec_orch.services.fresh_acpx_e2e import run_fresh_exploratory_acceptance_review

    repo_root = tmp_path
    (repo_root / "spec-orch.toml").write_text(
        """
[acceptance_evaluator]
adapter = "litellm"
model = "MiniMax-M2.7-highspeed"
api_type = "anthropic"
api_key_env = "MINIMAX_API_KEY"
api_base_env = "MINIMAX_ANTHROPIC_BASE_URL"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MINIMAX_API_KEY", "sk-minimax")
    monkeypatch.delenv("MINIMAX_ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.delenv("SPEC_ORCH_LLM_API_BASE", raising=False)

    mission_id = "fresh-acpx-1"
    round_dir = repo_root / "docs" / "specs" / mission_id / "rounds" / "round-02"
    round_dir.mkdir(parents=True, exist_ok=True)
    (round_dir / "round_summary.json").write_text('{"round_id": 2}\n', encoding="utf-8")

    monkeypatch.setattr(
        "spec_orch.services.fresh_acpx_e2e.build_fresh_exploratory_artifacts",
        lambda **kwargs: {"mission": {"mission_id": mission_id}, "browser_evidence": {}},
    )

    class FakeOrchestrator:
        def __init__(self, *, repo_root: Path, **_: object) -> None:
            pass

        def _build_acceptance_campaign(self, *, mission_id: str, artifacts: dict, mode_override):
            return AcceptanceCampaign(
                mode=AcceptanceMode.EXPLORATORY,
                goal="Dogfood the output from an operator perspective.",
                primary_routes=["/"],
            )

    class ShouldNotConstructEvaluator:
        def __init__(self, **kwargs) -> None:
            raise AssertionError("Evaluator should not be constructed when config is invalid")

    monkeypatch.setattr("spec_orch.services.round_orchestrator.RoundOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "spec_orch.services.acceptance.litellm_acceptance_evaluator.LiteLLMAcceptanceEvaluator",
        ShouldNotConstructEvaluator,
    )

    report = run_fresh_exploratory_acceptance_review(
        repo_root=repo_root,
        mission_id=mission_id,
        round_dir=round_dir,
        mission_payload={"mission_id": mission_id},
        browser_evidence={"status": "ok"},
    )

    assert report["status"] == "warn"
    assert report["summary"] == "Exploratory acceptance configuration is incomplete."
    assert report["findings"][0]["summary"] == "Acceptance evaluator configuration is incomplete."
    assert "MINIMAX_ANTHROPIC_BASE_URL" in report["findings"][0]["details"]
    assert report["artifacts"]["acceptance_evaluator_config"]["api_base_present"] is False
    assert (
        report["recommended_next_step"]
        == "Set the acceptance evaluator API base and rerun exploratory critique."
    )


def test_run_fresh_exploratory_acceptance_review_collects_deeper_browser_evidence(
    tmp_path: Path, monkeypatch
) -> None:
    from spec_orch.domain.models import AcceptanceCampaign, AcceptanceMode, AcceptanceReviewResult
    from spec_orch.services.fresh_acpx_e2e import run_fresh_exploratory_acceptance_review

    repo_root = tmp_path
    (repo_root / "spec-orch.toml").write_text(
        """
[acceptance_evaluator]
adapter = "litellm"
model = "MiniMax-M2.7-highspeed"
api_type = "anthropic"
api_key_env = "MINIMAX_API_KEY"
api_base_env = "MINIMAX_ANTHROPIC_BASE_URL"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MINIMAX_API_KEY", "sk-minimax")
    monkeypatch.setenv("MINIMAX_ANTHROPIC_BASE_URL", "https://api.minimaxi.com/anthropic")
    monkeypatch.setenv("SPEC_ORCH_VISUAL_EVAL_URL", "http://127.0.0.1:8426")

    mission_id = "fresh-acpx-1"
    round_dir = repo_root / "docs" / "specs" / mission_id / "rounds" / "round-02"
    round_dir.mkdir(parents=True, exist_ok=True)
    (round_dir / "round_summary.json").write_text('{"round_id": 2}\n', encoding="utf-8")

    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "spec_orch.services.fresh_acpx_e2e.build_fresh_exploratory_artifacts",
        lambda **kwargs: {
            "mission": {"mission_id": mission_id},
            "browser_evidence": {"tested_routes": ["/"], "interactions": {"/": []}},
            "review_routes": {
                "overview": f"/?mission={mission_id}&mode=missions&tab=overview",
                "transcript": f"/?mission={mission_id}&mode=missions&tab=transcript",
            },
        },
    )

    class FakeOrchestrator:
        def __init__(self, *, repo_root: Path, **_: object) -> None:
            pass

        def _build_acceptance_campaign(self, *, mission_id: str, artifacts: dict, mode_override):
            return AcceptanceCampaign(
                mode=AcceptanceMode.EXPLORATORY,
                goal="Dogfood the output from an operator perspective.",
                primary_routes=["/"],
                related_routes=[f"/?mission={mission_id}&mode=missions&tab=transcript"],
                filing_policy="auto_file_broken_flows_only",
                exploration_budget="bounded",
            )

    def fake_collect_browser_evidence(**kwargs):
        captured["browser_paths"] = kwargs["paths"]
        captured["browser_output_name"] = kwargs["output_name"]
        captured["browser_interaction_plans"] = kwargs["interaction_plans"]
        return {
            "tested_routes": kwargs["paths"],
            "interactions": {
                f"/?mission={mission_id}&mode=missions&tab=transcript": [
                    {
                        "action": "click_selector",
                        "target": '[data-automation-target="transcript-filter"][data-filter-key="all"]',
                        "status": "passed",
                    },
                    {
                        "action": "wait_for_selector",
                        "target": '[data-automation-target="transcript-filter"][data-filter-key="all"][data-active="true"]',
                        "status": "passed",
                    },
                    {
                        "action": "wait_for_selector",
                        "target": '[data-automation-target="transcript-block"]',
                        "status": "passed",
                    },
                ]
            },
            "console_errors": [],
            "page_errors": [],
            "screenshots": {},
            "artifact_paths": {"round_dir": str(kwargs["round_dir"])},
        }

    class FakeEvaluator:
        def __init__(self, **kwargs) -> None:
            pass

        def evaluate_acceptance(self, **kwargs):
            captured["campaign"] = kwargs["campaign"]
            captured["artifacts"] = kwargs["artifacts"]
            return AcceptanceReviewResult(
                status="warn",
                summary="Exploratory critique found a discoverability issue.",
                confidence=0.85,
                evaluator="fake_acceptance",
                acceptance_mode="exploratory",
                coverage_status="complete",
            )

    monkeypatch.setattr("spec_orch.services.round_orchestrator.RoundOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "spec_orch.services.fresh_acpx_e2e.collect_playwright_browser_evidence",
        fake_collect_browser_evidence,
    )
    monkeypatch.setattr(
        "spec_orch.services.acceptance.litellm_acceptance_evaluator.LiteLLMAcceptanceEvaluator",
        FakeEvaluator,
    )

    report = run_fresh_exploratory_acceptance_review(
        repo_root=repo_root,
        mission_id=mission_id,
        round_dir=round_dir,
        mission_payload={"mission_id": mission_id},
        browser_evidence={"status": "ok"},
    )

    assert report["status"] == "warn"
    assert captured["browser_output_name"] == "exploratory_browser_evidence.json"
    assert f"/?mission={mission_id}&mode=missions&tab=transcript" in captured["browser_paths"]
    assert captured["campaign"].filing_policy == "hold_ux_concerns_for_operator_review"
    assert captured["campaign"].exploration_budget == "wide"
    assert captured["campaign"].critique_focus
    assert captured["artifacts"]["workflow_browser_evidence"]["tested_routes"] == ["/"]
    assert (
        captured["artifacts"]["browser_evidence"]["interactions"][
            f"/?mission={mission_id}&mode=missions&tab=transcript"
        ][2]["target"]
        == '[data-automation-target="transcript-block"]'
    )


def test_run_fresh_exploratory_acceptance_review_reuses_existing_browser_evidence_when_covered(
    tmp_path: Path, monkeypatch
) -> None:
    from spec_orch.domain.models import AcceptanceCampaign, AcceptanceMode, AcceptanceReviewResult
    from spec_orch.services.fresh_acpx_e2e import run_fresh_exploratory_acceptance_review

    repo_root = tmp_path
    (repo_root / "spec-orch.toml").write_text(
        """
[acceptance_evaluator]
adapter = "litellm"
model = "MiniMax-M2.7-highspeed"
api_type = "anthropic"
api_key_env = "MINIMAX_API_KEY"
api_base_env = "MINIMAX_ANTHROPIC_BASE_URL"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MINIMAX_API_KEY", "sk-minimax")
    monkeypatch.setenv("MINIMAX_ANTHROPIC_BASE_URL", "https://api.minimaxi.com/anthropic")

    mission_id = "fresh-acpx-1"
    transcript_route = f"/?mission={mission_id}&mode=missions&tab=transcript"
    round_dir = repo_root / "docs" / "specs" / mission_id / "rounds" / "round-02"
    round_dir.mkdir(parents=True, exist_ok=True)
    (round_dir / "round_summary.json").write_text('{"round_id": 2}\n', encoding="utf-8")

    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "spec_orch.services.fresh_acpx_e2e.build_fresh_exploratory_artifacts",
        lambda **kwargs: {
            "mission": {"mission_id": mission_id},
            "browser_evidence": {
                "tested_routes": ["/", transcript_route],
                "interactions": {transcript_route: [{"action": "open", "status": "passed"}]},
            },
            "review_routes": {"transcript": transcript_route},
        },
    )

    class FakeOrchestrator:
        def __init__(self, *, repo_root: Path, **_: object) -> None:
            pass

        def _build_acceptance_campaign(self, *, mission_id: str, artifacts: dict, mode_override):
            return AcceptanceCampaign(
                mode=AcceptanceMode.EXPLORATORY,
                goal="Dogfood the output from an operator perspective.",
                primary_routes=["/"],
                related_routes=[transcript_route],
            )

    def should_not_collect_browser_evidence(**kwargs):
        raise AssertionError("existing browser evidence already covers the exploratory campaign")

    class FakeEvaluator:
        def __init__(self, **kwargs) -> None:
            pass

        def evaluate_acceptance(self, **kwargs):
            captured["artifacts"] = kwargs["artifacts"]
            return AcceptanceReviewResult(
                status="pass",
                summary="Existing browser evidence was sufficient.",
                confidence=0.9,
                evaluator="fake_acceptance",
                acceptance_mode="exploratory",
                coverage_status="complete",
            )

    monkeypatch.setattr("spec_orch.services.round_orchestrator.RoundOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "spec_orch.services.fresh_acpx_e2e.collect_playwright_browser_evidence",
        should_not_collect_browser_evidence,
    )
    monkeypatch.setattr(
        "spec_orch.services.acceptance.litellm_acceptance_evaluator.LiteLLMAcceptanceEvaluator",
        FakeEvaluator,
    )

    report = run_fresh_exploratory_acceptance_review(
        repo_root=repo_root,
        mission_id=mission_id,
        round_dir=round_dir,
        mission_payload={"mission_id": mission_id},
        browser_evidence={"status": "ignored"},
    )

    assert report["status"] == "pass"
    assert "workflow_browser_evidence" not in captured["artifacts"]
    assert captured["artifacts"]["browser_evidence"]["tested_routes"] == ["/", transcript_route]


def test_run_fresh_exploratory_acceptance_review_compacts_evaluator_artifacts(
    tmp_path: Path, monkeypatch
) -> None:
    from spec_orch.domain.models import AcceptanceCampaign, AcceptanceMode, AcceptanceReviewResult
    from spec_orch.services.fresh_acpx_e2e import run_fresh_exploratory_acceptance_review

    repo_root = tmp_path
    (repo_root / "spec-orch.toml").write_text(
        """
[acceptance_evaluator]
adapter = "litellm"
model = "MiniMax-M2.7-highspeed"
api_type = "anthropic"
api_key_env = "MINIMAX_API_KEY"
api_base_env = "MINIMAX_ANTHROPIC_BASE_URL"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MINIMAX_API_KEY", "sk-minimax")
    monkeypatch.setenv("MINIMAX_ANTHROPIC_BASE_URL", "https://api.minimaxi.com/anthropic")

    mission_id = "fresh-acpx-1"
    round_dir = repo_root / "docs" / "specs" / mission_id / "rounds" / "round-02"
    round_dir.mkdir(parents=True, exist_ok=True)
    (round_dir / "round_summary.json").write_text('{"round_id": 2}\n', encoding="utf-8")

    oversized_artifacts = {
        "mission": {
            "mission_id": mission_id,
            "title": "Fresh mission",
            "intent": "Validate a narrow fresh ACPX path.",
            "acceptance_criteria": ["criterion-a"],
            "constraints": ["constraint-a"],
            "metadata": {"fresh_variant": "default"},
            "post_run_campaign": {"primary_routes": ["/", "/?mode=missions"]},
        },
        "browser_evidence": {
            "tested_routes": ["/", "/?mode=missions"],
            "interactions": {"/": [{"action": "click_selector", "status": "passed"}]},
            "console_errors": [],
            "page_errors": [],
        },
        "fresh_acpx_mission_e2e_report": {
            "mission_id": mission_id,
            "variant": "default",
            "dashboard_url": "http://127.0.0.1:8426",
            "fresh_execution": {"fresh_round_path": str(round_dir), "worker_results": [1, 2, 3]},
            "workflow_replay": {"review_routes": {"overview": "/?mission=fresh-acpx-1"}},
            "acceptance_review": {
                "status": "pass",
                "summary": "Workflow replay already passed.",
                "artifacts": {"proof_split": {"workflow_replay": {"huge": "payload"}}},
            },
            "remaining_gaps": ["gap-a"],
        },
        "fresh_execution": {
            "proof_type": "fresh_execution",
            "mission_bootstrap": {"mission_id": mission_id, "title": "Fresh mission"},
            "launch": {"runner": {"status": "foreground_required"}},
            "daemon_run": {
                "runner_status": "finished",
                "state": {"phase": "all_done", "current_round": 1},
            },
            "fresh_round_path": str(round_dir),
            "builder_execution_summary": {
                "round_id": 2,
                "status": "decided",
                "worker_results": [
                    {"packet_id": "pkt-1", "succeeded": True, "adapter": "acpx_worker"},
                    {"packet_id": "pkt-2", "succeeded": True, "adapter": "acpx_worker"},
                ],
            },
        },
        "workflow_replay": {
            "proof_type": "workflow_replay",
            "review_routes": {
                "overview": f"/?mission={mission_id}&mode=missions&tab=overview",
                "judgment": f"/?mission={mission_id}&mode=missions&tab=judgment",
            },
            "workflow_assertions": ["assertion-a"],
        },
        "review_routes": {
            "overview": f"/?mission={mission_id}&mode=missions&tab=overview",
        },
        "proof_split": {
            "fresh_execution": {"proof_type": "fresh_execution", "huge": "payload"},
            "workflow_replay": {"proof_type": "workflow_replay", "huge": "payload"},
        },
        "workflow_acceptance_review": {
            "status": "pass",
            "summary": "Workflow acceptance pass",
            "confidence": 0.91,
            "tested_routes": ["/", "/?mode=missions"],
            "artifacts": {"proof_split": {"workflow_replay": {"huge": "payload"}}},
            "findings": [{"summary": "finding-a"}],
        },
        "round_summary": {
            "round_id": 2,
            "status": "decided",
            "decision": {"action": "pass", "reason_code": "none"},
            "worker_results": [{"packet_id": "pkt-1"}, {"packet_id": "pkt-2"}],
        },
    }
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "spec_orch.services.fresh_acpx_e2e.build_fresh_exploratory_artifacts",
        lambda **kwargs: oversized_artifacts,
    )

    class FakeOrchestrator:
        def __init__(self, *, repo_root: Path, **_: object) -> None:
            pass

        def _build_acceptance_campaign(self, *, mission_id: str, artifacts: dict, mode_override):
            return AcceptanceCampaign(
                mode=AcceptanceMode.EXPLORATORY,
                goal="Dogfood the output from an operator perspective.",
                primary_routes=["/"],
            )

    class FakeEvaluator:
        def __init__(self, **kwargs) -> None:
            pass

        def evaluate_acceptance(self, **kwargs):
            captured["artifacts"] = kwargs["artifacts"]
            return AcceptanceReviewResult(
                status="pass",
                summary="Exploratory review succeeded.",
                confidence=0.9,
                evaluator="fake_acceptance",
            )

    monkeypatch.setattr("spec_orch.services.round_orchestrator.RoundOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "spec_orch.services.acceptance.litellm_acceptance_evaluator.LiteLLMAcceptanceEvaluator",
        FakeEvaluator,
    )

    report = run_fresh_exploratory_acceptance_review(
        repo_root=repo_root,
        mission_id=mission_id,
        round_dir=round_dir,
        mission_payload={"mission_id": mission_id},
        browser_evidence={"status": "ok"},
    )

    compacted = captured["artifacts"]
    assert report["status"] == "pass"
    assert isinstance(compacted, dict)
    assert "proof_split" not in compacted
    assert "post_run_campaign" not in compacted["mission"]
    assert "fresh_execution" not in compacted["fresh_acpx_mission_e2e_report"]
    assert "workflow_replay" not in compacted["fresh_acpx_mission_e2e_report"]
    assert "acceptance_review" not in compacted["fresh_acpx_mission_e2e_report"]
    assert "artifacts" not in compacted["workflow_acceptance_review"]
    assert compacted["workflow_acceptance_review"]["summary"] == "Workflow acceptance pass"
    assert len(json.dumps(compacted, ensure_ascii=False)) < len(
        json.dumps(oversized_artifacts, ensure_ascii=False)
    )


def test_existing_browser_evidence_requires_non_empty_logs_for_interaction_routes() -> None:
    from spec_orch.domain.models import (
        AcceptanceCampaign,
        AcceptanceInteractionStep,
        AcceptanceMode,
    )
    from spec_orch.services.fresh_acpx_e2e import _existing_browser_evidence_covers_campaign

    transcript_route = "/?mission=fresh-acpx-1&mode=missions&tab=transcript"
    campaign = AcceptanceCampaign(
        mode=AcceptanceMode.EXPLORATORY,
        goal="Dogfood the output from an operator perspective.",
        primary_routes=["/"],
        related_routes=[transcript_route],
        interaction_plans={
            transcript_route: [
                AcceptanceInteractionStep(
                    action="wait_for_selector",
                    target='[data-automation-target="transcript-filter"][data-filter-key="all"]',
                    description="Confirm transcript controls are visible.",
                )
            ]
        },
    )

    stale_browser_evidence = {
        "tested_routes": ["/", transcript_route],
        "interactions": {
            "/": [{"action": "click_selector", "status": "passed"}],
            transcript_route: [],
        },
    }

    assert _existing_browser_evidence_covers_campaign(stale_browser_evidence, campaign) is False


def test_materialize_fresh_execution_artifacts_prefers_launch_pickup_daemon_run(
    tmp_path: Path,
) -> None:
    from spec_orch.services.fresh_acpx_e2e import materialize_fresh_execution_artifacts

    repo_root = tmp_path
    mission_id = "fresh-acpx-1"
    operator_dir = repo_root / "docs" / "specs" / mission_id / "operator"
    round_dir = repo_root / "docs" / "specs" / mission_id / "rounds" / "round-01"
    operator_dir.mkdir(parents=True, exist_ok=True)
    round_dir.mkdir(parents=True, exist_ok=True)

    (operator_dir / "mission_bootstrap.json").write_text(
        json.dumps({"mission_id": mission_id, "title": "Fresh ACPX Mission"}) + "\n",
        encoding="utf-8",
    )
    (operator_dir / "launch.json").write_text(
        json.dumps(
            {
                "last_launch": {"state": {"mission_id": mission_id, "phase": "executing"}},
                "runner": {"status": "foreground_required"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (operator_dir / "launch_pickup.json").write_text(
        json.dumps(
            {
                "mission_id": mission_id,
                "daemon_run": {
                    "mission_id": mission_id,
                    "proof_type": "fresh_execution",
                    "runner_status": "finished",
                    "state": {
                        "mission_id": mission_id,
                        "phase": "all_done",
                        "current_round": 1,
                    },
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (round_dir / "round_summary.json").write_text(
        json.dumps({"round_id": 1, "status": "decided", "worker_results": []}) + "\n",
        encoding="utf-8",
    )

    proof = materialize_fresh_execution_artifacts(
        repo_root=repo_root,
        mission_id=mission_id,
        round_dir=round_dir,
        launch_result={
            "background_runner_started": False,
            "state": {"mission_id": mission_id, "phase": "executing"},
        },
    )

    assert proof["daemon_run"]["runner_status"] == "finished"
    assert proof["daemon_run"]["state"]["phase"] == "all_done"


def test_run_fresh_execution_once_advances_lifecycle_and_records_daemon_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from spec_orch.services.fresh_acpx_e2e import run_fresh_execution_once

    repo_root = tmp_path
    operator_dir = repo_root / "docs" / "specs" / "fresh-acpx-1" / "operator"
    operator_dir.mkdir(parents=True, exist_ok=True)

    class FakeState:
        def to_dict(self) -> dict[str, object]:
            return {"mission_id": "fresh-acpx-1", "phase": "all_done", "current_round": 1}

    class FakeLifecycleManager:
        def auto_advance(self, mission_id: str) -> FakeState:
            assert mission_id == "fresh-acpx-1"
            return FakeState()

    monkeypatch.setattr(
        "spec_orch.services.fresh_acpx_e2e._build_execution_lifecycle_manager",
        lambda repo_root: FakeLifecycleManager(),
    )

    result = run_fresh_execution_once(repo_root=repo_root, mission_id="fresh-acpx-1")

    daemon_run = json.loads((operator_dir / "daemon_run.json").read_text(encoding="utf-8"))
    assert daemon_run["runner_status"] == "finished"
    assert daemon_run["state"]["phase"] == "all_done"
    assert result["state"]["phase"] == "all_done"


def test_run_fresh_launch_and_pickup_records_consistent_proof(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from spec_orch.services.fresh_acpx_e2e import run_fresh_launch_and_pickup

    operator_dir = tmp_path / "docs" / "specs" / "fresh-acpx-1" / "operator"
    operator_dir.mkdir(parents=True, exist_ok=True)
    launch_calls: list[bool] = []

    monkeypatch.setattr(
        "spec_orch.dashboard.launcher._launch_mission",
        lambda repo_root, mission_id, *, allow_background_runner=True: (
            launch_calls.append(allow_background_runner)
            or {
                "mission_id": mission_id,
                "background_runner_started": False,
                "state": {"mission_id": mission_id, "phase": "executing"},
                "launch": {"runner": {"status": "foreground_required"}},
            }
        ),
    )
    monkeypatch.setattr(
        "spec_orch.services.fresh_acpx_e2e.run_fresh_execution_once",
        lambda *, repo_root, mission_id: {
            "mission_id": mission_id,
            "runner_status": "finished",
            "state": {"mission_id": mission_id, "phase": "all_done"},
        },
    )

    result = run_fresh_launch_and_pickup(repo_root=tmp_path, mission_id="fresh-acpx-1")

    persisted = json.loads((operator_dir / "launch_pickup.json").read_text(encoding="utf-8"))
    assert launch_calls == [False]
    assert persisted["mission_id"] == "fresh-acpx-1"
    assert persisted["launch_result"]["state"]["phase"] == "executing"
    assert persisted["daemon_run"]["state"]["phase"] == "all_done"
    assert result["daemon_run"]["runner_status"] == "finished"


def test_run_fresh_launch_and_pickup_skips_local_pickup_when_daemon_running(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from spec_orch.services.fresh_acpx_e2e import run_fresh_launch_and_pickup

    operator_dir = tmp_path / "docs" / "specs" / "fresh-acpx-1" / "operator"
    operator_dir.mkdir(parents=True, exist_ok=True)
    pickup_attempts: list[str] = []

    monkeypatch.setattr(
        "spec_orch.dashboard.launcher._launch_mission",
        lambda repo_root, mission_id, *, allow_background_runner=True: {
            "mission_id": mission_id,
            "background_runner_started": False,
            "state": {"mission_id": mission_id, "phase": "executing"},
            "launch": {"runner": {"status": "daemon_running"}},
        },
    )
    monkeypatch.setattr(
        "spec_orch.services.fresh_acpx_e2e.run_fresh_execution_once",
        lambda *, repo_root, mission_id: pickup_attempts.append(mission_id),
    )

    result = run_fresh_launch_and_pickup(repo_root=tmp_path, mission_id="fresh-acpx-1")

    persisted = json.loads((operator_dir / "launch_pickup.json").read_text(encoding="utf-8"))
    assert pickup_attempts == []
    assert persisted["daemon_run"] is None
    assert result["daemon_run"] is None


def test_wait_for_dashboard_ready_retries_until_probe_succeeds(monkeypatch) -> None:
    from spec_orch.services.fresh_acpx_e2e import wait_for_dashboard_ready

    attempts: list[int] = []

    def fake_probe(url: str, timeout_seconds: float) -> dict[str, object]:
        attempts.append(1)
        if len(attempts) < 3:
            raise URLError("connection refused")
        return {"status": 200, "url": url}

    monkeypatch.setattr("spec_orch.services.fresh_acpx_e2e._probe_dashboard", fake_probe)
    monkeypatch.setattr("spec_orch.services.fresh_acpx_e2e.time.sleep", lambda _: None)

    result = wait_for_dashboard_ready("http://127.0.0.1:8426/", timeout_seconds=1.0)

    assert result["ready"] is True
    assert result["attempts"] == 3
    assert result["status"] == 200


def test_wait_for_dashboard_ready_times_out_with_last_error(monkeypatch) -> None:
    from spec_orch.services.fresh_acpx_e2e import wait_for_dashboard_ready

    monkeypatch.setattr(
        "spec_orch.services.fresh_acpx_e2e._probe_dashboard",
        lambda url, timeout_seconds: (_ for _ in ()).throw(URLError("still starting")),
    )
    monkeypatch.setattr("spec_orch.services.fresh_acpx_e2e.time.sleep", lambda _: None)

    try:
        wait_for_dashboard_ready("http://127.0.0.1:8426/", timeout_seconds=0.01)
    except TimeoutError as exc:
        assert "still starting" in str(exc)
    else:
        raise AssertionError("Expected readiness polling to time out")


def test_wait_for_dashboard_ready_treats_http_error_status_as_ready(monkeypatch) -> None:
    from spec_orch.services.fresh_acpx_e2e import wait_for_dashboard_ready

    def fake_probe(url: str, timeout_seconds: float) -> dict[str, object]:
        raise HTTPError(url, 404, "not found", hdrs=None, fp=None)

    monkeypatch.setattr("spec_orch.services.fresh_acpx_e2e._probe_dashboard", fake_probe)
    monkeypatch.setattr("spec_orch.services.fresh_acpx_e2e.time.sleep", lambda _: None)

    result = wait_for_dashboard_ready("http://127.0.0.1:8426/", timeout_seconds=0.1)

    assert result["ready"] is True
    assert result["status"] == 404


def test_resolve_dashboard_port_prefers_requested_port_when_available() -> None:
    from spec_orch.services.fresh_acpx_e2e import resolve_dashboard_port

    port = resolve_dashboard_port(0)

    assert isinstance(port, int)
    assert port > 0


def test_resolve_dashboard_port_avoids_busy_requested_port() -> None:
    import socket

    from spec_orch.services.fresh_acpx_e2e import resolve_dashboard_port

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        busy_port = sock.getsockname()[1]

        resolved_port = resolve_dashboard_port(busy_port)

    assert resolved_port != busy_port
    assert resolved_port > 0


def test_resolve_dashboard_port_candidates_prioritize_requested_port() -> None:
    from spec_orch.services.fresh_acpx_e2e import resolve_dashboard_port_candidates

    candidates = resolve_dashboard_port_candidates(0, attempts=3)

    assert len(candidates) == 3
    assert len(set(candidates)) == len(candidates)
    assert all(port > 0 for port in candidates)


def test_resolve_dashboard_port_candidates_skip_busy_requested_port() -> None:
    import socket

    from spec_orch.services.fresh_acpx_e2e import resolve_dashboard_port_candidates

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        busy_port = sock.getsockname()[1]

        candidates = resolve_dashboard_port_candidates(busy_port, attempts=3)

    assert len(candidates) == 3
    assert busy_port not in candidates
    assert len(set(candidates)) == len(candidates)


def test_compact_acceptance_review_for_evaluator_limits_entries() -> None:
    from spec_orch.services.fresh_acpx_e2e import _compact_acceptance_review_for_evaluator

    payload = _compact_acceptance_review_for_evaluator(
        {
            "status": "warn",
            "summary": "review",
            "findings": [
                {"severity": "medium", "summary": f"finding-{index}", "route": "/", "critique_axis": "ux"}
                for index in range(7)
            ],
            "issue_proposals": [
                {
                    "title": f"proposal-{index}",
                    "summary": "summary",
                    "severity": "medium",
                    "route": "/",
                    "critique_axis": "ux",
                }
                for index in range(7)
            ],
        }
    )

    assert len(payload["findings"]) == 5
    assert len(payload["issue_proposals"]) == 5


def test_compact_browser_evidence_for_evaluator_limits_interaction_steps() -> None:
    from spec_orch.services.fresh_acpx_e2e import _compact_browser_evidence_for_evaluator

    payload = _compact_browser_evidence_for_evaluator(
        {
            "tested_routes": ["/"],
            "interactions": {
                "/": [
                    {
                        "action": "click",
                        "target": f"target-{index}",
                        "description": f"step-{index}",
                        "status": "ok",
                    }
                    for index in range(10)
                ]
            },
        }
    )

    assert len(payload["interactions"]["/"]) == 8


def test_assert_fresh_plan_budget_rejects_broad_plan() -> None:
    from spec_orch.services.fresh_acpx_e2e import assert_fresh_plan_budget

    broad_plan = {
        "waves": [
            {"wave_number": 0, "work_packets": [{"packet_id": "one"}, {"packet_id": "two"}]},
            {"wave_number": 1, "work_packets": [{"packet_id": "three"}]},
        ]
    }

    try:
        assert_fresh_plan_budget(broad_plan, max_waves=1, max_packets=2)
    except ValueError as exc:
        assert "max_waves=1" in str(exc)
        assert "max_packets=2" in str(exc)
    else:
        raise AssertionError("Expected broad fresh plan to fail budget guard")


def test_assert_fresh_plan_budget_accepts_narrow_plan() -> None:
    from spec_orch.services.fresh_acpx_e2e import assert_fresh_plan_budget

    narrow_plan = {
        "waves": [
            {"wave_number": 0, "work_packets": [{"packet_id": "one"}, {"packet_id": "two"}]},
        ]
    }

    summary = assert_fresh_plan_budget(narrow_plan, max_waves=1, max_packets=2)

    assert summary["wave_count"] == 1
    assert summary["packet_count"] == 2


def test_build_fresh_exploratory_artifacts_inherits_prior_workflow_proof(
    tmp_path: Path,
) -> None:
    from spec_orch.services.fresh_acpx_e2e import build_fresh_exploratory_artifacts

    repo_root = tmp_path
    mission_id = "fresh-acpx-1"
    round_dir = repo_root / "docs" / "specs" / mission_id / "rounds" / "round-01"
    round_dir.mkdir(parents=True, exist_ok=True)

    report_payload = {
        "mission_id": mission_id,
        "fresh_execution": {"proof_type": "fresh_execution", "fresh_round_path": str(round_dir)},
        "workflow_replay": {
            "proof_type": "workflow_replay",
            "review_routes": {"overview": f"/?mission={mission_id}&tab=overview"},
        },
        "acceptance_review": {
            "status": "pass",
            "coverage_status": "complete",
            "summary": "Workflow replay already passed.",
        },
    }
    (round_dir / "fresh_acpx_mission_e2e_report.json").write_text(
        json.dumps(report_payload) + "\n",
        encoding="utf-8",
    )
    (round_dir / "round_summary.json").write_text(
        json.dumps(
            {
                "round_id": 1,
                "status": "decided",
                "decision": {"action": "retry", "reason_code": "contracts_not_defined"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (round_dir / "acceptance_review.json").write_text(
        json.dumps({"status": "pass", "summary": "Workflow acceptance pass"}) + "\n",
        encoding="utf-8",
    )

    artifacts = build_fresh_exploratory_artifacts(
        repo_root=repo_root,
        mission_id=mission_id,
        round_dir=round_dir,
        mission_payload={"mission_id": mission_id, "acceptance_criteria": ["criterion"]},
        browser_evidence={"tested_routes": ["/"]},
    )

    assert artifacts["fresh_execution"]["proof_type"] == "fresh_execution"
    assert artifacts["workflow_replay"]["proof_type"] == "workflow_replay"
    assert artifacts["review_routes"]["overview"].endswith("tab=overview")
    assert artifacts["proof_split"]["fresh_execution"]["fresh_round_path"] == str(round_dir)
    assert artifacts["proof_split"]["workflow_replay"]["review_routes"]["overview"].endswith(
        "tab=overview"
    )
    assert artifacts["fresh_acpx_mission_e2e_report"]["mission_id"] == mission_id
    assert artifacts["workflow_acceptance_review"]["status"] == "pass"
    assert artifacts["round_summary"]["decision"]["action"] == "retry"


def test_build_fresh_exploratory_artifacts_tolerates_missing_prior_proof(tmp_path: Path) -> None:
    from spec_orch.services.fresh_acpx_e2e import build_fresh_exploratory_artifacts

    repo_root = tmp_path
    mission_id = "fresh-acpx-1"
    round_dir = repo_root / "docs" / "specs" / mission_id / "rounds" / "round-01"
    round_dir.mkdir(parents=True, exist_ok=True)
    (round_dir / "round_summary.json").write_text(
        json.dumps(
            {
                "round_id": 1,
                "status": "decided",
                "decision": {"action": "pass", "reason_code": "none"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    artifacts = build_fresh_exploratory_artifacts(
        repo_root=repo_root,
        mission_id=mission_id,
        round_dir=round_dir,
        mission_payload={"mission_id": mission_id, "acceptance_criteria": []},
        browser_evidence={"tested_routes": ["/"]},
    )

    assert artifacts["mission"]["mission_id"] == mission_id
    assert artifacts["browser_evidence"]["tested_routes"] == ["/"]
    assert "proof_split" not in artifacts
    assert "fresh_execution" not in artifacts
    assert "workflow_replay" not in artifacts
    assert artifacts["round_summary"]["decision"]["action"] == "pass"
