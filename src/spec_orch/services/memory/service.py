"""MemoryService — singleton façade for the memory subsystem.

Wraps a :class:`MemoryProvider` and hooks into the :class:`EventBus`
to automatically capture mission lifecycle events into episodic memory.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from spec_orch.services.memory.fs_provider import FileSystemMemoryProvider
from spec_orch.services.memory.protocol import MemoryProvider
from spec_orch.services.memory.types import MemoryEntry, MemoryLayer, MemoryQuery

logger = logging.getLogger(__name__)

_DEFAULT_MEMORY_DIR = ".spec_orch_memory"

_instance: MemoryService | None = None


class MemoryService:
    """High-level façade over a pluggable :class:`MemoryProvider`.

    Also subscribes to the ``EventBus`` so that mission/issue state
    changes are transparently recorded in episodic memory.
    """

    def __init__(
        self,
        provider: MemoryProvider | None = None,
        *,
        repo_root: Path | None = None,
    ) -> None:
        if provider is not None:
            self._provider = provider
        else:
            root = (repo_root or Path.cwd()) / _DEFAULT_MEMORY_DIR
            self._provider = FileSystemMemoryProvider(root)

    @property
    def provider(self) -> MemoryProvider:
        return self._provider

    # -- delegated CRUD ------------------------------------------------------

    def store(self, entry: MemoryEntry) -> str:
        key = self._provider.store(entry)
        self._emit("memory.stored", {"key": key, "layer": entry.layer.value})
        return key

    def recall(self, query: MemoryQuery) -> list[MemoryEntry]:
        results = self._provider.recall(query)
        self._emit("memory.recalled", {"query_text": query.text, "count": len(results)})
        return results

    def forget(self, key: str) -> bool:
        removed = self._provider.forget(key)
        if removed:
            self._emit("memory.forgotten", {"key": key})
        return removed

    def get(self, key: str) -> MemoryEntry | None:
        return self._provider.get(key)

    def list_keys(
        self,
        *,
        layer: str | None = None,
        tags: list[str] | None = None,
        limit: int = 100,
    ) -> list[str]:
        return self._provider.list_keys(layer=layer, tags=tags, limit=limit)

    def list_summaries(
        self,
        *,
        layer: str | None = None,
        tags: list[str] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return index-only summaries (no file I/O per entry)."""
        if hasattr(self._provider, "list_summaries"):
            result: list[dict[str, Any]] = self._provider.list_summaries(
                layer=layer, tags=tags, limit=limit
            )  # type: ignore[union-attr]
            return result
        keys = self._provider.list_keys(layer=layer, tags=tags, limit=limit)
        return [{"key": k, "layer": layer or "", "tags": []} for k in keys]

    def compact(self, *, max_age_days: int = 30) -> dict[str, int]:
        """Remove expired episodic memory entries older than max_age_days.

        Uses index-only summaries to avoid O(N) file reads.
        """
        from datetime import UTC, datetime, timedelta

        cutoff = datetime.now(UTC) - timedelta(days=max_age_days)

        summaries = self.list_summaries(layer=MemoryLayer.EPISODIC.value, limit=100_000)
        expired_keys: list[str] = []
        retained = 0
        for s in summaries:
            created = s.get("created_at", "")
            try:
                entry_dt = datetime.fromisoformat(created)
            except (ValueError, TypeError):
                retained += 1
                continue
            if entry_dt < cutoff:
                expired_keys.append(s["key"])
            else:
                retained += 1

        removed = 0
        for key in expired_keys:
            if self.forget(key):
                removed += 1

        if removed > 0:
            logger.info(
                "Memory compact: removed %d expired entries, retained %d",
                removed,
                retained,
            )
        return {"removed": removed, "retained": retained}

    def consolidate_run(
        self,
        *,
        run_id: str,
        issue_id: str,
        succeeded: bool,
        failed_conditions: list[str] | None = None,
        key_learnings: str = "",
    ) -> str | None:
        """Store a run outcome summary in semantic memory for cross-run learning."""
        outcome = "succeeded" if succeeded else "failed"
        content = f"Run {run_id} for {issue_id}: {outcome}"
        if key_learnings:
            content = f"{content}\n{key_learnings}"

        entry = MemoryEntry(
            key=f"run-summary-{run_id}",
            content=content,
            layer=MemoryLayer.SEMANTIC,
            tags=["run-summary", "auto-consolidated"],
            metadata={
                "run_id": run_id,
                "issue_id": issue_id,
                "succeeded": succeeded,
                "failed_conditions": failed_conditions or [],
            },
        )
        return self.store(entry)

    # -- lifecycle event capture ---------------------------------------------

    def record_mission_event(
        self,
        mission_id: str,
        phase: str,
        *,
        detail: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Write a mission lifecycle event to episodic memory."""
        content = f"# Mission {mission_id} — {phase}"
        if detail:
            content += f"\n\n{detail}"
        entry = MemoryEntry(
            key=f"mission-event-{mission_id}-{phase}",
            content=content,
            layer=MemoryLayer.EPISODIC,
            tags=["mission-event", f"mission:{mission_id}", phase],
            metadata={"mission_id": mission_id, "phase": phase, **(metadata or {})},
        )
        return self.store(entry)

    def record_issue_completion(
        self,
        issue_id: str,
        *,
        succeeded: bool,
        summary: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Write an issue completion event to episodic memory."""
        status = "succeeded" if succeeded else "failed"
        content = f"# Issue {issue_id} — {status}"
        if summary:
            content += f"\n\n{summary}"
        entry = MemoryEntry(
            key=f"issue-result-{issue_id}",
            content=content,
            layer=MemoryLayer.EPISODIC,
            tags=["issue-result", f"issue:{issue_id}", status],
            metadata={"issue_id": issue_id, "succeeded": succeeded, **(metadata or {})},
        )
        return self.store(entry)

    # -- EventBus integration ------------------------------------------------

    def subscribe_to_event_bus(self) -> None:
        """Wire up automatic memory capture from EventBus events."""
        try:
            from spec_orch.services.event_bus import EventTopic, get_event_bus

            bus = get_event_bus()
            bus.subscribe(self._on_mission_state, EventTopic.MISSION_STATE)
            bus.subscribe(self._on_issue_state, EventTopic.ISSUE_STATE)
            bus.subscribe(self._on_conductor, EventTopic.CONDUCTOR)
            bus.subscribe(self._on_gate_result, EventTopic.GATE_RESULT)
            logger.info("MemoryService subscribed to EventBus")
        except ImportError:
            logger.debug("EventBus not available, skipping subscription")

    def _on_mission_state(self, event: Any) -> None:
        payload = event.payload if hasattr(event, "payload") else event
        mission_id = payload.get("mission_id", "unknown")
        new_state = payload.get("new_state", "unknown")
        old_state = payload.get("old_state", "")
        detail = f"Transition: {old_state} → {new_state}" if old_state else ""
        self.record_mission_event(mission_id, new_state, detail=detail, metadata=payload)

    def _on_issue_state(self, event: Any) -> None:
        payload = event.payload if hasattr(event, "payload") else event
        issue_id = payload.get("issue_id", "unknown")
        state = payload.get("state", "unknown")
        succeeded = state in ("accepted", "merged")
        if state in ("accepted", "merged", "failed"):
            self.record_issue_completion(issue_id, succeeded=succeeded, metadata=payload)

    def _on_conductor(self, event: Any) -> None:
        payload = event.payload if hasattr(event, "payload") else event
        action = payload.get("action", "")
        thread_id = payload.get("thread_id", "unknown")

        if action == "fork":
            self.store(
                MemoryEntry(
                    key=f"conductor-fork-{thread_id}-{payload.get('linear_issue_id', '')}",
                    content=f"Fork: {payload.get('title', '')}",
                    layer=MemoryLayer.EPISODIC,
                    tags=["conductor-fork", f"thread:{thread_id}"],
                    metadata=payload,
                )
            )
        else:
            intent_cat = payload.get("intent_category", "")
            self.store(
                MemoryEntry(
                    key=f"intent-classified-{thread_id}-{payload.get('message_id', '')}",
                    content=payload.get("summary", ""),
                    layer=MemoryLayer.EPISODIC,
                    tags=["intent-classified", f"thread:{thread_id}", f"intent:{intent_cat}"],
                    metadata=payload,
                )
            )

    def _on_gate_result(self, event: Any) -> None:
        payload = event.payload if hasattr(event, "payload") else event
        issue_id = payload.get("issue_id", "unknown")
        passed = payload.get("passed", False)
        self.store(
            MemoryEntry(
                key=f"gate-verdict-{issue_id}-{int(time.time() * 1000)}",
                content=f"Gate {'passed' if passed else 'failed'}",
                layer=MemoryLayer.EPISODIC,
                tags=[
                    "gate-verdict",
                    f"issue:{issue_id}",
                    "gate-passed" if passed else "gate-failed",
                ],
                metadata=payload,
            )
        )

    # -- EventBus emit helper ------------------------------------------------

    @staticmethod
    def _emit(topic_str: str, payload: dict[str, Any]) -> None:
        try:
            from spec_orch.services.event_bus import Event, EventTopic, get_event_bus

            bus = get_event_bus()
            topic = EventTopic.MEMORY
            bus.publish(
                Event(topic=topic, payload={"sub": topic_str, **payload}, source="memory_service")
            )
        except ImportError:
            pass


def get_memory_service(repo_root: Path | None = None) -> MemoryService:
    """Return the global ``MemoryService`` singleton, creating it if needed."""
    global _instance  # noqa: PLW0603
    if _instance is None:
        _instance = MemoryService(repo_root=repo_root)
    return _instance


def reset_memory_service() -> None:
    """Reset the singleton (for testing)."""
    global _instance  # noqa: PLW0603
    _instance = None
