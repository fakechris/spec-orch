from __future__ import annotations

from pathlib import Path

from spec_orch.domain.models import (
    AcceptanceCampaign,
    AcceptanceMode,
    AcceptanceReviewResult,
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


def test_acceptance_evaluator_prompt_includes_browser_evidence_and_routes(tmp_path: Path) -> None:
    from spec_orch.services.acceptance.litellm_acceptance_evaluator import (
        LiteLLMAcceptanceEvaluator,
    )

    captured_prompt: dict[str, str] = {}

    def fake_chat_completion(**kwargs):
        captured_prompt["text"] = kwargs["messages"][1]["content"]
        return """# Acceptance Review

Looks acceptable.

```json
{
  "status": "pass",
  "summary": "The run meets the intended result.",
  "confidence": 0.93,
  "evaluator": "acceptance_llm",
  "tested_routes": ["/", "/settings"],
  "findings": [],
  "issue_proposals": [],
  "artifacts": {"acceptance_review": "rounds/round-01/acceptance_review.json"}
}
```
"""

    adapter = LiteLLMAcceptanceEvaluator(
        repo_root=tmp_path,
        model="test/acceptance",
        chat_completion=fake_chat_completion,
    )

    result = adapter.evaluate_acceptance(
        mission_id="mission-1",
        round_id=1,
        round_dir=tmp_path / "docs/specs/mission-1/rounds/round-01",
        worker_results=[_worker_result(tmp_path)],
        artifacts={
            "mission": {"mission_id": "mission-1", "title": "Mission 1"},
            "round_summary": {"round_id": 1, "status": "reviewing"},
            "browser_evidence": {
                "tested_routes": ["/", "/settings"],
                "screenshots": {"/": "rounds/round-01/home.png"},
                "console_errors": [],
                "page_errors": [],
            },
            "review_routes": {
                "transcript": "/?mission=mission-1&tab=transcript",
                "visual_qa": "/?mission=mission-1&tab=visual-qa",
                "costs": "/?mission=mission-1&tab=costs",
            },
        },
        repo_root=tmp_path,
        campaign=AcceptanceCampaign(
            mode=AcceptanceMode.IMPACT_SWEEP,
            goal="Sweep launcher and transcript routes for regressions.",
            primary_routes=["/launcher"],
            related_routes=["/", "/?mission=mission-1&tab=transcript"],
            coverage_expectations=["launcher", "transcript"],
            filing_policy="auto_file_regressions_only",
            exploration_budget="medium",
        ),
    )

    assert result.status == "pass"
    prompt = captured_prompt["text"]
    assert "Mode: impact_sweep" in prompt
    assert '"browser_evidence"' in prompt
    assert '"round_summary"' in prompt
    assert '"review_routes"' in prompt
    assert '"campaign"' in prompt
    assert "/?mission=mission-1&tab=transcript" in prompt


def test_acceptance_evaluator_parses_structured_result(tmp_path: Path) -> None:
    from spec_orch.services.acceptance.litellm_acceptance_evaluator import (
        LiteLLMAcceptanceEvaluator,
    )

    def fake_chat_completion(**kwargs):
        return """# Acceptance Review

Reject this run.

```json
{
  "status": "fail",
  "summary": "The home page is missing the primary CTA.",
  "confidence": 0.91,
  "evaluator": "acceptance_llm",
  "acceptance_mode": "impact_sweep",
  "coverage_status": "partial",
  "tested_routes": ["/"],
  "untested_expected_routes": ["/pricing"],
  "recommended_next_step": "Expand coverage to /pricing before filing copy-only issues.",
  "findings": [
    {
      "severity": "high",
      "summary": "Primary CTA missing",
      "route": "/"
    }
  ],
  "issue_proposals": [
    {
      "title": "Restore home page CTA",
      "summary": "Acceptance evaluator found no primary CTA in the hero section.",
      "severity": "high",
      "confidence": 0.91
    }
  ],
  "artifacts": {
    "home_screenshot": "rounds/round-01/home.png"
  },
  "campaign": {
    "mode": "impact_sweep",
    "goal": "Sweep homepage and pricing for launch regressions.",
    "primary_routes": ["/"],
    "related_routes": ["/pricing"],
    "coverage_expectations": ["homepage", "pricing"],
    "filing_policy": "auto_file_regressions_only",
    "exploration_budget": "medium"
  }
}
```
"""

    adapter = LiteLLMAcceptanceEvaluator(
        repo_root=tmp_path,
        model="test/acceptance",
        chat_completion=fake_chat_completion,
    )

    result = adapter.evaluate_acceptance(
        mission_id="mission-2",
        round_id=2,
        round_dir=tmp_path / "docs/specs/mission-2/rounds/round-02",
        worker_results=[_worker_result(tmp_path)],
        artifacts={"browser_evidence": {"tested_routes": ["/"]}},
        repo_root=tmp_path,
    )

    assert isinstance(result, AcceptanceReviewResult)
    assert result.status == "fail"
    assert result.acceptance_mode == "impact_sweep"
    assert result.coverage_status == "partial"
    assert result.untested_expected_routes == ["/pricing"]
    assert result.findings[0].summary == "Primary CTA missing"
    assert result.issue_proposals[0].title == "Restore home page CTA"
    assert result.campaign is not None
    assert result.campaign.mode is AcceptanceMode.IMPACT_SWEEP


def test_acceptance_evaluator_degrades_safely_on_parse_error(tmp_path: Path) -> None:
    from spec_orch.services.acceptance.litellm_acceptance_evaluator import (
        LiteLLMAcceptanceEvaluator,
    )

    def fake_chat_completion(**kwargs):
        return "not valid acceptance evaluator output"

    adapter = LiteLLMAcceptanceEvaluator(
        repo_root=tmp_path,
        model="test/acceptance",
        chat_completion=fake_chat_completion,
    )

    result = adapter.evaluate_acceptance(
        mission_id="mission-3",
        round_id=3,
        round_dir=tmp_path / "docs/specs/mission-3/rounds/round-03",
        worker_results=[_worker_result(tmp_path)],
        artifacts={},
        repo_root=tmp_path,
    )

    assert result.status == "warn"
    assert result.confidence == 0.0
    assert result.findings[0].summary == "Acceptance evaluator output could not be parsed."


def test_acceptance_evaluator_degrades_safely_on_empty_json_payload(tmp_path: Path) -> None:
    from spec_orch.services.acceptance.litellm_acceptance_evaluator import (
        LiteLLMAcceptanceEvaluator,
    )

    def fake_chat_completion(**kwargs):
        return """# Acceptance Review

```json
{}
```"""

    adapter = LiteLLMAcceptanceEvaluator(
        repo_root=tmp_path,
        model="test/acceptance",
        chat_completion=fake_chat_completion,
    )

    result = adapter.evaluate_acceptance(
        mission_id="mission-4",
        round_id=4,
        round_dir=tmp_path / "docs/specs/mission-4/rounds/round-04",
        worker_results=[_worker_result(tmp_path)],
        artifacts={},
        repo_root=tmp_path,
    )

    assert result.status == "warn"
    assert result.findings[0].summary == "Acceptance evaluator output could not be parsed."


def test_acceptance_evaluator_normalizes_model_and_falls_back_to_minimax_envs(
    tmp_path: Path, monkeypatch
) -> None:
    from spec_orch.services.acceptance.litellm_acceptance_evaluator import (
        LiteLLMAcceptanceEvaluator,
    )

    captured_kwargs = {}

    def fake_chat_completion(**kwargs):
        captured_kwargs.update(kwargs)
        return """# Acceptance Review

```json
{
  "status": "pass",
  "summary": "Looks good.",
  "confidence": 0.9,
  "evaluator": "acceptance_llm",
  "tested_routes": ["/"],
  "findings": [],
  "issue_proposals": [],
  "artifacts": {}
}
```"""

    monkeypatch.delenv("SPEC_ORCH_LLM_API_KEY", raising=False)
    monkeypatch.delenv("SPEC_ORCH_LLM_API_BASE", raising=False)
    monkeypatch.setenv("MINIMAX_API_KEY", "sk-minimax")
    monkeypatch.setenv("MINIMAX_ANTHROPIC_BASE_URL", "https://api.minimaxi.com/anthropic")

    adapter = LiteLLMAcceptanceEvaluator(
        repo_root=tmp_path,
        model="MiniMax-M2.7-highspeed",
        api_type="anthropic",
        chat_completion=fake_chat_completion,
    )

    adapter.evaluate_acceptance(
        mission_id="mission-5",
        round_id=5,
        round_dir=tmp_path / "docs/specs/mission-5/rounds/round-05",
        worker_results=[_worker_result(tmp_path)],
        artifacts={},
        repo_root=tmp_path,
    )

    assert captured_kwargs["model"] == "anthropic/MiniMax-M2.7-highspeed"
    assert captured_kwargs["api_key"] == "sk-minimax"
    assert captured_kwargs["api_base"] == "https://api.minimaxi.com/anthropic"


def test_acceptance_evaluator_normalizes_low_signal_findings_and_issue_proposals(
    tmp_path: Path,
) -> None:
    from spec_orch.services.acceptance.litellm_acceptance_evaluator import (
        LiteLLMAcceptanceEvaluator,
    )

    def fake_chat_completion(**kwargs):
        return """# Acceptance Review

```json
{
  "status": "pass",
  "summary": "Workflow passed with one advisory.",
  "confidence": 0.92,
  "evaluator": "specorch-acceptance-evaluator",
  "tested_routes": ["/"],
  "findings": [
    {
      "severity": "advisory",
      "summary": "",
      "details": "",
      "expected": "",
      "actual": "",
      "route": "/"
    }
  ],
  "issue_proposals": [
    {
      "title": "",
      "summary": "",
      "severity": "medium",
      "confidence": 0.72,
      "expected": "",
      "actual": "",
      "route": "/"
    }
  ],
  "artifacts": {}
}
```"""

    adapter = LiteLLMAcceptanceEvaluator(
        repo_root=tmp_path,
        model="test/acceptance",
        chat_completion=fake_chat_completion,
    )

    result = adapter.evaluate_acceptance(
        mission_id="mission-6",
        round_id=6,
        round_dir=tmp_path / "docs/specs/mission-6/rounds/round-06",
        worker_results=[_worker_result(tmp_path)],
        artifacts={
            "browser_evidence": {
                "tested_routes": ["/"],
                "page_errors": [{"path": "/", "message": "Unexpected end of input"}],
                "console_errors": [],
                "interactions": {"/": []},
            }
        },
        repo_root=tmp_path,
    )

    finding = result.findings[0]
    proposal = result.issue_proposals[0]

    assert finding.summary == "Browser page error on /"
    assert "Unexpected end of input" in finding.details
    assert finding.actual == "Page error observed: Unexpected end of input"
    assert finding.expected == "Route should render without browser page errors."
    assert proposal.title == "Investigate browser page error on /"
    assert "Unexpected end of input" in proposal.summary
    assert proposal.actual == "Page error observed: Unexpected end of input"
    assert proposal.expected == "Route should render without browser page errors."


def test_acceptance_evaluator_drops_empty_shell_findings_without_supporting_evidence(
    tmp_path: Path,
) -> None:
    from spec_orch.services.acceptance.litellm_acceptance_evaluator import (
        LiteLLMAcceptanceEvaluator,
    )

    def fake_chat_completion(**kwargs):
        return """# Acceptance Review

```json
{
  "status": "pass",
  "summary": "Workflow passed.",
  "confidence": 0.95,
  "evaluator": "specorch-acceptance-evaluator",
  "tested_routes": ["/"],
  "findings": [
    {
      "severity": "info",
      "summary": "",
      "details": "",
      "expected": "",
      "actual": "",
      "route": "/"
    }
  ],
  "issue_proposals": [
    {
      "title": "",
      "summary": "",
      "severity": "low",
      "confidence": 0.3,
      "expected": "",
      "actual": "",
      "route": "/"
    }
  ],
  "artifacts": {}
}
```"""

    adapter = LiteLLMAcceptanceEvaluator(
        repo_root=tmp_path,
        model="test/acceptance",
        chat_completion=fake_chat_completion,
    )

    result = adapter.evaluate_acceptance(
        mission_id="mission-7",
        round_id=7,
        round_dir=tmp_path / "docs/specs/mission-7/rounds/round-07",
        worker_results=[_worker_result(tmp_path)],
        artifacts={"browser_evidence": {"tested_routes": ["/"], "page_errors": []}},
        repo_root=tmp_path,
    )

    assert result.findings == []
    assert result.issue_proposals == []


def test_acceptance_evaluator_normalization_handles_null_route_fields(tmp_path: Path) -> None:
    from spec_orch.services.acceptance.litellm_acceptance_evaluator import (
        LiteLLMAcceptanceEvaluator,
    )

    def fake_chat_completion(**kwargs):
        return """# Acceptance Review

```json
{
  "status": "warn",
  "summary": "Null route output.",
  "confidence": 0.5,
  "evaluator": "specorch-acceptance-evaluator",
  "tested_routes": ["/"],
  "findings": [
    {
      "severity": "advisory",
      "summary": "",
      "details": "",
      "expected": "",
      "actual": "",
      "route": null
    }
  ],
  "issue_proposals": [],
  "artifacts": {}
}
```"""

    adapter = LiteLLMAcceptanceEvaluator(
        repo_root=tmp_path,
        model="test/acceptance",
        chat_completion=fake_chat_completion,
    )

    result = adapter.evaluate_acceptance(
        mission_id="mission-8",
        round_id=8,
        round_dir=tmp_path / "docs/specs/mission-8/rounds/round-08",
        worker_results=[_worker_result(tmp_path)],
        artifacts={"browser_evidence": {"tested_routes": ["/"], "page_errors": []}},
        repo_root=tmp_path,
    )

    assert result.findings == []


def test_acceptance_system_prompt_includes_constitution() -> None:
    from spec_orch.services.acceptance.litellm_acceptance_evaluator import (
        _ACCEPTANCE_SYSTEM_PROMPT,
    )

    assert "## Constitution" in _ACCEPTANCE_SYSTEM_PROMPT
    assert (
        "Treat the implementation and mission framing as falsifiable." in _ACCEPTANCE_SYSTEM_PROMPT
    )
    assert "Be honest about missing coverage and uncertainty." in _ACCEPTANCE_SYSTEM_PROMPT
    assert "Do not inherit builder intent as proof of user value." in _ACCEPTANCE_SYSTEM_PROMPT
