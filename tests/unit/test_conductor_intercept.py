"""Tests for Conductor.intercept() — full lifecycle interception."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from spec_orch.services.conductor.conductor import Conductor
from spec_orch.services.conductor.types import (
    DMAStage,
    IntentCategory,
    IntentSignal,
    InterceptResult,
)

_CLASSIFY = "spec_orch.services.conductor.conductor.classify_intent"


@pytest.fixture()
def conductor(tmp_path: Path) -> Conductor:
    return Conductor(repo_root=tmp_path)


class TestInterceptDisabledByEnv:
    def test_disabled_returns_continue(self, tmp_path: Path) -> None:
        with patch.dict(os.environ, {"SPEC_ORCH_INTERCEPT_ENABLED": "false"}):
            c = Conductor(repo_root=tmp_path)
        result = c.intercept(DMAStage.BUILD, "stop the build")
        assert result.action == "continue"
        assert result.intent_signal.confidence == 0.0


class TestInterceptStageFilter:
    def test_filtered_stage_returns_continue(self, tmp_path: Path) -> None:
        with patch.dict(os.environ, {"SPEC_ORCH_INTERCEPT_STAGES": "gate,review"}):
            c = Conductor(repo_root=tmp_path)
        result = c.intercept(DMAStage.BUILD, "do something")
        assert result.action == "continue"

    def test_allowed_stage_proceeds(self, tmp_path: Path) -> None:
        with patch.dict(os.environ, {"SPEC_ORCH_INTERCEPT_STAGES": "build"}):
            c = Conductor(repo_root=tmp_path)
        with patch(
            _CLASSIFY,
            return_value=IntentSignal(category=IntentCategory.EXPLORATION, confidence=0.3),
        ):
            result = c.intercept(DMAStage.BUILD, "just checking")
        assert result.action == "continue"


class TestInterceptEmptyInput:
    def test_none_input(self, conductor: Conductor) -> None:
        result = conductor.intercept(DMAStage.BUILD, "")
        assert result.action == "continue"

    def test_whitespace_input(self, conductor: Conductor) -> None:
        result = conductor.intercept(DMAStage.VERIFY, "   ")
        assert result.action == "continue"


class TestInterceptDebounce:
    def test_same_input_within_window_returns_continue(self, conductor: Conductor) -> None:
        signal = IntentSignal(
            category=IntentCategory.EXPLORATION,
            confidence=0.4,
            summary="hello",
        )
        with patch(_CLASSIFY, return_value=signal):
            r1 = conductor.intercept(DMAStage.BUILD, "hello")
            r2 = conductor.intercept(DMAStage.BUILD, "hello")
        assert r1.action == "continue"
        assert r2.action == "continue"
        assert r2.intent_signal.confidence == 0.0


class TestInterceptActionMapping:
    @pytest.mark.parametrize(
        ("category", "confidence", "stage", "expected_action"),
        [
            (IntentCategory.EXPLORATION, 0.5, DMAStage.BUILD, "continue"),
            (IntentCategory.QUESTION, 0.9, DMAStage.GATE, "continue"),
            (IntentCategory.DRIFT, 0.8, DMAStage.BUILD, "pause"),
            (IntentCategory.DRIFT, 0.8, DMAStage.VERIFY, "pause"),
            (IntentCategory.DRIFT, 0.8, DMAStage.GATE, "fork"),
            (IntentCategory.DRIFT, 0.8, DMAStage.REVIEW, "fork"),
            (IntentCategory.FEATURE, 0.9, DMAStage.GATE, "fork"),
            (IntentCategory.BUG, 0.8, DMAStage.REVIEW, "fork"),
            (IntentCategory.FEATURE, 0.9, DMAStage.BUILD, "redirect"),
            (IntentCategory.QUICK_FIX, 0.7, DMAStage.VERIFY, "redirect"),
        ],
    )
    def test_intent_to_action(
        self,
        conductor: Conductor,
        category: IntentCategory,
        confidence: float,
        stage: DMAStage,
        expected_action: str,
    ) -> None:
        signal = IntentSignal(category=category, confidence=confidence, summary="test")
        with patch(_CLASSIFY, return_value=signal):
            result = conductor.intercept(stage, "test input unique " + stage.value)
        assert result.action == expected_action


class TestInterceptClassifyFailure:
    def test_llm_failure_degrades_to_continue(self, conductor: Conductor) -> None:
        with patch(_CLASSIFY, side_effect=RuntimeError("LLM down")):
            result = conductor.intercept(DMAStage.BUILD, "some input xyz")
        assert result.action == "continue"


class TestInterceptForkAction:
    def test_fork_populates_metadata(self, conductor: Conductor) -> None:
        signal = IntentSignal(
            category=IntentCategory.DRIFT,
            confidence=0.9,
            summary="scope change",
            suggested_title="New scope",
        )
        with patch(_CLASSIFY, return_value=signal):
            result = conductor.intercept(
                DMAStage.GATE,
                "scope change detected abc",
                context={"thread_id": "t-123"},
            )
        assert result.action == "fork"
        assert result.metadata.get("stage") == "gate"


class TestInterceptResultDataclass:
    def test_defaults(self) -> None:
        sig = IntentSignal(category=IntentCategory.EXPLORATION, confidence=0.0)
        r = InterceptResult(intent_signal=sig)
        assert r.action == "continue"
        assert r.metadata == {}

    def test_custom_action(self) -> None:
        sig = IntentSignal(category=IntentCategory.DRIFT, confidence=0.9)
        r = InterceptResult(intent_signal=sig, action="pause", metadata={"x": 1})
        assert r.action == "pause"
        assert r.metadata["x"] == 1


class TestDMAStageEnum:
    def test_all_values(self) -> None:
        expected = {
            "conversation",
            "build",
            "verify",
            "review",
            "gate",
            "retro",
        }
        assert {s.value for s in DMAStage} == expected
