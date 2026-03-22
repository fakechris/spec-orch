"""VectorEnhancedProvider — combines FileSystemMemoryProvider with QdrantIndex.

All writes and reads go through the filesystem provider (source of truth).
When ``query.text`` is provided in a ``recall()`` call and a QdrantIndex is
available, semantic search runs first and results are resolved back to the
filesystem layer for full entry data.

If the Qdrant dependency is not installed or the index is unavailable,
the provider silently degrades to pure filesystem recall.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from spec_orch.services.memory.fs_provider import FileSystemMemoryProvider
from spec_orch.services.memory.types import MemoryEntry, MemoryLayer, MemoryQuery

logger = logging.getLogger(__name__)

_INDEXED_LAYERS = frozenset({MemoryLayer.EPISODIC, MemoryLayer.SEMANTIC})


class VectorEnhancedProvider:
    """MemoryProvider that wraps FS storage with optional Qdrant indexing.

    Parameters
    ----------
    root:
        Filesystem root for Markdown memory files.
    qdrant_config:
        Dict with keys ``mode``, ``path``, ``collection``,
        ``embedding_model``.  If *None* or if ``qdrant-client`` is not
        installed, the provider falls back to pure filesystem mode.
    """

    def __init__(
        self,
        root: Path,
        qdrant_config: dict[str, Any] | None = None,
    ) -> None:
        self._fs = FileSystemMemoryProvider(root)
        self._qdrant = self._init_qdrant(qdrant_config)

    @staticmethod
    def _init_qdrant(
        config: dict[str, Any] | None,
    ) -> Any | None:
        """Try to create a QdrantIndex; return *None* on failure."""
        if not config:
            return None
        try:
            from spec_orch.services.memory.qdrant_index import QdrantIndex

            return QdrantIndex(
                mode=config.get("mode", "local"),
                path=config.get("path", ".spec_orch_qdrant"),
                url=config.get("url"),
                collection=config.get("collection", "spec_orch_memory"),
                embedding_model=config.get("embedding_model", "BAAI/bge-small-zh-v1.5"),
            )
        except Exception:
            logger.warning(
                "Failed to initialise Qdrant index; falling back to filesystem-only recall",
                exc_info=True,
            )
            return None

    # -- MemoryProvider interface ---------------------------------------------

    def store(self, entry: MemoryEntry) -> str:
        key = self._fs.store(entry)
        if self._qdrant and entry.layer in _INDEXED_LAYERS:
            try:
                self._qdrant.upsert(
                    key,
                    entry.content,
                    layer=entry.layer.value,
                    tags=entry.tags,
                    metadata=entry.metadata,
                )
            except Exception:
                logger.warning(
                    "Qdrant upsert failed for key=%s; entry is safely persisted in filesystem",
                    key,
                    exc_info=True,
                )
        return key

    def recall(self, query: MemoryQuery) -> list[MemoryEntry]:
        if not query.text or not self._qdrant:
            return self._fs.recall(query)

        layer_str = query.layer.value if query.layer else None

        if query.layer and query.layer not in _INDEXED_LAYERS:
            return self._fs.recall(query)

        fetch_k = query.top_k * 3 if query.filters else query.top_k

        try:
            hits = self._qdrant.search(
                text=query.text,
                layer=layer_str,
                tags=query.tags or None,
                top_k=fetch_k,
            )
        except Exception:
            logger.warning(
                "Qdrant search failed; falling back to filesystem recall",
                exc_info=True,
            )
            return self._fs.recall(query)

        semantic_keys = [h.key for h in hits]
        fts_keys = self._fs.search_fts(query.text, top_k=fetch_k)

        from spec_orch.services.memory.fs_provider import rrf_fuse

        fused = rrf_fuse(semantic_keys, fts_keys) if fts_keys else semantic_keys

        results: list[MemoryEntry] = []
        for key in fused:
            entry = self._fs.get(key)
            if entry is None:
                continue
            if query.filters and not all(
                entry.metadata.get(k) == v for k, v in query.filters.items()
            ):
                continue
            results.append(entry)
            if len(results) >= query.top_k:
                break

        return results

    def forget(self, key: str) -> bool:
        removed = self._fs.forget(key)
        if removed and self._qdrant:
            try:
                self._qdrant.delete(key)
            except Exception:
                logger.warning("Qdrant delete failed for key=%s", key, exc_info=True)
        return removed

    def list_keys(
        self,
        *,
        layer: str | None = None,
        tags: list[str] | None = None,
        limit: int = 100,
    ) -> list[str]:
        return self._fs.list_keys(layer=layer, tags=tags, limit=limit)

    def list_summaries(
        self,
        *,
        layer: str | None = None,
        tags: list[str] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return self._fs.list_summaries(layer=layer, tags=tags, limit=limit)

    def get(self, key: str) -> MemoryEntry | None:
        return self._fs.get(key)
