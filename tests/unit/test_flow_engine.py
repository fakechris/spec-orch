"""Tests for the flow_engine package — Phase 1 & 2 of Change 01."""

from __future__ import annotations

import pytest

from spec_orch.domain.models import FlowGraph, FlowStep, FlowTransitionEvent, FlowType, RunState
from spec_orch.flow_engine.engine import FlowEngine
from spec_orch.flow_engine.graphs import FULL_GRAPH, HOTFIX_GRAPH, STANDARD_GRAPH
from spec_orch.flow_engine.mapper import FlowMapper

# ── T1.1: FlowType enum ──────────────────────────────────────────────────


class TestFlowType:
    def test_values(self):
        assert FlowType.FULL == "full"
        assert FlowType.STANDARD == "standard"
        assert FlowType.HOTFIX == "hotfix"

    def test_construct_from_string(self):
        assert FlowType("full") is FlowType.FULL
        assert FlowType("standard") is FlowType.STANDARD

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            FlowType("unknown")


# ── T1.2: FlowStep, FlowGraph ────────────────────────────────────────────


class TestFlowStep:
    def test_construct(self):
        step = FlowStep(id="build", run_state=RunState.BUILDING)
        assert step.id == "build"
        assert step.run_state is RunState.BUILDING
        assert step.skippable_if == ()

    def test_skippable_if(self):
        step = FlowStep(id="verify", skippable_if=("doc_only",))
        assert "doc_only" in step.skippable_if


class TestFlowGraph:
    def test_step_ids(self):
        g = FlowGraph(
            flow_type=FlowType.STANDARD,
            steps=(FlowStep(id="a"), FlowStep(id="b")),
            transitions={"a": ("b",), "b": ()},
        )
        assert g.step_ids() == ["a", "b"]

    def test_get_step(self):
        step_a = FlowStep(id="a")
        g = FlowGraph(flow_type=FlowType.STANDARD, steps=(step_a,))
        assert g.get_step("a") is step_a
        assert g.get_step("missing") is None


# ── T1.3: FlowTransitionEvent ────────────────────────────────────────────


class TestFlowTransitionEvent:
    def test_construct(self):
        evt = FlowTransitionEvent(
            from_flow="standard",
            to_flow="full",
            trigger="promotion_required",
            timestamp="2026-01-01T00:00:00Z",
            issue_id="SON-123",
            run_id="run-001",
        )
        assert evt.from_flow == "standard"
        assert evt.to_flow == "full"
        assert evt.trigger == "promotion_required"


# ── T1.4/T1.5/T1.6: Pre-defined graphs ──────────────────────────────────


class TestFullGraph:
    def test_flow_type(self):
        assert FULL_GRAPH.flow_type is FlowType.FULL

    def test_steps_match_policy(self):
        ids = FULL_GRAPH.step_ids()
        assert "create_issue" in ids
        assert "discuss" in ids
        assert "freeze_spec" in ids
        assert "mission_approve" in ids
        assert "generate_plan" in ids
        assert "execute" in ids
        assert "verify" in ids
        assert "gate" in ids
        assert "pr_review" in ids
        assert "merge" in ids
        assert "retrospective" in ids

    def test_transitions_are_complete(self):
        for step in FULL_GRAPH.steps:
            assert step.id in FULL_GRAPH.transitions

    def test_backtrack_gate_recoverable(self):
        assert FULL_GRAPH.backtrack["gate"]["recoverable"] == "execute"

    def test_backtrack_gate_needs_redesign(self):
        assert FULL_GRAPH.backtrack["gate"]["needs_redesign"] == "freeze_spec"


class TestStandardGraph:
    def test_flow_type(self):
        assert STANDARD_GRAPH.flow_type is FlowType.STANDARD

    def test_no_discuss_freeze_plan(self):
        ids = STANDARD_GRAPH.step_ids()
        assert "discuss" not in ids
        assert "freeze_spec" not in ids
        assert "generate_plan" not in ids
        assert "retrospective" not in ids

    def test_starts_with_create_issue(self):
        assert STANDARD_GRAPH.steps[0].id == "create_issue"

    def test_implement_step_exists(self):
        assert STANDARD_GRAPH.get_step("implement") is not None
        assert STANDARD_GRAPH.get_step("implement").run_state is RunState.BUILDING


class TestHotfixGraph:
    def test_flow_type(self):
        assert HOTFIX_GRAPH.flow_type is FlowType.HOTFIX

    def test_has_post_merge_review(self):
        ids = HOTFIX_GRAPH.step_ids()
        assert "post_merge_review" in ids

    def test_pre_merge_review_skippable(self):
        step = HOTFIX_GRAPH.get_step("pre_merge_review")
        assert step is not None
        assert "urgent" in step.skippable_if


# ── T2.1: FlowEngine.get_graph ───────────────────────────────────────────


class TestFlowEngineGetGraph:
    def test_returns_full(self):
        engine = FlowEngine()
        assert engine.get_graph(FlowType.FULL) is FULL_GRAPH

    def test_returns_standard(self):
        engine = FlowEngine()
        assert engine.get_graph(FlowType.STANDARD) is STANDARD_GRAPH

    def test_returns_hotfix(self):
        engine = FlowEngine()
        assert engine.get_graph(FlowType.HOTFIX) is HOTFIX_GRAPH

    def test_unknown_raises(self):
        engine = FlowEngine(graphs={FlowType.STANDARD: STANDARD_GRAPH})
        with pytest.raises(ValueError, match="Unknown flow type"):
            engine.get_graph(FlowType.FULL)


# ── T2.2: FlowEngine.get_next_steps ──────────────────────────────────────


class TestFlowEngineNextSteps:
    def test_standard_implement_to_verify(self):
        engine = FlowEngine()
        assert engine.get_next_steps(FlowType.STANDARD, "implement") == ["verify"]

    def test_terminal_step_returns_empty(self):
        engine = FlowEngine()
        assert engine.get_next_steps(FlowType.STANDARD, "merge") == []

    def test_nonexistent_step_returns_empty(self):
        engine = FlowEngine()
        assert engine.get_next_steps(FlowType.STANDARD, "nonexistent") == []


# ── T2.3: FlowEngine.get_backtrack_target ─────────────────────────────────


class TestFlowEngineBacktrack:
    def test_recoverable(self):
        engine = FlowEngine()
        assert engine.get_backtrack_target(FlowType.FULL, "gate", "recoverable") == "execute"

    def test_needs_redesign(self):
        engine = FlowEngine()
        assert engine.get_backtrack_target(FlowType.FULL, "gate", "needs_redesign") == "freeze_spec"

    def test_unknown_reason_returns_none(self):
        engine = FlowEngine()
        assert engine.get_backtrack_target(FlowType.FULL, "gate", "unknown_reason") is None

    def test_no_backtrack_for_step(self):
        engine = FlowEngine()
        assert engine.get_backtrack_target(FlowType.FULL, "execute", "recoverable") is None


# ── T2.5: FlowMapper.resolve_flow_type ────────────────────────────────────


class TestFlowMapper:
    def test_feature_maps_to_full(self):
        mapper = FlowMapper()
        assert mapper.resolve_flow_type("feature") is FlowType.FULL

    def test_bug_maps_to_standard(self):
        mapper = FlowMapper()
        assert mapper.resolve_flow_type("bug") is FlowType.STANDARD

    def test_hotfix_label_overrides_intent(self):
        mapper = FlowMapper()
        assert mapper.resolve_flow_type("feature", labels=["hotfix"]) is FlowType.HOTFIX

    def test_unknown_intent_returns_none(self):
        mapper = FlowMapper()
        assert mapper.resolve_flow_type("exploration") is None

    def test_empty_returns_none(self):
        mapper = FlowMapper()
        assert mapper.resolve_flow_type(None) is None

    def test_run_class_fallback(self):
        mapper = FlowMapper()
        assert mapper.resolve_flow_type(None, run_class="bug") is FlowType.STANDARD

    def test_case_insensitive(self):
        mapper = FlowMapper()
        assert mapper.resolve_flow_type("Feature") is FlowType.FULL


# ── T2.6: Skippable step checking ────────────────────────────────────────


class TestFlowEngineSkippable:
    def test_doc_only_skips_execute_in_full(self):
        engine = FlowEngine()
        assert engine.is_skippable(FlowType.FULL, "execute", {"doc_only"}) is True

    def test_no_condition_not_skippable(self):
        engine = FlowEngine()
        assert engine.is_skippable(FlowType.FULL, "execute", set()) is False

    def test_non_skippable_step(self):
        engine = FlowEngine()
        assert engine.is_skippable(FlowType.FULL, "gate", {"doc_only"}) is False

    def test_hotfix_pre_merge_review_skippable(self):
        engine = FlowEngine()
        assert engine.is_skippable(FlowType.HOTFIX, "pre_merge_review", {"urgent"}) is True

    def test_unknown_step_returns_false(self):
        engine = FlowEngine()
        assert engine.is_skippable(FlowType.FULL, "nonexistent", {"doc_only"}) is False
