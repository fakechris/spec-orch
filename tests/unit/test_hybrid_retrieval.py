"""Tests for Memory vNext Phase 3: Hybrid Retrieval (SON-232)."""

from pathlib import Path

import pytest

from spec_orch.services.memory.fs_provider import (
    FileSystemMemoryProvider,
    _fts5_available,
    rrf_fuse,
)
from spec_orch.services.memory.types import MemoryEntry, MemoryLayer, MemoryQuery


@pytest.fixture()
def provider(tmp_path: Path) -> FileSystemMemoryProvider:
    return FileSystemMemoryProvider(tmp_path / "memory")


class TestRRFFusion:
    def test_single_list(self):
        result = rrf_fuse(["a", "b", "c"])
        assert result == ["a", "b", "c"]

    def test_two_identical_lists_preserve_order(self):
        result = rrf_fuse(["a", "b", "c"], ["a", "b", "c"])
        assert result == ["a", "b", "c"]

    def test_different_lists_merge(self):
        result = rrf_fuse(["a", "b"], ["c", "a"])
        assert result[0] == "a"
        assert set(result) == {"a", "b", "c"}

    def test_disjoint_lists(self):
        result = rrf_fuse(["a", "b"], ["c", "d"])
        assert len(result) == 4

    def test_empty_list(self):
        result = rrf_fuse([], ["a", "b"])
        assert result == ["a", "b"]

    def test_custom_k(self):
        r1 = rrf_fuse(["a", "b"], ["b", "a"], k=1)
        assert set(r1) == {"a", "b"}

    def test_three_lists(self):
        result = rrf_fuse(["a", "b"], ["b", "c"], ["c", "a"])
        assert len(result) == 3


class TestFTS5:
    def test_fts5_available_check(self, provider: FileSystemMemoryProvider):
        assert _fts5_available(provider._db) is True

    def test_fts_enabled_on_init(self, provider: FileSystemMemoryProvider):
        assert provider._fts_enabled is True

    def test_store_populates_fts(self, provider: FileSystemMemoryProvider):
        provider.store(
            MemoryEntry(
                key="doc-1",
                content="Python is a great programming language",
                layer=MemoryLayer.SEMANTIC,
            )
        )
        results = provider.search_fts("Python programming")
        assert "doc-1" in results

    def test_fts_returns_empty_for_no_match(self, provider: FileSystemMemoryProvider):
        provider.store(MemoryEntry(key="doc-1", content="hello world", layer=MemoryLayer.WORKING))
        results = provider.search_fts("zyxwvut")
        assert results == []

    def test_fts_empty_query(self, provider: FileSystemMemoryProvider):
        assert provider.search_fts("") == []
        assert provider.search_fts("   ") == []

    def test_fts_updates_on_overwrite(self, provider: FileSystemMemoryProvider):
        provider.store(MemoryEntry(key="doc-1", content="alpha beta", layer=MemoryLayer.SEMANTIC))
        provider.store(MemoryEntry(key="doc-1", content="gamma delta", layer=MemoryLayer.SEMANTIC))
        assert provider.search_fts("gamma") == ["doc-1"]
        assert provider.search_fts("alpha") == []

    def test_forget_removes_from_fts(self, provider: FileSystemMemoryProvider):
        provider.store(
            MemoryEntry(key="doc-1", content="searchable text", layer=MemoryLayer.SEMANTIC)
        )
        assert provider.search_fts("searchable") == ["doc-1"]
        provider.forget("doc-1")
        assert provider.search_fts("searchable") == []


class TestHybridRecall:
    def test_recall_uses_fts_when_text_given(self, provider: FileSystemMemoryProvider):
        for i, text in enumerate(
            ["error in authentication module", "fix database connection", "linting check"]
        ):
            provider.store(MemoryEntry(key=f"e{i}", content=text, layer=MemoryLayer.EPISODIC))
        results = provider.recall(
            MemoryQuery(text="authentication error", layer=MemoryLayer.EPISODIC, top_k=3)
        )
        keys = [r.key for r in results]
        assert "e0" in keys

    def test_recall_respects_layer_filter_with_fts(self, provider: FileSystemMemoryProvider):
        provider.store(
            MemoryEntry(key="ep1", content="special keyword xyz", layer=MemoryLayer.EPISODIC)
        )
        provider.store(
            MemoryEntry(key="sem1", content="special keyword xyz", layer=MemoryLayer.SEMANTIC)
        )
        results = provider.recall(
            MemoryQuery(text="special keyword", layer=MemoryLayer.EPISODIC, top_k=5)
        )
        keys = [r.key for r in results]
        assert "ep1" in keys
        assert "sem1" not in keys

    def test_recall_respects_metadata_filter(self, provider: FileSystemMemoryProvider):
        provider.store(
            MemoryEntry(
                key="m1",
                content="verification failed",
                layer=MemoryLayer.EPISODIC,
                metadata={"succeeded": False},
            )
        )
        provider.store(
            MemoryEntry(
                key="m2",
                content="verification passed",
                layer=MemoryLayer.EPISODIC,
                metadata={"succeeded": True},
            )
        )
        results = provider.recall(
            MemoryQuery(
                text="verification",
                layer=MemoryLayer.EPISODIC,
                filters={"succeeded": False},
                top_k=5,
            )
        )
        assert len(results) == 1
        assert results[0].key == "m1"

    def test_recall_without_text_skips_fts(self, provider: FileSystemMemoryProvider):
        provider.store(MemoryEntry(key="a", content="anything", layer=MemoryLayer.WORKING))
        results = provider.recall(MemoryQuery(layer=MemoryLayer.WORKING, top_k=5))
        assert len(results) == 1


class TestRebuildIndexWithFTS:
    def test_rebuild_repopulates_fts(self, provider: FileSystemMemoryProvider):
        provider.store(
            MemoryEntry(
                key="before-rebuild",
                content="unique content for rebuild test",
                layer=MemoryLayer.SEMANTIC,
            )
        )
        provider._db.execute("DELETE FROM memory_fts")
        provider._db.commit()
        assert provider.search_fts("rebuild") == []

        provider._rebuild_index()
        results = provider.search_fts("rebuild")
        assert "before-rebuild" in results
