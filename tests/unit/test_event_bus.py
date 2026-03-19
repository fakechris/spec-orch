"""Tests for EventBus."""

from __future__ import annotations

import asyncio

import pytest

from spec_orch.services.event_bus import (
    Event,
    EventBus,
    EventTopic,
    get_event_bus,
    reset_event_bus,
)


@pytest.fixture(autouse=True)
def _reset_global():
    reset_event_bus()
    yield
    reset_event_bus()


class TestEventBus:
    def test_publish_and_subscribe(self):
        bus = EventBus()
        received: list[Event] = []
        bus.subscribe(lambda e: received.append(e), EventTopic.MISSION_STATE)

        bus.publish(Event(topic=EventTopic.MISSION_STATE, payload={"x": 1}))
        assert len(received) == 1
        assert received[0].payload == {"x": 1}

    def test_wildcard_subscriber(self):
        bus = EventBus()
        received: list[Event] = []
        bus.subscribe(lambda e: received.append(e), topic=None)

        bus.publish(Event(topic=EventTopic.MISSION_STATE, payload={}))
        bus.publish(Event(topic=EventTopic.ISSUE_STATE, payload={}))
        assert len(received) == 2

    def test_topic_filtering(self):
        bus = EventBus()
        received: list[Event] = []
        bus.subscribe(lambda e: received.append(e), EventTopic.GATE_RESULT)

        bus.publish(Event(topic=EventTopic.MISSION_STATE, payload={}))
        bus.publish(Event(topic=EventTopic.GATE_RESULT, payload={"ok": True}))
        assert len(received) == 1

    def test_unsubscribe(self):
        bus = EventBus()
        received: list[Event] = []
        unsub = bus.subscribe(lambda e: received.append(e), EventTopic.SYSTEM)

        bus.publish(Event(topic=EventTopic.SYSTEM, payload={}))
        assert len(received) == 1

        unsub()
        bus.publish(Event(topic=EventTopic.SYSTEM, payload={}))
        assert len(received) == 1

    def test_handler_error_does_not_crash(self):
        bus = EventBus()

        def bad_handler(e: Event) -> None:
            raise ValueError("boom")

        ok: list[Event] = []
        bus.subscribe(bad_handler, EventTopic.SYSTEM)
        bus.subscribe(lambda e: ok.append(e), EventTopic.SYSTEM)

        bus.publish(Event(topic=EventTopic.SYSTEM, payload={}))
        assert len(ok) == 1

    def test_recent_events(self):
        bus = EventBus()
        for i in range(5):
            bus.publish(Event(topic=EventTopic.SYSTEM, payload={"i": i}))
        recent = bus.recent_events(limit=3)
        assert len(recent) == 3
        assert recent[0].payload["i"] == 2

    def test_query_history_by_issue_and_topic(self):
        bus = EventBus()
        bus.publish(Event(topic=EventTopic.SYSTEM, payload={"issue_id": "SON-1"}))
        bus.publish(Event(topic=EventTopic.ISSUE_STATE, payload={"issue_id": "SON-1"}))
        bus.publish(Event(topic=EventTopic.ISSUE_STATE, payload={"issue_id": "SON-2"}))

        events = bus.query_history(topic=EventTopic.ISSUE_STATE, issue_id="SON-1", limit=10)
        assert len(events) == 1
        assert events[0].payload["issue_id"] == "SON-1"

    def test_query_history_zero_limit_returns_empty(self):
        bus = EventBus()
        bus.publish(Event(topic=EventTopic.SYSTEM, payload={"issue_id": "SON-1"}))
        events = bus.query_history(limit=0)
        assert events == []

    def test_history_capped(self):
        bus = EventBus()
        bus._max_history = 10
        for i in range(20):
            bus.publish(Event(topic=EventTopic.SYSTEM, payload={"i": i}))
        assert len(bus._history) == 10

    def test_emit_mission_state(self):
        bus = EventBus()
        received: list[Event] = []
        bus.subscribe(lambda e: received.append(e), EventTopic.MISSION_STATE)

        bus.emit_mission_state("m1", "approved", "planning")
        assert received[0].payload["mission_id"] == "m1"
        assert received[0].payload["old_state"] == "approved"
        assert received[0].payload["new_state"] == "planning"

    def test_emit_issue_state(self):
        bus = EventBus()
        received: list[Event] = []
        bus.subscribe(lambda e: received.append(e), EventTopic.ISSUE_STATE)

        bus.emit_issue_state("SON-1", "building", mission_id="m1")
        assert received[0].payload["issue_id"] == "SON-1"
        assert received[0].payload["mission_id"] == "m1"

    def test_emit_builder_output(self):
        bus = EventBus()
        received: list[Event] = []
        bus.subscribe(lambda e: received.append(e), EventTopic.BUILDER_OUTPUT)

        bus.emit_builder_output("SON-1", "running tests...", "stdout")
        assert received[0].payload["line"] == "running tests..."

    def test_emit_btw(self):
        bus = EventBus()
        received: list[Event] = []
        bus.subscribe(lambda e: received.append(e), EventTopic.BTW_INJECTED)

        bus.emit_btw("SON-1", "handle binary frames", "tui")
        assert received[0].payload["message"] == "handle binary frames"

    @pytest.mark.asyncio
    async def test_async_queue(self):
        bus = EventBus()
        queue = bus.create_async_queue()

        bus.publish(Event(topic=EventTopic.SYSTEM, payload={"hello": True}))

        event = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert event.payload["hello"] is True

        bus.remove_async_queue(queue)
        bus.publish(Event(topic=EventTopic.SYSTEM, payload={}))
        assert queue.empty()


class TestGlobalBus:
    def test_get_event_bus_singleton(self):
        bus1 = get_event_bus()
        bus2 = get_event_bus()
        assert bus1 is bus2

    def test_reset_event_bus(self):
        bus1 = get_event_bus()
        reset_event_bus()
        bus2 = get_event_bus()
        assert bus1 is not bus2
