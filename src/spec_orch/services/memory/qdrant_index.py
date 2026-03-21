"""QdrantIndex — optional semantic index layer for memory entries.

Wraps ``qdrant-client`` with ``FastEmbed`` to provide vector search
over memory entries.  Designed to be used alongside
:class:`FileSystemMemoryProvider` — the file layer remains the source
of truth; this layer only accelerates ``recall(query.text)``.

Requires the ``memory`` extra: ``pip install spec-orch[memory]``.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_COLLECTION = "spec_orch_memory"
_DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"


@dataclass
class VectorHit:
    """A single semantic search result."""

    key: str
    score: float


class QdrantIndex:
    """Thin wrapper around Qdrant + FastEmbed for memory entry indexing.

    Parameters
    ----------
    mode:
        ``"local"`` for on-disk persistent storage (default),
        ``"memory"`` for ephemeral in-memory mode,
        ``"server"`` for connecting to a running Qdrant instance.
    path:
        Filesystem path for local mode (ignored for server/memory).
    url:
        Qdrant server URL for server mode.
    collection:
        Qdrant collection name.
    embedding_model:
        FastEmbed model identifier.
    """

    def __init__(
        self,
        *,
        mode: str = "local",
        path: str = ".spec_orch_qdrant",
        url: str | None = None,
        collection: str = _DEFAULT_COLLECTION,
        embedding_model: str = _DEFAULT_EMBEDDING_MODEL,
    ) -> None:
        try:
            from qdrant_client import QdrantClient  # type: ignore[import-untyped,import-not-found]
        except ImportError as exc:
            raise ImportError(
                "qdrant-client is required for vector-enhanced memory. "
                "Install with: pip install spec-orch[memory]"
            ) from exc

        self._collection = collection
        self._embedding_model = embedding_model

        if mode == "memory":
            self._client = QdrantClient(location=":memory:")
        elif mode == "server":
            self._client = QdrantClient(url=url or "http://localhost:6333")
        else:
            self._client = QdrantClient(path=path)

        self._ensure_collection()

    def _ensure_collection(self) -> None:
        """Create collection if it does not exist."""
        from qdrant_client.models import (  # type: ignore[import-untyped,import-not-found]
            Distance,
            VectorParams,
        )

        existing = [c.name for c in self._client.get_collections().collections]
        if self._collection in existing:
            return

        sample_vec = self._embed(["probe"])
        dim = len(sample_vec[0]) if sample_vec else 384

        self._client.create_collection(
            collection_name=self._collection,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
        logger.info(
            "Created Qdrant collection '%s' (dim=%d, model=%s)",
            self._collection,
            dim,
            self._embedding_model,
        )

    def _embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings using FastEmbed."""
        from qdrant_client import (
            models,  # type: ignore[import-untyped,import-not-found]  # noqa: F401
        )

        embeddings = list(
            self._client._get_or_init_model(  # noqa: SLF001
                self._embedding_model
            ).embed(texts)
        )
        return [list(e) for e in embeddings]

    def _key_to_id(self, key: str) -> str:
        """Deterministic point ID from memory key."""
        return hashlib.sha256(key.encode()).hexdigest()[:32]

    def upsert(
        self,
        key: str,
        content: str,
        *,
        layer: str = "",
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Index a memory entry (or update if key already exists)."""
        from qdrant_client.models import (
            PointStruct,  # type: ignore[import-untyped,import-not-found]
        )

        vectors = self._embed([content])
        if not vectors:
            return

        point_id = self._key_to_id(key)
        payload: dict[str, Any] = {
            "key": key,
            "layer": layer,
            "tags": tags or [],
        }
        if metadata:
            payload["metadata"] = metadata

        self._client.upsert(
            collection_name=self._collection,
            points=[PointStruct(id=point_id, vector=vectors[0], payload=payload)],
        )

    def delete(self, key: str) -> None:
        """Remove a memory entry from the index."""
        from qdrant_client.models import (
            PointIdsList,  # type: ignore[import-untyped,import-not-found]
        )

        point_id = self._key_to_id(key)
        self._client.delete(
            collection_name=self._collection,
            points_selector=PointIdsList(points=[point_id]),
        )

    def search(
        self,
        text: str,
        *,
        layer: str | None = None,
        tags: list[str] | None = None,
        top_k: int = 10,
    ) -> list[VectorHit]:
        """Semantic search over indexed entries."""
        from qdrant_client.models import (  # type: ignore[import-untyped,import-not-found]
            FieldCondition,
            Filter,
            MatchValue,
        )

        vectors = self._embed([text])
        if not vectors:
            return []

        conditions: list[FieldCondition] = []
        if layer:
            conditions.append(FieldCondition(key="layer", match=MatchValue(value=layer)))
        if tags:
            for tag in tags:
                conditions.append(FieldCondition(key="tags", match=MatchValue(value=tag)))

        query_filter = Filter(must=conditions) if conditions else None  # type: ignore[arg-type]

        results = self._client.query_points(
            collection_name=self._collection,
            query=vectors[0],
            query_filter=query_filter,
            limit=top_k,
        ).points

        return [
            VectorHit(key=r.payload["key"], score=r.score)
            for r in results
            if r.payload and "key" in r.payload
        ]

    def count(self) -> int:
        """Return total indexed points."""
        info = self._client.get_collection(self._collection)
        return info.points_count or 0

    def reindex(
        self,
        entries: list[tuple[str, str, str, list[str]]],
    ) -> int:
        """Rebuild the entire index from scratch.

        Parameters
        ----------
        entries:
            List of ``(key, content, layer, tags)`` tuples.

        Returns
        -------
        int
            Number of entries indexed.
        """
        self._client.delete_collection(self._collection)
        self._ensure_collection()

        for key, content, layer, tags in entries:
            self.upsert(key, content, layer=layer, tags=tags)

        return len(entries)
