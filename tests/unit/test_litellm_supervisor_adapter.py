from __future__ import annotations

import json
from pathlib import Path

from spec_orch.domain.models import (
    ExecutionPlan,
    RoundAction,
    RoundArtifacts,
    VisualEvaluationResult,
    Wave,
    WorkPacket,
)


def test_supervisor_adapter_parses_round_decision_from_model_output(tmp_path: Path) -> None:
    from spec_orch.services.litellm_supervisor_adapter import LiteLLMSupervisorAdapter

    def fake_chat_completion(**kwargs):
        return """# Review

Wave looks healthy. Continue to the next step.

```json
{
  "action": "continue",
  "reason_code": "all_green",
  "summary": "Wave completed successfully.",
  "confidence": 0.91
}
```
"""

    adapter = LiteLLMSupervisorAdapter(
        repo_root=tmp_path,
        model="test/model",
        chat_completion=fake_chat_completion,
    )
    decision = adapter.review_round(
        round_artifacts=RoundArtifacts(round_id=1, mission_id="mission-1"),
        plan=ExecutionPlan(plan_id="plan-1", mission_id="mission-1"),
        round_history=[],
        context={"note": "ctx"},
    )

    assert decision.action is RoundAction.CONTINUE
    assert decision.reason_code == "all_green"
    assert decision.summary == "Wave completed successfully."
    review_path = tmp_path / "docs/specs/mission-1/rounds/round-01/supervisor_review.md"
    decision_path = tmp_path / "docs/specs/mission-1/rounds/round-01/round_decision.json"
    assert review_path.exists()
    assert "Wave looks healthy" in review_path.read_text(encoding="utf-8")
    assert json.loads(decision_path.read_text(encoding="utf-8"))["action"] == "continue"


def test_supervisor_adapter_falls_back_to_ask_human_on_parse_error(tmp_path: Path) -> None:
    from spec_orch.services.litellm_supervisor_adapter import LiteLLMSupervisorAdapter

    def fake_chat_completion(**kwargs):
        return "this is not valid decision output"

    adapter = LiteLLMSupervisorAdapter(
        repo_root=tmp_path,
        model="test/model",
        chat_completion=fake_chat_completion,
    )
    decision = adapter.review_round(
        round_artifacts=RoundArtifacts(round_id=2, mission_id="mission-2"),
        plan=ExecutionPlan(plan_id="plan-2", mission_id="mission-2"),
        round_history=[],
        context=None,
    )

    assert decision.action is RoundAction.ASK_HUMAN
    assert decision.reason_code == "parse_error"
    decision_path = tmp_path / "docs/specs/mission-2/rounds/round-02/round_decision.json"
    saved = json.loads(decision_path.read_text(encoding="utf-8"))
    assert saved["action"] == "ask_human"


def test_supervisor_prompt_includes_visual_evaluation_and_wave_context(tmp_path: Path) -> None:
    from spec_orch.services.litellm_supervisor_adapter import LiteLLMSupervisorAdapter

    captured_prompt = {}

    def fake_chat_completion(**kwargs):
        captured_prompt["text"] = kwargs["messages"][1]["content"]
        return """# Review

Looks good.

```json
{
  "action": "stop",
  "reason_code": "done",
  "summary": "Mission is complete.",
  "confidence": 0.9
}
```
"""

    adapter = LiteLLMSupervisorAdapter(
        repo_root=tmp_path,
        model="test/model",
        chat_completion=fake_chat_completion,
    )
    decision = adapter.review_round(
        round_artifacts=RoundArtifacts(
            round_id=3,
            mission_id="mission-3",
            builder_reports=[{"packet_id": "pkt-1", "succeeded": True}],
            visual_evaluation=VisualEvaluationResult(
                evaluator="stub_visual",
                summary="Layout looks good.",
                confidence=0.88,
            ),
        ),
        plan=ExecutionPlan(
            plan_id="plan-3",
            mission_id="mission-3",
            waves=[
                Wave(
                    wave_number=0,
                    description="Wave 0",
                    work_packets=[WorkPacket(packet_id="pkt-1", title="Task 1")],
                )
            ],
        ),
        round_history=[],
        context={
            "mission": {"mission_id": "mission-3", "constraints": ["no schema changes"]},
            "wave": {"packet_ids": ["pkt-1"]},
        },
    )

    assert decision.action is RoundAction.STOP
    prompt = captured_prompt["text"]
    assert '"visual_evaluation"' in prompt
    assert "Layout looks good." in prompt
    assert '"packet_ids"' in prompt
    assert "no schema changes" in prompt


def test_supervisor_adapter_normalizes_model_and_falls_back_to_minimax_envs(
    tmp_path: Path, monkeypatch
) -> None:
    from spec_orch.services.litellm_supervisor_adapter import LiteLLMSupervisorAdapter

    captured_kwargs = {}

    def fake_chat_completion(**kwargs):
        captured_kwargs.update(kwargs)
        return """# Review

```json
{
  "action": "stop",
  "reason_code": "done",
  "summary": "Mission is complete.",
  "confidence": 0.9
}
```"""

    monkeypatch.delenv("SPEC_ORCH_LLM_API_KEY", raising=False)
    monkeypatch.delenv("SPEC_ORCH_LLM_API_BASE", raising=False)
    monkeypatch.setenv("MINIMAX_API_KEY", "sk-minimax")
    monkeypatch.setenv("MINIMAX_ANTHROPIC_BASE_URL", "https://api.minimaxi.com/anthropic")

    adapter = LiteLLMSupervisorAdapter(
        repo_root=tmp_path,
        model="MiniMax-M2.7-highspeed",
        api_type="anthropic",
        chat_completion=fake_chat_completion,
    )
    adapter.review_round(
        round_artifacts=RoundArtifacts(round_id=4, mission_id="mission-4"),
        plan=ExecutionPlan(plan_id="plan-4", mission_id="mission-4"),
        round_history=[],
        context=None,
    )

    assert captured_kwargs["model"] == "anthropic/MiniMax-M2.7-highspeed"
    assert captured_kwargs["api_key"] == "sk-minimax"
    assert captured_kwargs["api_base"] == "https://api.minimaxi.com/anthropic"
