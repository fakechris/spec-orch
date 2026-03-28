from __future__ import annotations

from pathlib import Path

from spec_orch.domain.models import (
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
    )

    assert result.status == "pass"
    prompt = captured_prompt["text"]
    assert '"browser_evidence"' in prompt
    assert '"round_summary"' in prompt
    assert '"review_routes"' in prompt
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
  "tested_routes": ["/"],
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
    assert result.findings[0].summary == "Primary CTA missing"
    assert result.issue_proposals[0].title == "Restore home page CTA"


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
