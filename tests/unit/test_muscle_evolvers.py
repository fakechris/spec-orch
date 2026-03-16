"""Tests for muscle evolvers (Change 03)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from spec_orch.services.evolver_protocol import Evolver
from spec_orch.services.flow_policy_evolver import (
    FlowPolicyEvolver,
    FlowPolicyEvolveResult,
    FlowPolicySuggestion,
)
from spec_orch.services.gate_policy_evolver import (
    GatePolicyEvolver,
    GatePolicyEvolveResult,
    GatePolicySuggestion,
)
from spec_orch.services.intent_evolver import ClassifierVariant, IntentEvolver
from spec_orch.services.memory.service import MemoryService, reset_memory_service
from spec_orch.services.memory.types import MemoryEntry, MemoryLayer, MemoryQuery

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _seed_memory(tmp_path: Path, entries: list[MemoryEntry]) -> MemoryService:
    reset_memory_service()
    svc = MemoryService(repo_root=tmp_path)
    for e in entries:
        svc.store(e)
    return svc


def _intent_entry(
    category: str = "bug",
    thread_id: str = "t-1",
    confidence: float = 0.8,
    summary: str = "test",
    key_suffix: str = "1",
) -> MemoryEntry:
    return MemoryEntry(
        key=f"intent-classified-{thread_id}-{key_suffix}",
        content=summary,
        layer=MemoryLayer.EPISODIC,
        tags=["intent-classified", f"thread:{thread_id}", f"intent:{category}"],
        metadata={
            "intent_category": category,
            "confidence": confidence,
            "summary": summary,
            "thread_id": thread_id,
        },
    )


def _flow_event_entry(
    trigger: str = "promotion",
    intent_category: str = "bug",
    from_flow: str = "standard",
    to_flow: str = "full",
    key_suffix: str = "1",
) -> MemoryEntry:
    tag = "flow-promotion" if "promotion" in trigger else "flow-demotion"
    return MemoryEntry(
        key=f"{tag}-{key_suffix}",
        content=f"{trigger}: {from_flow} → {to_flow}",
        layer=MemoryLayer.EPISODIC,
        tags=[tag, f"intent:{intent_category}"],
        metadata={
            "trigger": trigger,
            "intent_category": intent_category,
            "from_flow": from_flow,
            "to_flow": to_flow,
        },
    )


def _gate_verdict_entry(
    issue_id: str = "SON-1",
    passed: bool = True,
    failed_conditions: list[str] | None = None,
    key_suffix: str = "1",
) -> MemoryEntry:
    return MemoryEntry(
        key=f"gate-verdict-{key_suffix}",
        content=f"Gate {'passed' if passed else 'failed'}",
        layer=MemoryLayer.EPISODIC,
        tags=[
            "gate-verdict",
            f"issue:{issue_id}",
            "gate-passed" if passed else "gate-failed",
        ],
        metadata={
            "issue_id": issue_id,
            "passed": passed,
            "failed_conditions": failed_conditions or [],
        },
    )


def _issue_result_entry(
    issue_id: str = "SON-1",
    succeeded: bool = True,
    key_suffix: str = "1",
) -> MemoryEntry:
    return MemoryEntry(
        key=f"issue-result-{key_suffix}",
        content=f"Issue {issue_id} {'succeeded' if succeeded else 'failed'}",
        layer=MemoryLayer.EPISODIC,
        tags=["issue-result", f"issue:{issue_id}"],
        metadata={"issue_id": issue_id, "succeeded": succeeded},
    )


# ---------------------------------------------------------------------------
# EvolverProtocol
# ---------------------------------------------------------------------------


class TestEvolverProtocol:
    def test_intent_evolver_conforms(self, tmp_path: Path):
        e = IntentEvolver(tmp_path)
        assert isinstance(e, Evolver)

    def test_flow_policy_evolver_conforms(self, tmp_path: Path):
        e = FlowPolicyEvolver(tmp_path)
        assert isinstance(e, Evolver)

    def test_gate_policy_evolver_conforms(self, tmp_path: Path):
        e = GatePolicyEvolver(tmp_path)
        assert isinstance(e, Evolver)


# ---------------------------------------------------------------------------
# IntentEvolver
# ---------------------------------------------------------------------------


class TestIntentEvolver:
    def test_empty_history(self, tmp_path: Path):
        e = IntentEvolver(tmp_path)
        assert e.load_history() == []
        assert e.get_active() is None

    def test_save_and_load_history(self, tmp_path: Path):
        e = IntentEvolver(tmp_path)
        v = ClassifierVariant(
            variant_id="v0",
            prompt_text="classify intent",
            is_active=True,
        )
        e.save_history([v])
        loaded = e.load_history()
        assert len(loaded) == 1
        assert loaded[0].variant_id == "v0"
        assert loaded[0].is_active is True

    def test_promote(self, tmp_path: Path):
        e = IntentEvolver(tmp_path)
        e.save_history(
            [
                ClassifierVariant(variant_id="v0", prompt_text="p0", is_active=True),
                ClassifierVariant(variant_id="v1", prompt_text="p1", is_candidate=True),
            ]
        )
        assert e.promote("v1") is True
        active = e.get_active()
        assert active is not None
        assert active.variant_id == "v1"

    def test_promote_nonexistent(self, tmp_path: Path):
        e = IntentEvolver(tmp_path)
        e.save_history([ClassifierVariant(variant_id="v0", prompt_text="p0")])
        assert e.promote("v99") is False

    def test_evolve_no_planner(self, tmp_path: Path):
        e = IntentEvolver(tmp_path, planner=None)
        assert e.evolve() is None

    def test_evolve_not_enough_data(self, tmp_path: Path):
        _seed_memory(tmp_path, [_intent_entry(key_suffix=str(i)) for i in range(3)])
        planner = MagicMock()
        e = IntentEvolver(tmp_path, planner=planner)
        assert e.evolve() is None
        planner.invoke.assert_not_called()

    def test_recall_intent_logs(self, tmp_path: Path):
        entries = [_intent_entry(key_suffix=str(i)) for i in range(5)]
        _seed_memory(tmp_path, entries)
        e = IntentEvolver(tmp_path)
        logs = e.recall_intent_logs()
        assert len(logs) == 5

    def test_compute_error_patterns(self, tmp_path: Path):
        entries = [_intent_entry(category="bug", key_suffix=str(i)) for i in range(3)] + [
            _intent_entry(category="feature", key_suffix=str(i + 3)) for i in range(2)
        ]
        _seed_memory(tmp_path, entries)
        e = IntentEvolver(tmp_path)
        patterns = e.compute_error_patterns()
        assert patterns["total_classifications"] == 5
        assert patterns["category_distribution"]["bug"] == 3


# ---------------------------------------------------------------------------
# FlowPolicyEvolver
# ---------------------------------------------------------------------------


class TestFlowPolicyEvolver:
    def test_evolve_not_enough_events(self, tmp_path: Path):
        _seed_memory(tmp_path, [_flow_event_entry(key_suffix="1")])
        e = FlowPolicyEvolver(tmp_path)
        assert e.evolve() is None

    def test_evolve_with_promotions(self, tmp_path: Path):
        entries = [
            _flow_event_entry(trigger="promotion", intent_category="bug", key_suffix=str(i))
            for i in range(6)
        ]
        _seed_memory(tmp_path, entries)

        mapping_dir = tmp_path / "src" / "spec_orch"
        mapping_dir.mkdir(parents=True, exist_ok=True)
        (mapping_dir / "flow_mapping.yaml").write_text(
            "intent_to_flow:\n  bug: standard\n  feature: full\n"
        )

        e = FlowPolicyEvolver(tmp_path)
        result = e.evolve()
        assert result is not None
        assert result.total_events_analysed >= 5
        assert any(s.intent_category == "bug" for s in result.suggestions)

    def test_save_and_load_suggestions(self, tmp_path: Path):
        e = FlowPolicyEvolver(tmp_path)
        result = FlowPolicyEvolveResult(
            suggestions=[
                FlowPolicySuggestion(
                    intent_category="bug",
                    current_flow="standard",
                    suggested_flow="full",
                    rationale="test",
                )
            ],
            total_events_analysed=10,
        )
        e._save_suggestions(result)
        loaded = e.load_suggestions()
        assert loaded is not None
        assert len(loaded.suggestions) == 1
        assert loaded.suggestions[0].intent_category == "bug"

    def test_missing_flow_mapping(self, tmp_path: Path):
        e = FlowPolicyEvolver(tmp_path)
        mapping = e.load_flow_mapping()
        assert mapping == {}


# ---------------------------------------------------------------------------
# GatePolicyEvolver
# ---------------------------------------------------------------------------


class TestGatePolicyEvolver:
    def test_evolve_not_enough_verdicts(self, tmp_path: Path):
        _seed_memory(tmp_path, [_gate_verdict_entry(key_suffix="1")])
        e = GatePolicyEvolver(tmp_path)
        assert e.evolve() is None

    def test_detect_false_positive(self, tmp_path: Path):
        verdicts = [
            _gate_verdict_entry(issue_id=f"S-{i}", passed=True, key_suffix=str(i)) for i in range(6)
        ]
        outcomes = [
            _issue_result_entry(issue_id=f"S-{i}", succeeded=False, key_suffix=str(i))
            for i in range(3)
        ]
        _seed_memory(tmp_path, verdicts + outcomes)

        e = GatePolicyEvolver(tmp_path)
        patterns = e.detect_false_patterns()
        assert patterns["total_verdicts"] == 6
        assert len(patterns["false_positives"]) == 3

    def test_evolve_with_false_positives(self, tmp_path: Path):
        verdicts = [
            _gate_verdict_entry(issue_id=f"S-{i}", passed=True, key_suffix=str(i)) for i in range(6)
        ]
        outcomes = [
            _issue_result_entry(issue_id=f"S-{i}", succeeded=False, key_suffix=str(i))
            for i in range(4)
        ]
        _seed_memory(tmp_path, verdicts + outcomes)

        e = GatePolicyEvolver(tmp_path)
        result = e.evolve()
        assert result is not None
        assert result.false_positives >= 3
        assert any(s.suggestion_type == "add_condition" for s in result.suggestions)

    def test_save_and_load_suggestions(self, tmp_path: Path):
        e = GatePolicyEvolver(tmp_path)
        result = GatePolicyEvolveResult(
            suggestions=[
                GatePolicySuggestion(
                    suggestion_type="add_rule",
                    condition="regression_check",
                    rationale="test",
                )
            ],
            total_verdicts=10,
        )
        e._save_suggestions(result)
        loaded = e.load_suggestions()
        assert loaded is not None
        assert len(loaded.suggestions) == 1

    def test_detect_false_negative(self, tmp_path: Path):
        verdicts = [
            _gate_verdict_entry(
                issue_id=f"FN-{i}",
                passed=False,
                failed_conditions=["builder"],
                key_suffix=f"fn-{i}",
            )
            for i in range(4)
        ]
        outcomes = [
            _issue_result_entry(issue_id=f"FN-{i}", succeeded=True, key_suffix=f"fn-{i}")
            for i in range(4)
        ]
        _seed_memory(tmp_path, verdicts + outcomes)
        e = GatePolicyEvolver(tmp_path)
        patterns = e.detect_false_patterns()
        assert len(patterns["false_negatives"]) == 4
        assert patterns["fn_failed_conditions"]["builder"] == 4

    def test_evolve_with_false_negatives(self, tmp_path: Path):
        verdicts = [
            _gate_verdict_entry(
                issue_id=f"FN-{i}",
                passed=False,
                failed_conditions=["builder"],
                key_suffix=f"fn-{i}",
            )
            for i in range(5)
        ]
        outcomes = [
            _issue_result_entry(issue_id=f"FN-{i}", succeeded=True, key_suffix=f"fn-{i}")
            for i in range(5)
        ]
        _seed_memory(tmp_path, verdicts + outcomes)
        e = GatePolicyEvolver(tmp_path)
        result = e.evolve()
        assert result is not None
        assert result.false_negatives >= 3
        assert any(s.suggestion_type == "adjust_severity" for s in result.suggestions)

    def test_no_outcomes_partial_analysis(self, tmp_path: Path):
        verdicts = [
            _gate_verdict_entry(issue_id=f"S-{i}", passed=True, key_suffix=str(i)) for i in range(6)
        ]
        _seed_memory(tmp_path, verdicts)
        e = GatePolicyEvolver(tmp_path)
        patterns = e.detect_false_patterns()
        assert patterns["total_verdicts"] == 6
        assert len(patterns["false_positives"]) == 0


# ---------------------------------------------------------------------------
# Memory event handlers
# ---------------------------------------------------------------------------


class TestMemoryEventHandlers:
    def test_on_conductor_intent(self, tmp_path: Path):
        reset_memory_service()
        svc = MemoryService(repo_root=tmp_path)
        event = MagicMock()
        event.payload = {
            "action": "classify",
            "thread_id": "t-1",
            "intent_category": "bug",
            "summary": "test bug",
            "message_id": "m-1",
        }
        svc._on_conductor(event)
        results = svc.recall(MemoryQuery(layer=MemoryLayer.EPISODIC, tags=["intent-classified"]))
        assert len(results) >= 1

    def test_on_conductor_fork(self, tmp_path: Path):
        reset_memory_service()
        svc = MemoryService(repo_root=tmp_path)
        event = MagicMock()
        event.payload = {
            "action": "fork",
            "thread_id": "t-1",
            "linear_issue_id": "SON-99",
            "title": "forked issue",
        }
        svc._on_conductor(event)
        results = svc.recall(MemoryQuery(layer=MemoryLayer.EPISODIC, tags=["conductor-fork"]))
        assert len(results) >= 1

    def test_on_gate_result(self, tmp_path: Path):
        reset_memory_service()
        svc = MemoryService(repo_root=tmp_path)
        event = MagicMock()
        event.payload = {
            "issue_id": "SON-1",
            "passed": False,
            "failed_conditions": ["builder", "verification"],
        }
        svc._on_gate_result(event)
        results = svc.recall(MemoryQuery(layer=MemoryLayer.EPISODIC, tags=["gate-verdict"]))
        assert len(results) >= 1
        assert results[0].metadata["passed"] is False


# ---------------------------------------------------------------------------
# GateService event emission
# ---------------------------------------------------------------------------


class TestGateServiceEmit:
    def test_evaluate_and_emit_calls_emit(self, tmp_path: Path, monkeypatch: Any):
        from spec_orch.domain.models import GateInput
        from spec_orch.services.gate_service import GatePolicy, GateService

        mock_emit = MagicMock()
        monkeypatch.setattr(GateService, "_emit_verdict", mock_emit)

        policy = GatePolicy(required_conditions={"builder"})
        svc = GateService(policy=policy)
        gate_input = GateInput(builder_succeeded=True)
        verdict = svc.evaluate_and_emit(gate_input)

        assert verdict.mergeable is True
        mock_emit.assert_called_once_with(gate_input, verdict)

    def test_evaluate_does_not_emit(self, tmp_path: Path, monkeypatch: Any):
        from spec_orch.domain.models import GateInput
        from spec_orch.services.gate_service import GatePolicy, GateService

        mock_emit = MagicMock()
        monkeypatch.setattr(GateService, "_emit_verdict", mock_emit)

        policy = GatePolicy(required_conditions={"builder"})
        svc = GateService(policy=policy)
        svc.evaluate(GateInput(builder_succeeded=True))
        mock_emit.assert_not_called()
