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
from spec_orch.runtime_chain.store import read_chain_events, read_chain_status
from spec_orch.services.memory.service import MemoryService, reset_memory_service


def test_supervisor_adapter_parses_round_decision_from_model_output(tmp_path: Path) -> None:
    import spec_orch.services.memory.service as mem_mod
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

    reset_memory_service()
    svc = MemoryService(repo_root=tmp_path)
    mem_mod._instance = svc
    try:
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
    finally:
        reset_memory_service()

    assert decision.action is RoundAction.CONTINUE
    assert decision.reason_code == "all_green"
    assert decision.summary == "Wave completed successfully."
    review_path = tmp_path / "docs/specs/mission-1/rounds/round-01/supervisor_review.md"
    decision_path = tmp_path / "docs/specs/mission-1/rounds/round-01/round_decision.json"
    record_path = tmp_path / "docs/specs/mission-1/rounds/round-01/decision_record.json"
    assert review_path.exists()
    assert "Wave looks healthy" in review_path.read_text(encoding="utf-8")
    assert json.loads(decision_path.read_text(encoding="utf-8"))["action"] == "continue"
    assert json.loads(record_path.read_text(encoding="utf-8")) == {
        "record_id": "mission-1-round-1-review",
        "point_key": "mission.round.review",
        "authority": "llm_owned",
        "owner": "litellm_supervisor_adapter",
        "selected_action": "continue",
        "summary": "Wave completed successfully.",
        "rationale": "",
        "confidence": 0.91,
        "context_artifacts": [
            "docs/specs/mission-1/rounds/round-01/supervisor_review.md",
            "docs/specs/mission-1/rounds/round-01/round_decision.json",
        ],
        "blocking_questions": [],
        "created_at": json.loads(record_path.read_text(encoding="utf-8"))["created_at"],
    }
    memory_entry = svc.get("decision-record-mission-1-round-1-review")
    assert memory_entry is not None
    assert memory_entry.metadata["mission_id"] == "mission-1"
    assert memory_entry.metadata["round_id"] == 1
    assert memory_entry.metadata["provenance"] == "unreviewed"
    assert (
        memory_entry.created_at == json.loads(record_path.read_text(encoding="utf-8"))["created_at"]
    )


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
    record_path = tmp_path / "docs/specs/mission-2/rounds/round-02/decision_record.json"
    saved = json.loads(decision_path.read_text(encoding="utf-8"))
    assert saved["action"] == "ask_human"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["selected_action"] == "ask_human"
    assert record["blocking_questions"] == [
        "Review the supervisor output and decide the next action."
    ]


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


def test_supervisor_adapter_logs_memory_write_failures_without_breaking_review(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    import spec_orch.services.memory.service as mem_mod
    from spec_orch.services.litellm_supervisor_adapter import LiteLLMSupervisorAdapter

    class BrokenMemory:
        def record_decision_record(self, **kwargs):
            raise ValueError("boom")

    def fake_chat_completion(**kwargs):
        return """# Review

```json
{
  "action": "continue",
  "reason_code": "all_green",
  "summary": "Wave completed successfully.",
  "confidence": 0.91
}
```"""

    monkeypatch.setattr(mem_mod, "get_memory_service", lambda repo_root=None: BrokenMemory())

    adapter = LiteLLMSupervisorAdapter(
        repo_root=tmp_path,
        model="test/model",
        chat_completion=fake_chat_completion,
    )

    with caplog.at_level("WARNING"):
        decision = adapter.review_round(
            round_artifacts=RoundArtifacts(round_id=5, mission_id="mission-5"),
            plan=ExecutionPlan(plan_id="plan-5", mission_id="mission-5"),
            round_history=[],
            context=None,
        )

    assert decision.action is RoundAction.CONTINUE
    assert "decision record memory write failed" in caplog.text


def test_supervisor_adapter_emits_runtime_chain_heartbeat(tmp_path: Path) -> None:
    from spec_orch.services.litellm_supervisor_adapter import LiteLLMSupervisorAdapter

    def fake_chat_completion(**kwargs):
        return """# Review

```json
{
  "action": "continue",
  "reason_code": "all_green",
  "summary": "Wave completed successfully.",
  "confidence": 0.91
}
```"""

    adapter = LiteLLMSupervisorAdapter(
        repo_root=tmp_path,
        model="test/model",
        chat_completion=fake_chat_completion,
    )

    adapter.review_round(
        round_artifacts=RoundArtifacts(round_id=6, mission_id="mission-6"),
        plan=ExecutionPlan(plan_id="plan-6", mission_id="mission-6"),
        round_history=[],
        context=None,
        chain_root=tmp_path / "docs/specs/mission-6/operator/runtime_chain",
        chain_id="chain-mission-6",
        span_id="span-round-06-supervisor",
        parent_span_id="span-round-06",
    )

    chain_root = tmp_path / "docs/specs/mission-6/operator/runtime_chain"
    events = read_chain_events(chain_root)
    status = read_chain_status(chain_root)

    assert [event.phase.value for event in events] == ["started", "completed"]
    assert all(event.subject_kind.value == "supervisor" for event in events)
    assert status is not None
    assert status.subject_kind.value == "supervisor"
    assert status.phase.value == "completed"


def test_supervisor_adapter_emits_degraded_chain_status_on_model_fallback(tmp_path: Path) -> None:
    from spec_orch.services.litellm_supervisor_adapter import LiteLLMSupervisorAdapter

    def fake_chat_completion(**kwargs):
        raise TimeoutError("supervisor timed out")

    adapter = LiteLLMSupervisorAdapter(
        repo_root=tmp_path,
        model="test/model",
        chat_completion=fake_chat_completion,
    )

    decision = adapter.review_round(
        round_artifacts=RoundArtifacts(round_id=7, mission_id="mission-7"),
        plan=ExecutionPlan(plan_id="plan-7", mission_id="mission-7"),
        round_history=[],
        context=None,
        chain_root=tmp_path / "docs/specs/mission-7/operator/runtime_chain",
        chain_id="chain-mission-7",
        span_id="span-round-07-supervisor",
        parent_span_id="span-round-07",
    )

    chain_root = tmp_path / "docs/specs/mission-7/operator/runtime_chain"
    events = read_chain_events(chain_root)
    status = read_chain_status(chain_root)

    assert decision.action is RoundAction.ASK_HUMAN
    assert [event.phase.value for event in events] == ["started", "degraded"]
    assert status is not None
    assert status.phase.value == "degraded"


def test_supervisor_adapter_times_out_to_deterministic_continue_fallback(
    tmp_path: Path,
) -> None:
    from spec_orch.services.litellm_supervisor_adapter import LiteLLMSupervisorAdapter

    captured_kwargs = {}

    def fake_chat_completion(**kwargs):
        captured_kwargs.update(kwargs)
        raise TimeoutError("supervisor call timed out")

    adapter = LiteLLMSupervisorAdapter(
        repo_root=tmp_path,
        model="test/model",
        chat_completion=fake_chat_completion,
        request_timeout_seconds=12.5,
    )

    decision = adapter.review_round(
        round_artifacts=RoundArtifacts(
            round_id=6,
            mission_id="mission-6",
            builder_reports=[
                {"packet_id": "pkt-1", "succeeded": True},
                {"packet_id": "pkt-2", "succeeded": True},
            ],
            gate_verdicts=[
                {"packet_id": "pkt-1", "mergeable": True, "failed_conditions": []},
                {"packet_id": "pkt-2", "mergeable": True, "failed_conditions": []},
            ],
        ),
        plan=ExecutionPlan(plan_id="plan-6", mission_id="mission-6"),
        round_history=[],
        context=None,
    )

    assert captured_kwargs["timeout"] == 12.5
    assert decision.action is RoundAction.CONTINUE
    assert decision.reason_code == "supervisor_timeout_all_mergeable"
    assert "timed out" in decision.summary.lower()


def test_supervisor_adapter_times_out_to_retry_when_round_has_failed_packets(
    tmp_path: Path,
) -> None:
    from spec_orch.services.litellm_supervisor_adapter import LiteLLMSupervisorAdapter

    def fake_chat_completion(**kwargs):
        raise TimeoutError("supervisor call timed out")

    adapter = LiteLLMSupervisorAdapter(
        repo_root=tmp_path,
        model="test/model",
        chat_completion=fake_chat_completion,
        request_timeout_seconds=12.5,
    )

    decision = adapter.review_round(
        round_artifacts=RoundArtifacts(
            round_id=7,
            mission_id="mission-7",
            builder_reports=[
                {"packet_id": "pkt-1", "succeeded": False},
                {"packet_id": "pkt-2", "succeeded": True},
            ],
            gate_verdicts=[
                {
                    "packet_id": "pkt-1",
                    "mergeable": False,
                    "failed_conditions": ["verification"],
                },
                {"packet_id": "pkt-2", "mergeable": True, "failed_conditions": []},
            ],
        ),
        plan=ExecutionPlan(plan_id="plan-7", mission_id="mission-7"),
        round_history=[],
        context=None,
    )

    assert decision.action is RoundAction.RETRY
    assert decision.reason_code == "supervisor_timeout_round_needs_retry"
    assert "timed out" in decision.summary.lower()


def test_supervisor_system_prompt_includes_constitution() -> None:
    from spec_orch.services.litellm_supervisor_adapter import _SUPERVISOR_SYSTEM_PROMPT

    assert "## Constitution" in _SUPERVISOR_SYSTEM_PROMPT
    assert "Prefer evidence over optimism." in _SUPERVISOR_SYSTEM_PROMPT
    assert "Escalate with explicit blocking questions" in _SUPERVISOR_SYSTEM_PROMPT
    assert "Do not silently approve ambiguous outcomes" in _SUPERVISOR_SYSTEM_PROMPT
