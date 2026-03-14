"""MemoryProvider protocol — the pluggable storage contract."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from spec_orch.services.memory.types import MemoryEntry, MemoryQuery


@runtime_checkable
class MemoryProvider(Protocol):
    """Abstract interface for memory storage backends.

    Implementations may range from a simple file-system store (shipped
    by default) to vector-database adapters (Mem0, Chroma, …).
    All methods are synchronous; async wrappers can be layered on top
    by the ``MemoryService`` if needed.
    """

    def store(self, entry: MemoryEntry) -> str:
        """Persist *entry* and return its key.

        If an entry with the same key already exists the implementation
        must **upsert** — overwrite content / metadata and bump
        ``updated_at``.
        """
        ...

    def recall(self, query: MemoryQuery) -> list[MemoryEntry]:
        """Return entries matching *query*, ordered by relevance.

        At minimum providers must support filtering by ``layer`` and
        ``tags``.  Free-text search in ``query.text`` is optional for
        simple backends and required for vector-enabled ones.
        """
        ...

    def forget(self, key: str) -> bool:
        """Delete the entry identified by *key*.

        Returns ``True`` if the entry existed and was removed.
        """
        ...

    def list_keys(
        self,
        *,
        layer: str | None = None,
        tags: list[str] | None = None,
        limit: int = 100,
    ) -> list[str]:
        """Return keys matching the given filters.

        This is a lightweight alternative to ``recall`` when only keys
        are needed (e.g. for admin / CLI listing).
        """
        ...

    def get(self, key: str) -> MemoryEntry | None:
        """Return a single entry by exact key, or ``None``."""
        ...
