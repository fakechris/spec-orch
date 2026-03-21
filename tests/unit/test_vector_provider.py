"""Tests for VectorEnhancedProvider — filesystem + optional Qdrant index."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from spec_orch.services.memory.types import MemoryEntry, MemoryLayer, MemoryQuery
from spec_orch.services.memory.vector_provider import VectorEnhancedProvider


@pytest.fixture()
def mem_root(tmp_path: Path) -> Path:
    return tmp_path / "memory"


class TestVectorEnhancedProviderFallback:
    """When Qdrant is not available, provider degrades to pure FS."""

    def test_store_and_recall_without_qdrant(self, mem_root: Path) -> None:
        provider = VectorEnhancedProvider(mem_root, qdrant_config=None)
        entry = MemoryEntry(
            key="test-1",
            content="deployment failed on staging",
            layer=MemoryLayer.EPISODIC,
            tags=["issue-result"],
            metadata={"succeeded": False},
        )
        key = provider.store(entry)
        assert key == "test-1"

        results = provider.recall(
            MemoryQuery(layer=MemoryLayer.EPISODIC, tags=["issue-result"], top_k=5)
        )
        assert len(results) == 1
        assert results[0].key == "test-1"

    def test_forget_without_qdrant(self, mem_root: Path) -> None:
        provider = VectorEnhancedProvider(mem_root, qdrant_config=None)
        entry = MemoryEntry(
            key="forget-me",
            content="old data",
            layer=MemoryLayer.SEMANTIC,
        )
        provider.store(entry)
        assert provider.forget("forget-me")
        assert provider.get("forget-me") is None

    def test_list_keys_without_qdrant(self, mem_root: Path) -> None:
        provider = VectorEnhancedProvider(mem_root, qdrant_config=None)
        for i in range(3):
            provider.store(MemoryEntry(key=f"k-{i}", content=f"c-{i}", layer=MemoryLayer.EPISODIC))
        keys = provider.list_keys(layer="episodic")
        assert len(keys) == 3


class TestVectorEnhancedProviderWithMockQdrant:
    """Test integration when Qdrant is mocked."""

    @pytest.fixture()
    def mock_qdrant(self):
        from spec_orch.services.memory.qdrant_index import VectorHit

        idx = MagicMock()
        idx.search.return_value = [VectorHit(key="match-1", score=0.95)]
        idx.upsert.return_value = None
        idx.delete.return_value = None
        return idx

    def test_store_indexes_episodic_and_semantic(
        self, mem_root: Path, mock_qdrant: MagicMock
    ) -> None:
        provider = VectorEnhancedProvider(mem_root, qdrant_config=None)
        provider._qdrant = mock_qdrant

        provider.store(
            MemoryEntry(
                key="ep-1",
                content="test failure",
                layer=MemoryLayer.EPISODIC,
                tags=["issue-result"],
            )
        )
        mock_qdrant.upsert.assert_called_once()
        mock_qdrant.reset_mock()

        provider.store(
            MemoryEntry(
                key="sem-1",
                content="run summary",
                layer=MemoryLayer.SEMANTIC,
                tags=["run-summary"],
            )
        )
        mock_qdrant.upsert.assert_called_once()

    def test_store_skips_working_layer(self, mem_root: Path, mock_qdrant: MagicMock) -> None:
        provider = VectorEnhancedProvider(mem_root, qdrant_config=None)
        provider._qdrant = mock_qdrant

        provider.store(MemoryEntry(key="w-1", content="temp", layer=MemoryLayer.WORKING))
        mock_qdrant.upsert.assert_not_called()

    def test_store_skips_procedural_layer(self, mem_root: Path, mock_qdrant: MagicMock) -> None:
        provider = VectorEnhancedProvider(mem_root, qdrant_config=None)
        provider._qdrant = mock_qdrant

        provider.store(MemoryEntry(key="p-1", content="adr", layer=MemoryLayer.PROCEDURAL))
        mock_qdrant.upsert.assert_not_called()

    def test_recall_with_text_uses_qdrant_search(
        self, mem_root: Path, mock_qdrant: MagicMock
    ) -> None:
        provider = VectorEnhancedProvider(mem_root, qdrant_config=None)
        provider._qdrant = mock_qdrant

        provider.store(
            MemoryEntry(
                key="match-1",
                content="staging deploy crash",
                layer=MemoryLayer.EPISODIC,
                tags=["issue-result"],
            )
        )

        results = provider.recall(
            MemoryQuery(
                text="deployment failure",
                layer=MemoryLayer.EPISODIC,
                tags=["issue-result"],
                top_k=5,
            )
        )

        mock_qdrant.search.assert_called_once()
        assert len(results) == 1
        assert results[0].key == "match-1"

    def test_recall_without_text_uses_fs(self, mem_root: Path, mock_qdrant: MagicMock) -> None:
        provider = VectorEnhancedProvider(mem_root, qdrant_config=None)
        provider._qdrant = mock_qdrant

        provider.store(
            MemoryEntry(
                key="fs-1",
                content="data",
                layer=MemoryLayer.EPISODIC,
                tags=["tag-a"],
            )
        )

        results = provider.recall(MemoryQuery(layer=MemoryLayer.EPISODIC, tags=["tag-a"], top_k=5))
        mock_qdrant.search.assert_not_called()
        assert len(results) == 1

    def test_recall_working_layer_skips_qdrant(
        self, mem_root: Path, mock_qdrant: MagicMock
    ) -> None:
        provider = VectorEnhancedProvider(mem_root, qdrant_config=None)
        provider._qdrant = mock_qdrant

        provider.store(MemoryEntry(key="w-1", content="temp", layer=MemoryLayer.WORKING))

        provider.recall(MemoryQuery(text="temp", layer=MemoryLayer.WORKING, top_k=5))
        mock_qdrant.search.assert_not_called()

    def test_forget_deletes_from_qdrant(self, mem_root: Path, mock_qdrant: MagicMock) -> None:
        provider = VectorEnhancedProvider(mem_root, qdrant_config=None)
        provider._qdrant = mock_qdrant

        provider.store(MemoryEntry(key="del-1", content="x", layer=MemoryLayer.EPISODIC))
        provider.forget("del-1")
        mock_qdrant.delete.assert_called_once_with("del-1")

    def test_qdrant_upsert_failure_does_not_block_store(
        self, mem_root: Path, mock_qdrant: MagicMock
    ) -> None:
        mock_qdrant.upsert.side_effect = RuntimeError("Qdrant down")
        provider = VectorEnhancedProvider(mem_root, qdrant_config=None)
        provider._qdrant = mock_qdrant

        key = provider.store(
            MemoryEntry(
                key="resilient-1",
                content="data",
                layer=MemoryLayer.EPISODIC,
            )
        )
        assert key == "resilient-1"
        assert provider.get("resilient-1") is not None

    def test_qdrant_search_failure_falls_back_to_fs(
        self, mem_root: Path, mock_qdrant: MagicMock
    ) -> None:
        mock_qdrant.search.side_effect = RuntimeError("Qdrant down")
        provider = VectorEnhancedProvider(mem_root, qdrant_config=None)
        provider._qdrant = mock_qdrant

        provider.store(
            MemoryEntry(
                key="fb-1",
                content="fallback content",
                layer=MemoryLayer.EPISODIC,
                tags=["test"],
            )
        )

        results = provider.recall(
            MemoryQuery(text="fallback", layer=MemoryLayer.EPISODIC, tags=["test"], top_k=5)
        )
        assert len(results) == 1
        assert results[0].key == "fb-1"


class TestQdrantConfigLoading:
    """Test that TOML config is loaded and parsed correctly."""

    def test_load_qdrant_config_from_toml(self, tmp_path: Path) -> None:
        from spec_orch.services.memory.service import _load_qdrant_config

        toml_content = b"""
[memory]
provider = "filesystem_qdrant"

[memory.qdrant]
mode = "local"
path = ".spec_orch_qdrant"
collection = "memory"
embedding_model = "BAAI/bge-small-zh-v1.5"
"""
        (tmp_path / "spec-orch.toml").write_bytes(toml_content)
        config = _load_qdrant_config(tmp_path)
        assert config is not None
        assert config["mode"] == "local"
        assert config["embedding_model"] == "BAAI/bge-small-zh-v1.5"

    def test_load_qdrant_config_returns_none_without_section(self, tmp_path: Path) -> None:
        from spec_orch.services.memory.service import _load_qdrant_config

        toml_content = b"""
[planner]
model = "gpt-4o"
"""
        (tmp_path / "spec-orch.toml").write_bytes(toml_content)
        assert _load_qdrant_config(tmp_path) is None

    def test_load_qdrant_config_returns_none_wrong_provider(self, tmp_path: Path) -> None:
        from spec_orch.services.memory.service import _load_qdrant_config

        toml_content = b"""
[memory]
provider = "redis"
"""
        (tmp_path / "spec-orch.toml").write_bytes(toml_content)
        assert _load_qdrant_config(tmp_path) is None

    def test_load_qdrant_config_returns_none_no_toml(self, tmp_path: Path) -> None:
        from spec_orch.services.memory.service import _load_qdrant_config

        assert _load_qdrant_config(tmp_path) is None
