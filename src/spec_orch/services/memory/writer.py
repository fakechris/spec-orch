from __future__ import annotations

from typing import Any

from spec_orch.services.memory.protocol import MemoryProvider
from spec_orch.services.memory.types import MemoryEntry


class MemoryWriter:
    """Write-focused facade over provider and recorder-backed memory operations."""

    def __init__(self, *, provider: MemoryProvider, service: Any) -> None:
        self._provider = provider
        self._service = service

    def store(self, entry: MemoryEntry) -> str:
        return self._provider.store(entry)

    def forget(self, key: str) -> bool:
        return self._provider.forget(key)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._service, name)
