from __future__ import annotations

from typing import Any, cast

from spec_orch.services.memory.protocol import MemoryProvider
from spec_orch.services.memory.types import MemoryEntry


class MemoryWriter:
    """Write-focused facade over provider and recorder-backed memory operations."""

    def __init__(self, *, provider: MemoryProvider, service: Any) -> None:
        self._provider = provider
        self._service = service

    def store(self, entry: MemoryEntry) -> str:
        return cast(str, self._service.store(entry))

    def forget(self, key: str) -> bool:
        return cast(bool, self._service.forget(key))

    def __getattr__(self, name: str) -> Any:
        allowed = {
            "compact",
            "consolidate_run",
            "record_issue_completion",
            "record_mission_event",
            "schedule_post_run_derivations",
            "enqueue_derivation",
            "process_derivations",
        }
        if name in allowed:
            return getattr(self._service, name)
        raise AttributeError(f"{type(self).__name__!s} has no attribute {name!s}")
