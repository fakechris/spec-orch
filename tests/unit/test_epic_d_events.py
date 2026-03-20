"""Tests for Epic D: EventBus standardization and trace sampling."""

from __future__ import annotations

from spec_orch.services.event_bus import EventBus, EventTopic
from spec_orch.services.trace_sampler import TraceSampler


def test_new_event_topics() -> None:
    assert EventTopic.TOOL_START == "tool.start"
    assert EventTopic.TOOL_END == "tool.end"
    assert EventTopic.TURN_END == "turn.end"
    assert EventTopic.EVAL_SAMPLE == "eval.sample"


def test_emit_tool_start() -> None:
    bus = EventBus()
    events: list = []
    bus.subscribe(lambda e: events.append(e), EventTopic.TOOL_START)
    bus.emit_tool_start("git_diff", issue_id="TEST-1")
    assert len(events) == 1
    assert events[0].payload["tool_name"] == "git_diff"


def test_emit_tool_end() -> None:
    bus = EventBus()
    events: list = []
    bus.subscribe(lambda e: events.append(e), EventTopic.TOOL_END)
    bus.emit_tool_end("git_diff", issue_id="TEST-1", duration_ms=123, success=True)
    assert len(events) == 1
    assert events[0].payload["duration_ms"] == 123


def test_emit_turn_end() -> None:
    bus = EventBus()
    events: list = []
    bus.subscribe(lambda e: events.append(e), EventTopic.TURN_END)
    bus.emit_turn_end(issue_id="TEST-1", token_count=5000)
    assert len(events) == 1
    assert events[0].payload["token_count"] == 5000


def test_emit_eval_sample() -> None:
    bus = EventBus()
    events: list = []
    bus.subscribe(lambda e: events.append(e), EventTopic.EVAL_SAMPLE)
    bus.emit_eval_sample("run-42", reason="negative_feedback")
    assert len(events) == 1
    assert events[0].payload["reason"] == "negative_feedback"


def test_trace_sampler_negative_feedback() -> None:
    sampler = TraceSampler()
    should, reason = sampler.should_sample(run_id="r1", has_negative_feedback=True)
    assert should
    assert reason == "negative_feedback"


def test_trace_sampler_high_cost() -> None:
    sampler = TraceSampler()
    should, reason = sampler.should_sample(run_id="r1", token_count=100000)
    assert should
    assert "high_cost" in reason


def test_trace_sampler_post_change() -> None:
    sampler = TraceSampler()
    sampler.record_change()
    should, reason = sampler.should_sample(run_id="r1")
    assert should
    assert reason == "post_change_window"
