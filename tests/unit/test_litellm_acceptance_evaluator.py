from __future__ import annotations

import json
import time
from pathlib import Path

from spec_orch.domain.models import (
    AcceptanceCampaign,
    AcceptanceFinding,
    AcceptanceIssueProposal,
    AcceptanceMode,
    AcceptanceReviewResult,
    BuilderResult,
    WorkPacket,
)
from spec_orch.runtime_chain.store import read_chain_events, read_chain_status


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
            functional_plan=["Validate the launcher route."],
            adversarial_plan=["Probe transcript navigation drift."],
            coverage_gaps=["Review costs tab only if evidence stays incomplete."],
            merged_plan=[
                "Validate the launcher route.",
                "Probe transcript navigation drift.",
                "Review costs tab only if evidence stays incomplete.",
            ],
        ),
    )

    assert result.status == "pass"
    prompt = captured_prompt["text"]
    assert "Mode: impact_sweep" in prompt
    assert '"browser_evidence"' in prompt
    assert '"round_summary"' in prompt
    assert '"review_routes"' in prompt
    assert '"campaign"' in prompt
    assert '"functional_plan"' in prompt
    assert '"adversarial_plan"' in prompt
    assert '"coverage_gaps"' in prompt
    assert '"merged_plan"' in prompt
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


def test_acceptance_evaluator_normalizes_lenient_doubao_style_payload(tmp_path: Path) -> None:
    from spec_orch.services.acceptance.litellm_acceptance_evaluator import (
        LiteLLMAcceptanceEvaluator,
    )

    def fake_chat_completion(**kwargs):
        return """### Acceptance Review
Transcript flow is usable, but transcript entry remains weak for operators.

```json
{
  "status": "conditional_accept",
  "summary": "Basic workflow validation complete; transcript entry weakness noted for resolution prior to full acceptance.",
  "confidence": "medium",
  "evaluator": "Transcript Workflow Validator",
  "tested_routes": ["/?tab=transcript"],
  "findings": ["Transcript entry is weak"],
  "issue_proposals": ["Clarify transcript entry point"],
  "artifacts": []
}
```"""

    adapter = LiteLLMAcceptanceEvaluator(
        repo_root=tmp_path,
        model="test/acceptance",
        chat_completion=fake_chat_completion,
    )

    result = adapter.evaluate_acceptance(
        mission_id="mission-doubao",
        round_id=1,
        round_dir=tmp_path / "docs/specs/mission-doubao/rounds/round-01",
        worker_results=[_worker_result(tmp_path)],
        artifacts={"browser_evidence": {"tested_routes": ["/?tab=transcript"], "page_errors": []}},
        repo_root=tmp_path,
    )

    assert result.status == "warn"
    assert result.confidence == 0.7
    assert result.findings
    assert result.findings[0].summary == "Transcript entry is weak"
    assert result.issue_proposals
    assert result.issue_proposals[0].title == "Clarify transcript entry point"
    assert result.artifacts == {
        "review_producer_role": "verifier",
        "verification_origin": "independent_verifier",
    }


def test_acceptance_evaluator_skips_unusable_primary_profile(tmp_path: Path) -> None:
    from spec_orch.services.acceptance.litellm_acceptance_evaluator import (
        LiteLLMAcceptanceEvaluator,
    )
    from spec_orch.services.litellm_profile import ResolvedLiteLLMProfile

    calls: list[str] = []

    def fake_chat_completion(**kwargs):
        calls.append(kwargs["model"])
        return """Review
```json
{"status":"pass","summary":"ok","confidence":0.9,"evaluator":"probe","findings":[],"issue_proposals":[],"artifacts":{}}
```"""

    adapter = LiteLLMAcceptanceEvaluator(
        repo_root=tmp_path,
        model="ignored",
        api_type="anthropic",
        model_chain=[
            ResolvedLiteLLMProfile(
                model="anthropic/MiniMax-M2.7-highspeed",
                api_type="anthropic",
                api_key="",
                api_base="",
                api_key_env="MINIMAX_API_KEY",
                api_base_env="MINIMAX_ANTHROPIC_BASE_URL",
                slot="primary",
            ),
            ResolvedLiteLLMProfile(
                model="anthropic/doubao-seed-2.0-code",
                api_type="anthropic",
                api_key="ok",
                api_base="https://ark.cn-beijing.volces.com/api/coding",
                api_key_env="ANTHROPIC_AUTH_TOKEN",
                api_base_env="ANTHROPIC_BASE_URL",
                slot="fallback-1",
            ),
        ],
        chat_completion=fake_chat_completion,
    )

    result = adapter.evaluate_acceptance(
        mission_id="mission-fallback",
        round_id=1,
        round_dir=tmp_path / "docs/specs/mission-fallback/rounds/round-01",
        worker_results=[_worker_result(tmp_path)],
        artifacts={},
        repo_root=tmp_path,
    )

    assert result.status == "pass"
    assert calls == ["anthropic/doubao-seed-2.0-code"]


def test_acceptance_evaluator_prefers_deterministic_campaign_and_browser_routes(
    tmp_path: Path,
) -> None:
    from spec_orch.services.acceptance.litellm_acceptance_evaluator import (
        LiteLLMAcceptanceEvaluator,
    )

    def fake_chat_completion(**kwargs):
        return """# Acceptance Review

```json
{
  "status": "fail",
  "summary": "Workflow replay was not executed.",
  "confidence": 0.3,
  "evaluator": "acceptance_llm",
  "acceptance_mode": "feature_scoped",
  "tested_routes": [],
  "findings": [],
  "issue_proposals": [],
  "artifacts": {},
  "campaign": {
    "mode": "feature_scoped",
    "goal": "Verify the declared feature and directly affected routes.",
    "primary_routes": ["/"],
    "related_routes": ["/transcript"]
  }
}
```"""

    adapter = LiteLLMAcceptanceEvaluator(
        repo_root=tmp_path,
        model="test/acceptance",
        chat_completion=fake_chat_completion,
    )
    supplied_campaign = AcceptanceCampaign(
        mode=AcceptanceMode.WORKFLOW,
        goal="Validate the post-run dashboard workflow for a fresh ACPX mission.",
        primary_routes=["/", "/?mode=missions"],
        related_routes=["/?mission=mission-9&mode=missions&tab=overview"],
        coverage_expectations=["launcher", "mission inventory", "mission detail"],
        filing_policy="auto_file_broken_flows_only",
        exploration_budget="bounded",
    )

    result = adapter.evaluate_acceptance(
        mission_id="mission-9",
        round_id=9,
        round_dir=tmp_path / "docs/specs/mission-9/rounds/round-09",
        worker_results=[_worker_result(tmp_path)],
        artifacts={
            "browser_evidence": {
                "tested_routes": [
                    "/",
                    "/?mode=missions",
                    "/?mission=mission-9&mode=missions&tab=overview",
                ],
                "page_errors": [],
            }
        },
        repo_root=tmp_path,
        campaign=supplied_campaign,
    )

    assert result.acceptance_mode == "workflow"
    assert result.tested_routes == [
        "/",
        "/?mode=missions",
        "/?mission=mission-9&mode=missions&tab=overview",
    ]
    assert result.coverage_status == "complete"
    assert result.campaign is not None
    assert result.campaign.mode is AcceptanceMode.WORKFLOW


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


def test_acceptance_evaluator_times_out_to_warn_fallback(tmp_path: Path) -> None:
    from spec_orch.services.acceptance.litellm_acceptance_evaluator import (
        LiteLLMAcceptanceEvaluator,
    )

    captured_kwargs = {}

    def fake_chat_completion(**kwargs):
        captured_kwargs.update(kwargs)
        raise TimeoutError("acceptance evaluator timed out")

    adapter = LiteLLMAcceptanceEvaluator(
        repo_root=tmp_path,
        model="test/acceptance",
        chat_completion=fake_chat_completion,
        request_timeout_seconds=9.0,
    )

    result = adapter.evaluate_acceptance(
        mission_id="mission-4b",
        round_id=4,
        round_dir=tmp_path / "docs/specs/mission-4b/rounds/round-04",
        worker_results=[_worker_result(tmp_path)],
        artifacts={},
        repo_root=tmp_path,
        chain_root=tmp_path / "docs/specs/mission-4b/operator/runtime_chain",
        chain_id="chain-mission-4b",
        span_id="span-round-04-acceptance",
        parent_span_id="span-round-04",
    )

    assert captured_kwargs["timeout"] == 9.0
    assert result.status == "warn"
    assert result.confidence == 0.0
    assert result.findings[0].summary == "Acceptance evaluator call failed."
    assert "timed out" in result.summary.lower()
    chain_root = tmp_path / "docs/specs/mission-4b/operator/runtime_chain"
    events = read_chain_events(chain_root)
    status = read_chain_status(chain_root)
    assert [event.phase.value for event in events] == ["started", "degraded"]
    assert status is not None
    assert status.phase.value == "degraded"


def test_acceptance_evaluator_retries_transient_overload_then_succeeds(tmp_path: Path) -> None:
    from spec_orch.services.acceptance.litellm_acceptance_evaluator import (
        LiteLLMAcceptanceEvaluator,
    )

    calls = {"count": 0}

    def fake_chat_completion(**kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("529 overloaded_error: provider busy")
        return """# Acceptance Review

```json
{
  "status": "pass",
  "summary": "Recovered after retry.",
  "confidence": 0.9,
  "evaluator": "acceptance_llm",
  "tested_routes": ["/"],
  "findings": [],
  "issue_proposals": [],
  "artifacts": {}
}
```"""

    adapter = LiteLLMAcceptanceEvaluator(
        repo_root=tmp_path,
        model="test/acceptance",
        chat_completion=fake_chat_completion,
        retry_backoff_seconds=0.0,
    )

    result = adapter.evaluate_acceptance(
        mission_id="mission-retry",
        round_id=1,
        round_dir=tmp_path / "docs/specs/mission-retry/rounds/round-01",
        worker_results=[_worker_result(tmp_path)],
        artifacts={},
        repo_root=tmp_path,
    )

    assert calls["count"] == 2
    assert result.status == "pass"
    assert result.summary == "Recovered after retry."


def test_acceptance_evaluator_does_not_retry_auth_errors(tmp_path: Path) -> None:
    from spec_orch.services.acceptance.litellm_acceptance_evaluator import (
        LiteLLMAcceptanceEvaluator,
    )

    calls = {"count": 0}

    def fake_chat_completion(**kwargs):
        calls["count"] += 1
        raise RuntimeError("authentication_error: invalid x-api-key")

    adapter = LiteLLMAcceptanceEvaluator(
        repo_root=tmp_path,
        model="test/acceptance",
        chat_completion=fake_chat_completion,
        retry_backoff_seconds=0.0,
    )

    result = adapter.evaluate_acceptance(
        mission_id="mission-auth",
        round_id=1,
        round_dir=tmp_path / "docs/specs/mission-auth/rounds/round-01",
        worker_results=[_worker_result(tmp_path)],
        artifacts={},
        repo_root=tmp_path,
    )

    assert calls["count"] == 1
    assert result.status == "warn"
    assert "invalid x-api-key" in result.summary


def test_acceptance_evaluator_falls_back_to_secondary_model_on_transient_overload(
    tmp_path: Path,
) -> None:
    from spec_orch.services.acceptance.litellm_acceptance_evaluator import (
        LiteLLMAcceptanceEvaluator,
    )
    from spec_orch.services.litellm_profile import ResolvedLiteLLMProfile

    seen_bases: list[str] = []

    def fake_chat_completion(**kwargs):
        seen_bases.append(str(kwargs.get("api_base") or ""))
        if kwargs.get("api_base") == "https://primary.example":
            raise RuntimeError("529 overloaded_error: primary unavailable")
        return """# Acceptance Review

```json
{
  "status": "pass",
  "summary": "Fallback model succeeded.",
  "confidence": 0.88,
  "evaluator": "acceptance_llm",
  "tested_routes": ["/"],
  "findings": [],
  "issue_proposals": [],
  "artifacts": {}
}
```"""

    adapter = LiteLLMAcceptanceEvaluator(
        repo_root=tmp_path,
        model="ignored",
        chat_completion=fake_chat_completion,
        retry_backoff_seconds=0.0,
        max_retries=0,
        model_chain=[
            ResolvedLiteLLMProfile(
                model="anthropic/MiniMax-M2.7-highspeed",
                api_type="anthropic",
                api_key="primary-key",
                api_base="https://primary.example",
                api_key_env="MINIMAX_API_KEY",
                api_base_env="MINIMAX_ANTHROPIC_BASE_URL",
                slot="primary",
            ),
            ResolvedLiteLLMProfile(
                model="anthropic/accounts/fireworks/routers/kimi-k2p5-turbo",
                api_type="anthropic",
                api_key="fallback-key",
                api_base="https://fallback.example",
                api_key_env="ANTHROPIC_AUTH_TOKEN",
                api_base_env="ANTHROPIC_BASE_URL",
                slot="fallback-1",
            ),
        ],
    )

    result = adapter.evaluate_acceptance(
        mission_id="mission-fallback",
        round_id=1,
        round_dir=tmp_path / "docs/specs/mission-fallback/rounds/round-01",
        worker_results=[_worker_result(tmp_path)],
        artifacts={},
        repo_root=tmp_path,
    )

    assert seen_bases == ["https://primary.example", "https://fallback.example"]
    assert result.status == "pass"
    assert result.summary == "Fallback model succeeded."


def test_acceptance_evaluator_emits_completed_runtime_chain_status(tmp_path: Path) -> None:
    from spec_orch.services.acceptance.litellm_acceptance_evaluator import (
        LiteLLMAcceptanceEvaluator,
    )

    def fake_chat_completion(**kwargs):
        return """# Acceptance Review

```json
{
  "status": "pass",
  "summary": "The run meets the intended result.",
  "confidence": 0.93,
  "evaluator": "acceptance_llm",
  "tested_routes": ["/"],
  "findings": [],
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
        mission_id="mission-4c",
        round_id=4,
        round_dir=tmp_path / "docs/specs/mission-4c/rounds/round-04",
        worker_results=[_worker_result(tmp_path)],
        artifacts={},
        repo_root=tmp_path,
        chain_root=tmp_path / "docs/specs/mission-4c/operator/runtime_chain",
        chain_id="chain-mission-4c",
        span_id="span-round-04-acceptance",
        parent_span_id="span-round-04",
    )

    chain_root = tmp_path / "docs/specs/mission-4c/operator/runtime_chain"
    events = read_chain_events(chain_root)
    status = read_chain_status(chain_root)

    assert result.status == "pass"
    assert [event.phase.value for event in events] == ["started", "completed"]
    assert status is not None
    assert status.subject_kind.value == "acceptance"
    assert status.phase.value == "completed"


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


def test_acceptance_evaluator_fallback_route_requires_single_unambiguous_route() -> None:
    from spec_orch.services.acceptance.litellm_acceptance_evaluator import (
        LiteLLMAcceptanceEvaluator,
    )

    result = AcceptanceReviewResult(
        status="warn",
        summary="review",
        confidence=0.5,
        evaluator="acceptance_llm",
        tested_routes=["/missions", "/approvals"],
        findings=[
            AcceptanceFinding(
                severity="medium",
                summary="",
                details="Operator observed ambiguous routes.",
                route="",
            )
        ],
        issue_proposals=[
            AcceptanceIssueProposal(
                title="",
                summary="Operator observed ambiguous routes.",
                severity="medium",
                confidence=0.5,
                route="",
            )
        ],
    )

    normalized = LiteLLMAcceptanceEvaluator._normalize_result(
        result,
        artifacts={
            "browser_evidence": {
                "tested_routes": ["/missions", "/approvals"],
                "page_errors": [
                    {"path": "/missions", "message": "boom"},
                    {"path": "/approvals", "message": "pow"},
                ],
            }
        },
    )

    assert normalized.findings
    assert normalized.issue_proposals
    assert normalized.findings[0].route == ""
    assert normalized.issue_proposals[0].route == ""
    assert normalized.findings[0].summary == "Acceptance finding on tested route"
    assert normalized.findings[0].actual == ""
    assert normalized.issue_proposals[0].title == "Investigate acceptance issue on tested route"


def test_normalize_acceptance_judgments_maps_held_candidate_into_candidate_finding() -> None:
    from spec_orch.acceptance_core.models import AcceptanceJudgmentClass
    from spec_orch.services.acceptance.litellm_acceptance_evaluator import (
        normalize_acceptance_judgments,
    )

    result = AcceptanceReviewResult(
        status="warn",
        summary="Exploratory review found a credible UX concern.",
        confidence=0.62,
        evaluator="acceptance_llm",
        acceptance_mode="exploratory",
        issue_proposals=[
            AcceptanceIssueProposal(
                title="Clarify transcript entry point",
                summary="Transcript entry point is credible but should not auto-file yet.",
                severity="medium",
                route="/?mission=demo&mode=missions&tab=transcript",
                hold_reason="Needs operator review before filing.",
                confidence=0.62,
            )
        ],
    )

    judgments = normalize_acceptance_judgments(result)

    assert len(judgments) == 1
    assert judgments[0].judgment_class is AcceptanceJudgmentClass.CANDIDATE_FINDING


def test_acceptance_evaluator_carries_proof_split_artifacts_forward(tmp_path: Path) -> None:
    from spec_orch.services.acceptance.litellm_acceptance_evaluator import (
        LiteLLMAcceptanceEvaluator,
    )

    def fake_chat_completion(**kwargs):
        return """# Acceptance Review

```json
{
  "status": "pass",
  "summary": "Fresh mission replay completed.",
  "confidence": 0.91,
  "evaluator": "acceptance_llm",
  "tested_routes": ["/"],
  "findings": [],
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
        mission_id="mission-9",
        round_id=9,
        round_dir=tmp_path / "docs/specs/mission-9/rounds/round-09",
        worker_results=[_worker_result(tmp_path)],
        artifacts={
            "proof_split": {
                "fresh_execution": {"proof_type": "fresh_execution"},
                "workflow_replay": {"proof_type": "workflow_replay"},
            }
        },
        repo_root=tmp_path,
    )

    assert result.artifacts["proof_split"]["fresh_execution"]["proof_type"] == "fresh_execution"
    assert result.artifacts["proof_split"]["workflow_replay"]["proof_type"] == "workflow_replay"


def test_acceptance_evaluator_normalizes_non_mapping_artifacts(tmp_path: Path) -> None:
    from spec_orch.services.acceptance.litellm_acceptance_evaluator import (
        LiteLLMAcceptanceEvaluator,
    )

    result = AcceptanceReviewResult(
        status="pass",
        summary="ok",
        confidence=0.9,
        evaluator="acceptance_llm",
        tested_routes=["/"],
        findings=[],
        issue_proposals=[],
        artifacts="not-a-dict",  # type: ignore[arg-type]
    )

    normalized = LiteLLMAcceptanceEvaluator._normalize_result(
        result,
        artifacts={"proof_split": {"fresh_execution": {"proof_type": "fresh_execution"}}},
    )

    assert normalized.artifacts["proof_split"]["fresh_execution"]["proof_type"] == "fresh_execution"


def test_acceptance_evaluator_synthesizes_exploratory_transcript_hold_candidate(
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
  "summary": "All exploratory routes rendered without blocking browser errors.",
  "confidence": 0.88,
  "evaluator": "acceptance_llm",
  "tested_routes": [
    "/",
    "/?mission=mission-1&mode=missions&tab=transcript"
  ],
  "findings": [],
  "issue_proposals": [],
  "artifacts": {}
}
```"""

    adapter = LiteLLMAcceptanceEvaluator(
        repo_root=tmp_path,
        model="test/acceptance",
        chat_completion=fake_chat_completion,
    )

    campaign = AcceptanceCampaign(
        mode=AcceptanceMode.EXPLORATORY,
        goal="Dogfood transcript discoverability from an operator perspective.",
        primary_routes=["/"],
        related_routes=["/?mission=mission-1&mode=missions&tab=transcript"],
        filing_policy="hold_ux_concerns_for_operator_review",
        exploration_budget="wide",
    )

    result = adapter.evaluate_acceptance(
        mission_id="mission-1",
        round_id=1,
        round_dir=tmp_path / "docs/specs/mission-1/rounds/round-01",
        worker_results=[_worker_result(tmp_path)],
        artifacts={
            "browser_evidence": {
                "tested_routes": [
                    "/",
                    "/?mission=mission-1&mode=missions&tab=transcript",
                ],
                "interactions": {
                    "/?mission=mission-1&mode=missions&tab=transcript": [
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
                            "status": "failed",
                            "message": "wait_for_selector failed: strict mode violation",
                        },
                    ],
                },
                "page_errors": [],
                "console_errors": [],
            }
        },
        repo_root=tmp_path,
        campaign=campaign,
    )

    assert result.status == "warn"
    assert result.findings
    assert result.issue_proposals
    assert "Transcript evidence entry is hard to discover" in result.findings[0].summary
    assert result.findings[0].route == "/?mission=mission-1&mode=missions&tab=transcript"
    assert result.findings[0].critique_axis == "evidence_discoverability"
    assert result.findings[0].operator_task == "open packet-level transcript evidence"
    assert "Operators can stall" in result.findings[0].why_it_matters
    assert result.issue_proposals[0].critique_axis == "evidence_discoverability"
    assert result.issue_proposals[0].hold_reason
    assert "empty-state" in result.issue_proposals[0].summary


def test_acceptance_evaluator_replaces_low_signal_exploratory_transcript_gap_output(
    tmp_path: Path,
) -> None:
    from spec_orch.services.acceptance.litellm_acceptance_evaluator import (
        LiteLLMAcceptanceEvaluator,
    )

    def fake_chat_completion(**kwargs):
        return """# Acceptance Review

```json
{
  "status": "fail",
  "summary": "Transcript tab renders zero packet rows.",
  "confidence": 0.9,
  "evaluator": "acceptance_llm",
  "tested_routes": [
    "/",
    "/?mission=mission-1&mode=missions&tab=transcript"
  ],
  "findings": [
    {
      "severity": "informational",
      "summary": "Browser page error on /?mission=mission-1&mode=missions&tab=transcript",
      "details": "wait_for_selector '[data-automation-target=\\\"transcript-block\\\"]' failed",
      "expected": "Route should render without browser page errors.",
      "actual": "Page error observed",
      "route": "/?mission=mission-1&mode=missions&tab=transcript"
    }
  ],
  "issue_proposals": [
    {
      "title": "Transcript tab renders no packet rows for mission mission-1",
      "summary": "Transcript tab renders no packet rows for mission mission-1",
      "severity": "",
      "confidence": 0.0,
      "repro_steps": [],
      "expected": "",
      "actual": "",
      "route": "",
      "artifact_paths": {}
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

    campaign = AcceptanceCampaign(
        mode=AcceptanceMode.EXPLORATORY,
        goal="Dogfood transcript discoverability from an operator perspective.",
        primary_routes=["/"],
        related_routes=["/?mission=mission-1&mode=missions&tab=transcript"],
        filing_policy="hold_ux_concerns_for_operator_review",
        exploration_budget="wide",
    )

    result = adapter.evaluate_acceptance(
        mission_id="mission-1",
        round_id=1,
        round_dir=tmp_path / "docs/specs/mission-1/rounds/round-01",
        worker_results=[_worker_result(tmp_path)],
        artifacts={
            "browser_evidence": {
                "tested_routes": [
                    "/",
                    "/?mission=mission-1&mode=missions&tab=transcript",
                ],
                "interactions": {
                    "/?mission=mission-1&mode=missions&tab=transcript": [
                        {
                            "action": "click_selector",
                            "target": '[data-automation-target="transcript-filter"][data-filter-key="all"]',
                            "status": "passed",
                        },
                        {
                            "action": "wait_for_selector",
                            "target": '[data-automation-target="transcript-block"]',
                            "status": "failed",
                            "message": "wait_for_selector failed: timeout",
                        },
                    ],
                },
                "page_errors": [
                    {
                        "path": "/?mission=mission-1&mode=missions&tab=transcript",
                        "message": "wait_for_selector '[data-automation-target=\"transcript-block\"]' failed",
                    }
                ],
                "console_errors": [],
            }
        },
        repo_root=tmp_path,
        campaign=campaign,
    )

    assert result.status == "warn"
    assert "packet selection is not self-evident" in result.summary
    assert len(result.findings) == 1
    assert result.findings[0].severity == "high"
    assert result.findings[0].route == "/?mission=mission-1&mode=missions&tab=transcript"
    assert result.findings[0].critique_axis == "evidence_discoverability"
    assert "first-time operator" in result.findings[0].expected
    assert len(result.issue_proposals) == 1
    assert result.issue_proposals[0].route == "/?mission=mission-1&mode=missions&tab=transcript"
    assert result.issue_proposals[0].hold_reason
    assert "empty-state" in result.issue_proposals[0].summary


def test_acceptance_evaluator_treats_transcript_block_access_as_successful_depth(
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
  "summary": "Transcript route is usable.",
  "confidence": 0.88,
  "evaluator": "acceptance_llm",
  "tested_routes": [
    "/",
    "/?mission=mission-1&mode=missions&tab=transcript"
  ],
  "findings": [],
  "issue_proposals": [],
  "artifacts": {}
}
```"""

    adapter = LiteLLMAcceptanceEvaluator(
        repo_root=tmp_path,
        model="test/acceptance",
        chat_completion=fake_chat_completion,
    )

    campaign = AcceptanceCampaign(
        mode=AcceptanceMode.EXPLORATORY,
        goal="Dogfood transcript discoverability from an operator perspective.",
        primary_routes=["/"],
        related_routes=["/?mission=mission-1&mode=missions&tab=transcript"],
        filing_policy="hold_ux_concerns_for_operator_review",
        exploration_budget="wide",
    )

    result = adapter.evaluate_acceptance(
        mission_id="mission-1",
        round_id=1,
        round_dir=tmp_path / "docs/specs/mission-1/rounds/round-01",
        worker_results=[_worker_result(tmp_path)],
        artifacts={
            "browser_evidence": {
                "tested_routes": [
                    "/",
                    "/?mission=mission-1&mode=missions&tab=transcript",
                ],
                "interactions": {
                    "/?mission=mission-1&mode=missions&tab=transcript": [
                        {
                            "action": "click_selector",
                            "target": '[data-automation-target="transcript-filter"][data-filter-key="all"]',
                            "status": "passed",
                        },
                        {
                            "action": "wait_for_selector",
                            "target": '[data-automation-target="transcript-block"]',
                            "status": "passed",
                        },
                        {
                            "action": "click_selector",
                            "target": '[data-automation-target="transcript-block"]',
                            "status": "passed",
                        },
                    ],
                },
                "page_errors": [],
                "console_errors": [],
            }
        },
        repo_root=tmp_path,
        campaign=campaign,
    )

    assert result.status == "pass"
    assert result.findings == []
    assert result.issue_proposals == []


def test_acceptance_evaluator_drops_coverage_only_exploratory_proposals_for_untested_routes(
    tmp_path: Path,
) -> None:
    from spec_orch.services.acceptance.litellm_acceptance_evaluator import (
        LiteLLMAcceptanceEvaluator,
    )

    def fake_chat_completion(**kwargs):
        return """# Acceptance Review

```json
{
  "status": "warn",
  "summary": "Transcript surface reveals one useful operator issue.",
  "confidence": 0.86,
  "evaluator": "acceptance_llm",
  "tested_routes": [
    "/",
    "/?mission=mission-3&mode=missions&tab=transcript"
  ],
  "findings": [
    {
      "severity": "operator_experience",
      "summary": "Transcript evidence entry is hard to discover",
      "details": "Operators can reach transcript filters but not deeper evidence.",
      "expected": "A first-time operator can move into packet-level evidence.",
      "actual": "The bounded replay stops at transcript controls.",
      "route": "/?mission=mission-3&mode=missions&tab=transcript",
      "critique_axis": "evidence_discoverability",
      "operator_task": "open packet-level transcript evidence",
      "why_it_matters": "Operators can stall before reaching mission evidence."
    }
  ],
  "issue_proposals": [
    {
      "title": "Clarify transcript packet selection entry point",
      "summary": "Operators need a clearer affordance for packet-level transcript evidence.",
      "severity": "high",
      "confidence": 0.86,
      "route": "/?mission=mission-3&mode=missions&tab=transcript",
      "critique_axis": "evidence_discoverability",
      "operator_task": "open packet-level transcript evidence",
      "why_it_matters": "Operators should reach evidence without prior context.",
      "hold_reason": "Exploratory UX critique should be reviewed before automatic filing."
    },
    {
      "title": "Approvals tab operator affordances not validated in this round",
      "summary": "Approvals tab operator affordances not validated in this round",
      "severity": "",
      "confidence": 0.0,
      "route": "/?mission=mission-3&mode=missions&tab=approvals"
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

    campaign = AcceptanceCampaign(
        mode=AcceptanceMode.EXPLORATORY,
        goal="Dogfood transcript discoverability from an operator perspective.",
        primary_routes=["/", "/?mission=mission-3&mode=missions&tab=transcript"],
        related_routes=["/?mission=mission-3&mode=missions&tab=approvals"],
        filing_policy="hold_ux_concerns_for_operator_review",
        exploration_budget="wide",
    )

    result = adapter.evaluate_acceptance(
        mission_id="mission-3",
        round_id=1,
        round_dir=tmp_path / "docs/specs/mission-3/rounds/round-01",
        worker_results=[_worker_result(tmp_path)],
        artifacts={
            "browser_evidence": {
                "tested_routes": [
                    "/",
                    "/?mission=mission-3&mode=missions&tab=transcript",
                ],
                "interactions": {
                    "/?mission=mission-3&mode=missions&tab=transcript": [
                        {
                            "action": "click_selector",
                            "target": '[data-automation-target="transcript-filter"][data-filter-key="all"]',
                            "status": "passed",
                        }
                    ]
                },
                "page_errors": [],
                "console_errors": [],
            }
        },
        repo_root=tmp_path,
        campaign=campaign,
    )

    assert len(result.issue_proposals) == 1
    assert result.issue_proposals[0].route == "/?mission=mission-3&mode=missions&tab=transcript"
    assert "Approvals tab operator affordances not validated" not in result.issue_proposals[0].title


def test_acceptance_evaluator_replaces_generic_browser_error_proposal_on_transcript_gap(
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
  "summary": "Transcript interaction failed once.",
  "confidence": 0.7,
  "evaluator": "acceptance_llm",
  "tested_routes": [
    "/",
    "/?mission=mission-1&mode=missions&tab=transcript"
  ],
  "findings": [
    {
      "severity": "blocking",
      "summary": "Browser page error on /?mission=mission-1&mode=missions&tab=transcript",
      "details": "wait_for_selector '[data-automation-target=\\\"transcript-block\\\"]' failed",
      "expected": "Route should render without browser page errors.",
      "actual": "Page error observed: click_selector failed",
      "route": "/?mission=mission-1&mode=missions&tab=transcript"
    }
  ],
  "issue_proposals": [
    {
      "title": "Investigate browser page error on /?mission=mission-1&mode=missions&tab=transcript",
      "summary": "Browser evidence recorded a page error on transcript.",
      "severity": "",
      "confidence": 0.0,
      "repro_steps": [],
      "expected": "Route should render without browser page errors.",
      "actual": "Page error observed",
      "route": "/?mission=mission-1&mode=missions&tab=transcript",
      "artifact_paths": {}
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

    campaign = AcceptanceCampaign(
        mode=AcceptanceMode.EXPLORATORY,
        goal="Dogfood transcript discoverability from an operator perspective.",
        primary_routes=["/"],
        related_routes=["/?mission=mission-1&mode=missions&tab=transcript"],
        filing_policy="hold_ux_concerns_for_operator_review",
        exploration_budget="wide",
    )

    result = adapter.evaluate_acceptance(
        mission_id="mission-1",
        round_id=1,
        round_dir=tmp_path / "docs/specs/mission-1/rounds/round-01",
        worker_results=[_worker_result(tmp_path)],
        artifacts={
            "browser_evidence": {
                "tested_routes": [
                    "/",
                    "/?mission=mission-1&mode=missions&tab=transcript",
                ],
                "interactions": {
                    "/?mission=mission-1&mode=missions&tab=transcript": [
                        {
                            "action": "click_selector",
                            "target": '[data-automation-target="transcript-filter"][data-filter-key="all"]',
                            "status": "passed",
                        },
                        {
                            "action": "wait_for_selector",
                            "target": '[data-automation-target="transcript-block"]',
                            "status": "failed",
                            "message": "wait_for_selector failed: timeout",
                        },
                    ],
                },
                "page_errors": [
                    {
                        "path": "/?mission=mission-1&mode=missions&tab=transcript",
                        "message": "wait_for_selector '[data-automation-target=\"transcript-block\"]' failed",
                    }
                ],
                "console_errors": [],
            }
        },
        repo_root=tmp_path,
        campaign=campaign,
    )

    assert result.status == "warn"
    assert len(result.findings) == 1
    assert result.findings[0].severity == "high"
    assert len(result.issue_proposals) == 1
    assert result.issue_proposals[0].title == "Clarify transcript packet selection entry point"
    assert result.issue_proposals[0].critique_axis == "evidence_discoverability"
    assert result.issue_proposals[0].hold_reason


def test_acceptance_evaluator_explains_zero_finding_exploratory_runs_when_evidence_is_thin(
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
  "summary": "The exploratory pass completed without blocking failures.",
  "confidence": 0.8,
  "evaluator": "acceptance_llm",
  "tested_routes": [
    "/",
    "/?mission=mission-2&mode=missions&tab=transcript"
  ],
  "findings": [],
  "issue_proposals": [],
  "artifacts": {}
}
```"""

    adapter = LiteLLMAcceptanceEvaluator(
        repo_root=tmp_path,
        model="test/acceptance",
        chat_completion=fake_chat_completion,
    )

    campaign = AcceptanceCampaign(
        mode=AcceptanceMode.EXPLORATORY,
        goal="Dogfood transcript discoverability from an operator perspective.",
        primary_routes=["/"],
        related_routes=["/?mission=mission-2&mode=missions&tab=transcript"],
        filing_policy="hold_ux_concerns_for_operator_review",
        exploration_budget="wide",
    )

    result = adapter.evaluate_acceptance(
        mission_id="mission-2",
        round_id=1,
        round_dir=tmp_path / "docs/specs/mission-2/rounds/round-01",
        worker_results=[_worker_result(tmp_path)],
        artifacts={
            "browser_evidence": {
                "tested_routes": [
                    "/",
                    "/?mission=mission-2&mode=missions&tab=transcript",
                ],
                "interactions": {
                    "/?mission=mission-2&mode=missions&tab=transcript": [
                        {
                            "action": "click_selector",
                            "target": '[data-automation-target="transcript-filter"][data-filter-key="all"]',
                            "status": "failed",
                            "message": "click_selector failed: timeout",
                        }
                    ]
                },
                "page_errors": [],
                "console_errors": [],
            }
        },
        repo_root=tmp_path,
        campaign=campaign,
    )

    assert result.findings == []
    assert result.issue_proposals == []
    assert "did not clear the critique threshold" in result.summary.lower()
    assert result.recommended_next_step


def test_acceptance_evaluator_rewrites_transcript_empty_surface_into_operator_critique(
    tmp_path: Path,
) -> None:
    from spec_orch.services.acceptance.litellm_acceptance_evaluator import (
        LiteLLMAcceptanceEvaluator,
    )

    def fake_chat_completion(**kwargs):
        return """# Acceptance Review

```json
{
  "status": "warn",
  "summary": "Surface navigation is functional across 5 of 6 routes. The transcript surface failed to render packet rows for a completed round, blocking deeper evidence inspection.",
  "confidence": 0.84,
  "evaluator": "acceptance_llm",
  "tested_routes": [
    "/",
    "/?mission=operator-console-dogfood-smoke&mode=missions&tab=transcript&round=1"
  ],
  "findings": [
    {
      "severity": "material",
      "summary": "Browser page error on /?mission=operator-console-dogfood-smoke&mode=missions&tab=transcript&round=1",
      "details": "Browser evidence recorded a page error.",
      "expected": "Route should render without browser page errors.",
      "actual": "Page error observed",
      "route": "/?mission=operator-console-dogfood-smoke&mode=missions&tab=transcript&round=1"
    }
  ],
  "issue_proposals": [
    {
      "title": "Transcript surface empty for completed round",
      "summary": "Browser evidence recorded a page error on transcript.",
      "severity": "",
      "confidence": 0.0,
      "repro_steps": [],
      "expected": "Route should render without browser page errors.",
      "actual": "Page error observed",
      "route": "/?mission=operator-console-dogfood-smoke&mode=missions&tab=transcript&round=1",
      "artifact_paths": {}
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

    campaign = AcceptanceCampaign(
        mode=AcceptanceMode.EXPLORATORY,
        goal="Dogfood transcript discoverability from an operator perspective.",
        primary_routes=["/"],
        related_routes=[
            "/?mission=operator-console-dogfood-smoke&mode=missions&tab=transcript&round=1"
        ],
        filing_policy="hold_ux_concerns_for_operator_review",
        exploration_budget="wide",
    )

    result = adapter.evaluate_acceptance(
        mission_id="operator-console-dogfood-smoke",
        round_id=1,
        round_dir=tmp_path / "docs/specs/operator-console-dogfood-smoke/rounds/round-01",
        worker_results=[_worker_result(tmp_path)],
        artifacts={
            "browser_evidence": {
                "tested_routes": [
                    "/",
                    "/?mission=operator-console-dogfood-smoke&mode=missions&tab=transcript&round=1",
                ],
                "interactions": {
                    "/?mission=operator-console-dogfood-smoke&mode=missions&tab=transcript&round=1": [
                        {
                            "action": "click_selector",
                            "target": '[data-automation-target="transcript-filter"][data-filter-key="all"]',
                            "status": "passed",
                        },
                        {
                            "action": "wait_for_selector",
                            "target": '[data-automation-target="transcript-block"]',
                            "status": "failed",
                            "message": "wait_for_selector failed: timeout",
                        },
                    ]
                },
                "page_errors": [
                    {
                        "path": "/?mission=operator-console-dogfood-smoke&mode=missions&tab=transcript&round=1",
                        "message": "wait_for_selector '[data-automation-target=\"transcript-block\"]' failed",
                    }
                ],
                "console_errors": [],
            }
        },
        repo_root=tmp_path,
        campaign=campaign,
    )

    assert result.findings[0].critique_axis == "evidence_discoverability"
    assert result.issue_proposals[0].critique_axis == "evidence_discoverability"
    assert result.issue_proposals[0].hold_reason


def test_acceptance_evaluator_rewrites_retry_backed_transcript_empty_state_into_task_continuity_critique(
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
  "summary": "Dashboard infrastructure is navigable and functional. All six routes load, tab switching works, launcher opens, and internal route affordances resolve. The transcript tab shows an empty state consistent with the mission's round-1 retry decision (contracts_not_defined). No blocking defects found. One held UX concern: the empty transcript state does not signal its cause to the operator.",
  "confidence": 0.85,
  "evaluator": "operator-console-dogfood-smoke/exploratory",
  "tested_routes": [
    "/",
    "/?mission=operator-console-dogfood-smoke&mode=missions&tab=transcript&round=1"
  ],
  "findings": [
    {
      "severity": "held",
      "summary": "Browser page error on /?mission=operator-console-dogfood-smoke&mode=missions&tab=transcript&round=1",
      "details": "Browser evidence recorded a page error on transcript.",
      "expected": "Route should render without browser page errors.",
      "actual": "Page error observed",
      "route": "/?mission=operator-console-dogfood-smoke&mode=missions&tab=transcript&round=1"
    }
  ],
  "issue_proposals": [
    {
      "title": "Transcript empty state should signal cause to operator",
      "summary": "Browser evidence recorded a page error on transcript.",
      "severity": "",
      "confidence": 0.0,
      "repro_steps": [],
      "expected": "Route should render without browser page errors.",
      "actual": "Page error observed",
      "route": "/?mission=operator-console-dogfood-smoke&mode=missions&tab=transcript&round=1",
      "artifact_paths": {}
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

    campaign = AcceptanceCampaign(
        mode=AcceptanceMode.EXPLORATORY,
        goal="Dogfood transcript empty-state continuity from an operator perspective.",
        primary_routes=["/"],
        related_routes=[
            "/?mission=operator-console-dogfood-smoke&mode=missions&tab=transcript&round=1"
        ],
        filing_policy="hold_ux_concerns_for_operator_review",
        exploration_budget="wide",
    )

    result = adapter.evaluate_acceptance(
        mission_id="operator-console-dogfood-smoke",
        round_id=1,
        round_dir=tmp_path / "docs/specs/operator-console-dogfood-smoke/rounds/round-01",
        worker_results=[_worker_result(tmp_path)],
        artifacts={
            "round_summary": {
                "round_id": 7,
                "status": "decided",
                "decision": {
                    "action": "retry",
                    "reason_code": "contracts_not_defined",
                },
            },
            "browser_evidence": {
                "tested_routes": [
                    "/",
                    "/?mission=operator-console-dogfood-smoke&mode=missions&tab=transcript&round=1",
                ],
                "interactions": {
                    "/?mission=operator-console-dogfood-smoke&mode=missions&tab=transcript&round=1": [
                        {
                            "action": "click_selector",
                            "target": '[data-automation-target="transcript-filter"][data-filter-key="all"]',
                            "status": "passed",
                        },
                        {
                            "action": "wait_for_selector",
                            "target": '[data-automation-target="transcript-block"]',
                            "status": "failed",
                            "message": "wait_for_selector failed: timeout",
                        },
                    ]
                },
                "page_errors": [
                    {
                        "path": "/?mission=operator-console-dogfood-smoke&mode=missions&tab=transcript&round=1",
                        "message": "wait_for_selector '[data-automation-target=\"transcript-block\"]' failed",
                    }
                ],
                "console_errors": [],
            },
        },
        repo_root=tmp_path,
        campaign=campaign,
    )

    assert result.status == "warn"
    assert "round 7 was retried for contracts_not_defined" in result.summary
    assert result.findings[0].summary == "Transcript empty state hides the retry cause"
    assert result.findings[0].critique_axis == "task_continuity"
    assert "retry" in result.findings[0].details.lower()
    assert result.findings[0].operator_task == (
        "understand why transcript evidence is unavailable and what to review next"
    )
    assert result.issue_proposals[0].title == "Explain retry-backed transcript empty states"
    assert result.issue_proposals[0].critique_axis == "task_continuity"
    assert result.issue_proposals[0].hold_reason


def test_acceptance_evaluator_finds_transcript_route_from_interaction_keys(
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
  "summary": "The exploratory pass completed.",
  "confidence": 0.76,
  "evaluator": "acceptance_llm",
  "tested_routes": ["/"],
  "findings": [],
  "issue_proposals": [],
  "artifacts": {}
}
```"""

    adapter = LiteLLMAcceptanceEvaluator(
        repo_root=tmp_path,
        model="test/acceptance",
        chat_completion=fake_chat_completion,
    )

    campaign = AcceptanceCampaign(
        mode=AcceptanceMode.EXPLORATORY,
        goal="Dogfood transcript discoverability from an operator perspective.",
        primary_routes=["/"],
        related_routes=["/?mission=mission-3&mode=missions&tab=transcript"],
        filing_policy="hold_ux_concerns_for_operator_review",
        exploration_budget="wide",
    )

    result = adapter.evaluate_acceptance(
        mission_id="mission-3",
        round_id=1,
        round_dir=tmp_path / "docs/specs/mission-3/rounds/round-01",
        worker_results=[_worker_result(tmp_path)],
        artifacts={
            "browser_evidence": {
                "tested_routes": ["/"],
                "interactions": {
                    "/?mission=mission-3&mode=missions&tab=transcript": [
                        {
                            "action": "click_selector",
                            "target": '[data-automation-target="transcript-filter"][data-filter-key="all"]',
                            "status": "passed",
                        },
                        {
                            "action": "wait_for_selector",
                            "target": '[data-automation-target="transcript-block"]',
                            "status": "failed",
                            "message": "wait_for_selector failed: timeout",
                        },
                    ]
                },
                "page_errors": [],
                "console_errors": [],
            }
        },
        repo_root=tmp_path,
        campaign=campaign,
    )

    assert result.status == "warn"
    assert result.findings[0].route == "/?mission=mission-3&mode=missions&tab=transcript"
    assert result.findings[0].critique_axis == "evidence_discoverability"


def test_invoke_acceptance_graph_step_uses_supplied_step_prompts(tmp_path: Path) -> None:
    from spec_orch.services.acceptance.litellm_acceptance_evaluator import (
        LiteLLMAcceptanceEvaluator,
    )

    captured: dict[str, object] = {}

    def fake_chat_completion(**kwargs):
        captured["messages"] = kwargs["messages"]
        return (
            '{"decision":"continue","outputs":{},"next_transition":"",'
            '"warnings":[],"review_markdown":"## Step"}'
        )

    adapter = LiteLLMAcceptanceEvaluator(
        repo_root=tmp_path,
        model="test/acceptance",
        chat_completion=fake_chat_completion,
    )

    raw = adapter.invoke_acceptance_graph_step(
        system_prompt="STEP SYSTEM",
        user_prompt="STEP USER",
    )

    assert json.loads(raw)["decision"] == "continue"
    assert captured["messages"] == [
        {"role": "system", "content": "STEP SYSTEM"},
        {"role": "user", "content": "STEP USER"},
    ]


def test_invoke_acceptance_graph_step_hard_deadline_interrupts_stuck_model_call(
    tmp_path: Path,
) -> None:
    from spec_orch.services.acceptance.litellm_acceptance_evaluator import (
        LiteLLMAcceptanceEvaluator,
    )

    def fake_chat_completion(**kwargs):
        time.sleep(0.2)
        return '{"decision":"continue"}'

    adapter = LiteLLMAcceptanceEvaluator(
        repo_root=tmp_path,
        model="test/acceptance",
        chat_completion=fake_chat_completion,
        request_timeout_seconds=0.01,
    )

    try:
        adapter.invoke_acceptance_graph_step(
            system_prompt="STEP SYSTEM",
            user_prompt="STEP USER",
        )
    except TimeoutError:
        pass
    else:
        raise AssertionError("Expected acceptance graph step invoke to time out")
