"""Tests for QdrantIndex — semantic vector index for memory entries.

These tests only run if qdrant-client[fastembed] is installed; otherwise
they are automatically skipped.
"""

from __future__ import annotations

import pytest

qdrant_available = True
try:
    from qdrant_client import QdrantClient  # noqa: F401
except ImportError:
    qdrant_available = False

pytestmark = pytest.mark.skipif(
    not qdrant_available,
    reason="qdrant-client[fastembed] not installed",
)


@pytest.fixture()
def index():
    from spec_orch.services.memory.qdrant_index import QdrantIndex

    return QdrantIndex(mode="memory", collection="test_memory")


class TestQdrantIndex:
    def test_upsert_and_search(self, index) -> None:
        index.upsert("k1", "deployment failed in staging", layer="episodic", tags=["issue-result"])
        index.upsert("k2", "all tests passed on main", layer="episodic", tags=["issue-result"])
        index.upsert("k3", "cooking recipe for pasta", layer="semantic", tags=["unrelated"])

        hits = index.search("deploy failure", top_k=3)
        assert len(hits) > 0
        keys = [h.key for h in hits]
        assert "k1" in keys

    def test_search_with_layer_filter(self, index) -> None:
        index.upsert("ep-1", "test failure", layer="episodic")
        index.upsert("sem-1", "test failure", layer="semantic")

        hits = index.search("test failure", layer="episodic", top_k=5)
        keys = [h.key for h in hits]
        assert "ep-1" in keys
        assert "sem-1" not in keys

    def test_search_with_tag_filter(self, index) -> None:
        index.upsert("t1", "api timeout", layer="episodic", tags=["issue-result"])
        index.upsert("t2", "api timeout", layer="episodic", tags=["run-summary"])

        hits = index.search("timeout", tags=["issue-result"], top_k=5)
        keys = [h.key for h in hits]
        assert "t1" in keys
        assert "t2" not in keys

    def test_delete(self, index) -> None:
        index.upsert("del-1", "content to delete", layer="episodic")
        assert index.count() >= 1

        index.delete("del-1")
        hits = index.search("content to delete", top_k=5)
        keys = [h.key for h in hits]
        assert "del-1" not in keys

    def test_upsert_updates_existing(self, index) -> None:
        index.upsert("up-1", "old content", layer="episodic")
        index.upsert("up-1", "new content about authentication", layer="episodic")

        hits = index.search("authentication", top_k=3)
        keys = [h.key for h in hits]
        assert "up-1" in keys

    def test_reindex(self, index) -> None:
        index.upsert("before-1", "old data", layer="episodic")
        count = index.reindex(
            [
                ("re-1", "new data about security", "episodic", ["tag-a"]),
                ("re-2", "new data about performance", "semantic", ["tag-b"]),
            ]
        )
        assert count == 2

        hits = index.search("old data", top_k=5)
        keys = [h.key for h in hits]
        assert "before-1" not in keys

    def test_count(self, index) -> None:
        assert index.count() == 0
        index.upsert("cnt-1", "data", layer="episodic")
        assert index.count() >= 1

    def test_empty_search(self, index) -> None:
        hits = index.search("anything", top_k=5)
        assert hits == []
