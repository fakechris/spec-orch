"""Tests for evidence context injection into Scoper and ReadinessChecker (SON-77)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from spec_orch.services.readiness_checker import ReadinessChecker
from spec_orch.services.scoper_adapter import _SCOPER_SYSTEM_PROMPT, LiteLLMScoperAdapter


class TestScoperEvidenceInjection:
    def test_no_evidence_uses_base_prompt(self) -> None:
        scoper = LiteLLMScoperAdapter(evidence_context=None)
        assert scoper._evidence_context is None

    def test_evidence_stored_on_init(self) -> None:
        ctx = "<evidence>10 runs, 80% success rate.</evidence>"
        scoper = LiteLLMScoperAdapter(evidence_context=ctx)
        assert scoper._evidence_context == ctx

    def test_evidence_injected_into_system_prompt(self) -> None:
        import sys
        from unittest.mock import MagicMock

        from spec_orch.domain.models import Mission

        mock_litellm = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"waves": []}'
        mock_litellm.completion.return_value = mock_response

        evidence = (
            "<evidence>5 runs, 60% success rate. Common failures: verification (3x).</evidence>"
        )
        scoper = LiteLLMScoperAdapter(evidence_context=evidence)

        mission = Mission(
            mission_id="test",
            title="Test Mission",
            acceptance_criteria=["AC1"],
            constraints=[],
        )
        with patch.dict(sys.modules, {"litellm": mock_litellm}):
            scoper.scope(
                mission=mission, codebase_context={"spec_content": "spec", "file_tree": ""}
            )

        call_kwargs = mock_litellm.completion.call_args[1]
        system_msg = call_kwargs["messages"][0]["content"]
        assert "historical evidence" in system_msg
        assert evidence in system_msg
        assert system_msg.startswith(_SCOPER_SYSTEM_PROMPT)

    def test_no_evidence_keeps_base_prompt_only(self) -> None:
        import sys
        from unittest.mock import MagicMock

        from spec_orch.domain.models import Mission

        mock_litellm = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"waves": []}'
        mock_litellm.completion.return_value = mock_response

        scoper = LiteLLMScoperAdapter(evidence_context=None)
        mission = Mission(
            mission_id="test",
            title="Test Mission",
            acceptance_criteria=[],
            constraints=[],
        )
        with patch.dict(sys.modules, {"litellm": mock_litellm}):
            scoper.scope(mission=mission, codebase_context={"spec_content": "", "file_tree": ""})

        call_kwargs = mock_litellm.completion.call_args[1]
        system_msg = call_kwargs["messages"][0]["content"]
        assert system_msg == _SCOPER_SYSTEM_PROMPT


class TestReadinessCheckerEvidenceInjection:
    def test_no_evidence_default(self) -> None:
        checker = ReadinessChecker(planner=None, evidence_context=None)
        assert checker._evidence_context is None

    def test_evidence_stored(self) -> None:
        ctx = "<evidence>Data here</evidence>"
        checker = ReadinessChecker(planner=None, evidence_context=ctx)
        assert checker._evidence_context == ctx

    def test_llm_check_includes_evidence_in_prompt(self) -> None:
        mock_planner = MagicMock()
        mock_planner.brainstorm.return_value = "READY"

        evidence = "<evidence>High failure rate in database-related issues.</evidence>"
        checker = ReadinessChecker(planner=mock_planner, evidence_context=evidence)

        description = (
            "## Goal\nFix the bug\n\n"
            "## Acceptance Criteria\n- [ ] Tests pass\n\n"
            "## Files in Scope\n- `src/foo.py`\n"
        )
        result = checker.check(description)
        assert result.ready is True

        call_args = mock_planner.brainstorm.call_args
        prompt = call_args[1]["conversation_history"][0]["content"]
        assert "historical evidence" in prompt
        assert evidence in prompt

    def test_llm_check_without_evidence_no_evidence_block(self) -> None:
        mock_planner = MagicMock()
        mock_planner.brainstorm.return_value = "READY"

        checker = ReadinessChecker(planner=mock_planner, evidence_context=None)

        description = (
            "## Goal\nFix the bug\n\n"
            "## Acceptance Criteria\n- [ ] Tests pass\n\n"
            "## Files in Scope\n- `src/foo.py`\n"
        )
        result = checker.check(description)
        assert result.ready is True

        call_args = mock_planner.brainstorm.call_args
        prompt = call_args[1]["conversation_history"][0]["content"]
        assert "historical evidence" not in prompt

    def test_rule_check_skips_llm_regardless_of_evidence(self) -> None:
        """Rule check failure returns immediately, LLM is never called."""
        mock_planner = MagicMock()
        checker = ReadinessChecker(
            planner=mock_planner,
            evidence_context="<evidence>stuff</evidence>",
        )
        result = checker.check("No proper sections here.")
        assert result.ready is False
        assert len(result.missing_fields) > 0
        mock_planner.brainstorm.assert_not_called()
