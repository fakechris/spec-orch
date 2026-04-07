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
_REINDEX_BATCH_SIZE = 64


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
            from fastembed import TextEmbedding  # type: ignore[import-untyped,import-not-found]
            from qdrant_client import QdrantClient  # type: ignore[import-untyped,import-not-found]
        except ImportError as exc:
            raise ImportError(
                "qdrant-client[fastembed] is required for vector-enhanced memory. "
                "Install with: pip install spec-orch[memory]"
            ) from exc

        self._collection = collection
        self._embedding_model = embedding_model
        self._embedder = TextEmbedding(embedding_model)

        _VALID_MODES = {"local", "memory", "server"}
        if mode not in _VALID_MODES:
            raise ValueError(f"Invalid Qdrant mode '{mode}'; expected one of {_VALID_MODES}")

        if mode == "memory":
            self._client = QdrantClient(location=":memory:")
        elif mode == "server":
            self._client = QdrantClient(url=url or "http://localhost:6333")
        else:
            self._client = QdrantClient(path=path)

        self._ensure_collection()

    @staticmethod
    def _extract_vector_dim(vectors_config: Any) -> int | None:
        """Extract dimension from vectors config, handling both named and unnamed."""
        if hasattr(vectors_config, "size"):
            return vectors_config.size  # type: ignore[no-any-return]
        if isinstance(vectors_config, dict):
            for v in vectors_config.values():
                if hasattr(v, "size"):
                    return v.size  # type: ignore[no-any-return]
        return None

    def _ensure_collection(self) -> None:
        """Create collection if it does not exist, or validate dimension match."""
        from qdrant_client.models import (  # type: ignore[import-untyped,import-not-found]
            Distance,
            VectorParams,
        )

        sample_vec = self._embed(["probe"])
        if not sample_vec or not sample_vec[0]:
            raise RuntimeError(
                f"Failed to determine embedding dimension for model {self._embedding_model}"
            )
        dim = len(sample_vec[0])

        existing = [c.name for c in self._client.get_collections().collections]
        if self._collection in existing:
            info = self._client.get_collection(self._collection)
            existing_dim = self._extract_vector_dim(info.config.params.vectors)
            if existing_dim is None:
                logger.warning(
                    "Cannot determine dimension for collection '%s'; "
                    "dropping and recreating to be safe",
                    self._collection,
                )
                self._client.delete_collection(self._collection)
            elif existing_dim != dim:
                logger.warning(
                    "Embedding dimension mismatch: collection '%s' has dim=%d "
                    "but model '%s' produces dim=%d — dropping and recreating",
                    self._collection,
                    existing_dim,
                    self._embedding_model,
                    dim,
                )
                self._client.delete_collection(self._collection)
            else:
                return

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
        embeddings = list(self._embedder.embed(texts))
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
            # Promote filterable fields to top-level for FieldCondition pushdown.
            for filterable_key in ("entity_scope", "entity_id", "relation_type"):
                if filterable_key in metadata:
                    payload[filterable_key] = metadata[filterable_key]

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
        entity_scope: str | None = None,
        entity_id: str | None = None,
        exclude_relation_types: list[str] | None = None,
        top_k: int = 10,
    ) -> list[VectorHit]:
        """Semantic search over indexed entries.

        Pushes ``entity_scope``, ``entity_id``, and ``exclude_relation_types``
        as Qdrant FieldConditions so filtering happens server-side instead of
        in Python post-filter.
        """
        from qdrant_client.models import (  # type: ignore[import-untyped,import-not-found]
            FieldCondition,
            Filter,
            MatchAny,
            MatchValue,
        )

        vectors = self._embed([text])
        if not vectors:
            return []

        must: list[FieldCondition] = []
        if layer:
            must.append(FieldCondition(key="layer", match=MatchValue(value=layer)))
        if tags:
            for tag in tags:
                must.append(FieldCondition(key="tags", match=MatchValue(value=tag)))
        if entity_scope:
            must.append(FieldCondition(key="entity_scope", match=MatchValue(value=entity_scope)))
        if entity_id:
            must.append(FieldCondition(key="entity_id", match=MatchValue(value=entity_id)))

        must_not: list[FieldCondition] = []
        if exclude_relation_types:
            must_not.append(
                FieldCondition(key="relation_type", match=MatchAny(any=exclude_relation_types))
            )

        query_filter: Filter | None = None
        if must or must_not:
            query_filter = Filter(
                must=must or None,  # type: ignore[arg-type]
                must_not=must_not or None,  # type: ignore[arg-type]
            )

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
        entries: list[tuple[str, str, str, list[str], dict[str, Any]]],
    ) -> int:
        """Rebuild the entire index from scratch.

        Parameters
        ----------
        entries:
            List of ``(key, content, layer, tags, metadata)`` tuples.

        Returns
        -------
        int
            Number of entries indexed.
        """
        from qdrant_client.models import (
            PointStruct,  # type: ignore[import-untyped,import-not-found]
        )

        self._client.delete_collection(self._collection)
        self._ensure_collection()

        for i in range(0, len(entries), _REINDEX_BATCH_SIZE):
            batch = entries[i : i + _REINDEX_BATCH_SIZE]
            contents = [e[1] for e in batch]
            vectors = self._embed(contents)
            if not vectors:
                continue

            points = [
                PointStruct(
                    id=self._key_to_id(entry[0]),
                    vector=vectors[j],
                    payload={
                        "key": entry[0],
                        "layer": entry[2],
                        "tags": entry[3] or [],
                        **({"metadata": entry[4]} if entry[4] else {}),
                    },
                )
                for j, entry in enumerate(batch)
                if j < len(vectors)
            ]
            if points:
                self._client.upsert(
                    collection_name=self._collection,
                    points=points,
                )

        return len(entries)
