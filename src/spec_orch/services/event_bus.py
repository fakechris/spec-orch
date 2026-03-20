"""In-process event bus for broadcasting state changes.

Subscribers receive events via sync callbacks or async queues.
The bus is thread-safe and supports topic-based filtering.
"""

from __future__ import annotations

import asyncio
import enum
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


class EventTopic(enum.StrEnum):
    MISSION_STATE = "mission.state"
    ISSUE_STATE = "issue.state"
    BUILDER_OUTPUT = "builder.output"
    GATE_RESULT = "gate.result"
    EVOLUTION = "evolution"
    BTW_INJECTED = "btw.injected"
    CONDUCTOR = "conductor"
    MEMORY = "memory"
    SYSTEM = "system"
    TOOL_START = "tool.start"
    TOOL_END = "tool.end"
    TURN_END = "turn.end"
    EVAL_SAMPLE = "eval.sample"
    FALLBACK = "fallback"


@dataclass(frozen=True)
class Event:
    topic: EventTopic
    payload: dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    source: str = ""


SyncHandler = Callable[[Event], None]


class EventBus:
    """Thread-safe in-process pub/sub event bus."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sync_handlers: dict[EventTopic | None, list[SyncHandler]] = {}
        self._async_queues: list[asyncio.Queue[Event]] = []
        self._history: list[Event] = []
        self._max_history = 500

    def publish(self, event: Event) -> None:
        with self._lock:
            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history :]

            topic_handlers = self._sync_handlers.get(event.topic, [])
            wildcard_handlers = self._sync_handlers.get(None, [])
            handlers = topic_handlers + wildcard_handlers

            queues = list(self._async_queues)

        for handler in handlers:
            try:
                handler(event)
            except Exception:
                logger.exception("Event handler error for %s", event.topic)

        for queue in queues:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("Async queue full, dropping event %s", event.topic)

    def subscribe(
        self, handler: SyncHandler, topic: EventTopic | None = None
    ) -> Callable[[], None]:
        """Subscribe a sync handler. Pass topic=None for all events.

        Returns an unsubscribe callable.
        """
        with self._lock:
            self._sync_handlers.setdefault(topic, []).append(handler)

        def unsubscribe() -> None:
            with self._lock:
                handlers = self._sync_handlers.get(topic, [])
                if handler in handlers:
                    handlers.remove(handler)

        return unsubscribe

    def create_async_queue(self, maxsize: int = 256) -> asyncio.Queue[Event]:
        """Create an async queue that receives all events (for WebSocket consumers)."""
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=maxsize)
        with self._lock:
            self._async_queues.append(queue)
        return queue

    def remove_async_queue(self, queue: asyncio.Queue[Event]) -> None:
        with self._lock:
            if queue in self._async_queues:
                self._async_queues.remove(queue)

    def recent_events(self, limit: int = 50) -> list[Event]:
        with self._lock:
            return list(self._history[-limit:])

    def query_history(
        self,
        *,
        topic: EventTopic | None = None,
        issue_id: str | None = None,
        run_id: str | None = None,
        since_ts: float | None = None,
        limit: int = 100,
    ) -> list[Event]:
        """Query buffered history with optional filters."""
        with self._lock:
            events = list(self._history)

        def _match(ev: Event) -> bool:
            if topic is not None and ev.topic != topic:
                return False
            if since_ts is not None and ev.timestamp < since_ts:
                return False
            if issue_id is not None and ev.payload.get("issue_id") != issue_id:
                return False
            return run_id is None or ev.payload.get("run_id") == run_id

        filtered = [ev for ev in events if _match(ev)]
        if limit <= 0:
            return []
        return filtered[-limit:]

    def emit_mission_state(
        self, mission_id: str, old_state: str, new_state: str, **extra: Any
    ) -> None:
        self.publish(
            Event(
                topic=EventTopic.MISSION_STATE,
                payload={
                    "mission_id": mission_id,
                    "old_state": old_state,
                    "new_state": new_state,
                    **extra,
                },
                source="lifecycle_manager",
            )
        )

    def emit_issue_state(self, issue_id: str, state: str, **extra: Any) -> None:
        self.publish(
            Event(
                topic=EventTopic.ISSUE_STATE,
                payload={"issue_id": issue_id, "state": state, **extra},
                source="daemon",
            )
        )

    def emit_builder_output(self, issue_id: str, line: str, stream: str = "stdout") -> None:
        self.publish(
            Event(
                topic=EventTopic.BUILDER_OUTPUT,
                payload={
                    "issue_id": issue_id,
                    "line": line,
                    "stream": stream,
                },
                source="builder",
            )
        )

    def emit_btw(self, issue_id: str, message: str, channel: str) -> None:
        self.publish(
            Event(
                topic=EventTopic.BTW_INJECTED,
                payload={
                    "issue_id": issue_id,
                    "message": message,
                    "channel": channel,
                },
                source=channel,
            )
        )

    def emit_tool_start(self, tool_name: str, issue_id: str = "", **extra: Any) -> None:
        self.publish(
            Event(
                topic=EventTopic.TOOL_START,
                payload={"tool_name": tool_name, "issue_id": issue_id, **extra},
                source="agent",
            )
        )

    def emit_tool_end(
        self,
        tool_name: str,
        issue_id: str = "",
        duration_ms: float = 0,
        success: bool = True,
        **extra: Any,
    ) -> None:
        self.publish(
            Event(
                topic=EventTopic.TOOL_END,
                payload={
                    "tool_name": tool_name,
                    "issue_id": issue_id,
                    "duration_ms": duration_ms,
                    "success": success,
                    **extra,
                },
                source="agent",
            )
        )

    def emit_turn_end(self, issue_id: str = "", token_count: int = 0, **extra: Any) -> None:
        self.publish(
            Event(
                topic=EventTopic.TURN_END,
                payload={
                    "issue_id": issue_id,
                    "token_count": token_count,
                    **extra,
                },
                source="agent",
            )
        )

    def emit_eval_sample(self, run_id: str, reason: str, **extra: Any) -> None:
        """Mark a run for online evaluation sampling."""
        self.publish(
            Event(
                topic=EventTopic.EVAL_SAMPLE,
                payload={"run_id": run_id, "reason": reason, **extra},
                source="eval_sampler",
            )
        )

    def emit_fallback(
        self,
        component: str,
        primary: str,
        fallback: str,
        reason: str,
        issue_id: str = "",
        **extra: Any,
    ) -> None:
        """Record a degradation / fallback event for observability."""
        self.publish(
            Event(
                topic=EventTopic.FALLBACK,
                payload={
                    "component": component,
                    "primary": primary,
                    "fallback": fallback,
                    "reason": reason,
                    "issue_id": issue_id,
                    **extra,
                },
                source=component,
            )
        )


_global_bus: EventBus | None = None
_global_lock = threading.Lock()


def get_event_bus() -> EventBus:
    """Get or create the global EventBus singleton."""
    global _global_bus
    if _global_bus is None:
        with _global_lock:
            if _global_bus is None:
                _global_bus = EventBus()
    return _global_bus


def reset_event_bus() -> None:
    """Reset the global bus (for testing)."""
    global _global_bus
    with _global_lock:
        _global_bus = None
