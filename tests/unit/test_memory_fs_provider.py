"""Tests for FileSystemMemoryProvider."""

from pathlib import Path

import pytest

from spec_orch.services.memory.fs_provider import (
    FileSystemMemoryProvider,
    _text_matches,
    _tokenize,
)
from spec_orch.services.memory.types import MemoryEntry, MemoryLayer, MemoryQuery


@pytest.fixture()
def provider(tmp_path: Path) -> FileSystemMemoryProvider:
    return FileSystemMemoryProvider(tmp_path / "memory")


class TestStoreAndGet:
    def test_store_creates_file(self, provider: FileSystemMemoryProvider, tmp_path: Path):
        entry = MemoryEntry(key="test-1", content="hello", layer=MemoryLayer.WORKING)
        key = provider.store(entry)
        assert key == "test-1"
        assert (tmp_path / "memory" / "working" / "test-1.md").exists()

    def test_get_returns_stored_entry(self, provider: FileSystemMemoryProvider):
        entry = MemoryEntry(
            key="my-entry",
            content="some content\nwith newlines",
            layer=MemoryLayer.SEMANTIC,
            tags=["tag1", "tag2"],
            metadata={"source": "test"},
        )
        provider.store(entry)
        result = provider.get("my-entry")
        assert result is not None
        assert result.key == "my-entry"
        assert result.content == "some content\nwith newlines"
        assert result.layer == MemoryLayer.SEMANTIC
        assert result.tags == ["tag1", "tag2"]
        assert result.metadata["source"] == "test"

    def test_get_nonexistent_returns_none(self, provider: FileSystemMemoryProvider):
        assert provider.get("does-not-exist") is None

    def test_upsert_overwrites(self, provider: FileSystemMemoryProvider):
        entry1 = MemoryEntry(key="k", content="v1", layer=MemoryLayer.WORKING)
        provider.store(entry1)
        entry2 = MemoryEntry(key="k", content="v2", layer=MemoryLayer.WORKING)
        provider.store(entry2)
        result = provider.get("k")
        assert result is not None
        assert result.content == "v2"

    def test_upsert_across_layers_moves_file(
        self, provider: FileSystemMemoryProvider, tmp_path: Path
    ):
        entry1 = MemoryEntry(key="moveable", content="v1", layer=MemoryLayer.WORKING)
        provider.store(entry1)
        assert (tmp_path / "memory" / "working" / "moveable.md").exists()

        entry2 = MemoryEntry(key="moveable", content="v2", layer=MemoryLayer.EPISODIC)
        provider.store(entry2)
        assert not (tmp_path / "memory" / "working" / "moveable.md").exists()
        assert (tmp_path / "memory" / "episodic" / "moveable.md").exists()


class TestForget:
    def test_forget_removes_entry(self, provider: FileSystemMemoryProvider):
        provider.store(MemoryEntry(key="gone", content="bye", layer=MemoryLayer.WORKING))
        assert provider.forget("gone") is True
        assert provider.get("gone") is None

    def test_forget_nonexistent_returns_false(self, provider: FileSystemMemoryProvider):
        assert provider.forget("nope") is False


class TestListKeys:
    def test_list_all(self, provider: FileSystemMemoryProvider):
        provider.store(MemoryEntry(key="a", content="1", layer=MemoryLayer.WORKING))
        provider.store(MemoryEntry(key="b", content="2", layer=MemoryLayer.EPISODIC))
        keys = provider.list_keys()
        assert set(keys) == {"a", "b"}

    def test_filter_by_layer(self, provider: FileSystemMemoryProvider):
        provider.store(MemoryEntry(key="w1", content="1", layer=MemoryLayer.WORKING))
        provider.store(MemoryEntry(key="e1", content="2", layer=MemoryLayer.EPISODIC))
        keys = provider.list_keys(layer="working")
        assert keys == ["w1"]

    def test_filter_by_tags(self, provider: FileSystemMemoryProvider):
        provider.store(
            MemoryEntry(key="tagged", content="1", layer=MemoryLayer.WORKING, tags=["important"])
        )
        provider.store(MemoryEntry(key="untagged", content="2", layer=MemoryLayer.WORKING))
        keys = provider.list_keys(tags=["important"])
        assert keys == ["tagged"]

    def test_limit(self, provider: FileSystemMemoryProvider):
        for i in range(20):
            provider.store(
                MemoryEntry(key=f"item-{i:02d}", content=str(i), layer=MemoryLayer.WORKING)
            )
        keys = provider.list_keys(limit=5)
        assert len(keys) == 5


class TestRecall:
    def test_text_search(self, provider: FileSystemMemoryProvider):
        provider.store(
            MemoryEntry(key="apple", content="I like apples", layer=MemoryLayer.SEMANTIC)
        )
        provider.store(
            MemoryEntry(key="banana", content="I like bananas", layer=MemoryLayer.SEMANTIC)
        )
        results = provider.recall(MemoryQuery(text="apple"))
        assert len(results) == 1
        assert results[0].key == "apple"

    def test_layer_filter(self, provider: FileSystemMemoryProvider):
        provider.store(MemoryEntry(key="w", content="work", layer=MemoryLayer.WORKING))
        provider.store(MemoryEntry(key="e", content="event", layer=MemoryLayer.EPISODIC))
        results = provider.recall(MemoryQuery(layer=MemoryLayer.WORKING))
        assert len(results) == 1
        assert results[0].key == "w"

    def test_metadata_filter(self, provider: FileSystemMemoryProvider):
        provider.store(
            MemoryEntry(key="x", content="c", layer=MemoryLayer.WORKING, metadata={"src": "a"})
        )
        provider.store(
            MemoryEntry(key="y", content="c", layer=MemoryLayer.WORKING, metadata={"src": "b"})
        )
        results = provider.recall(MemoryQuery(filters={"src": "b"}))
        assert len(results) == 1
        assert results[0].key == "y"

    def test_top_k(self, provider: FileSystemMemoryProvider):
        for i in range(10):
            provider.store(
                MemoryEntry(key=f"item-{i}", content="common text", layer=MemoryLayer.WORKING)
            )
        results = provider.recall(MemoryQuery(text="common", top_k=3))
        assert len(results) == 3


class TestTokenize:
    def test_english_splits_on_whitespace(self):
        tokens = _tokenize("hello world test")
        assert "hello" in tokens
        assert "world" in tokens
        assert "test" in tokens

    def test_english_filters_short_words(self):
        tokens = _tokenize("I am a big dog")
        assert "I" not in tokens
        assert "am" not in tokens
        assert "a" not in tokens
        assert "big" in tokens
        assert "dog" in tokens

    def test_chinese_uses_jieba(self):
        tokens = _tokenize("数据库连接超时")
        assert len(tokens) >= 2
        assert any("数据" in t for t in tokens)

    def test_mixed_chinese_english(self):
        tokens = _tokenize("PostgreSQL 数据库连接池耗尽")
        assert len(tokens) >= 2

    def test_empty_input(self):
        assert _tokenize("") == []


class TestTextMatchesChinese:
    def test_chinese_semantic_overlap(self):
        assert _text_matches(
            "数据库连接问题", "部署到 staging 环境时数据库连接超时，PostgreSQL 连接池耗尽"
        )

    def test_chinese_no_overlap(self):
        assert not _text_matches(
            "前端样式调整", "部署到 staging 环境时数据库连接超时，PostgreSQL 连接池耗尽"
        )

    def test_chinese_partial_overlap(self):
        assert _text_matches("接口响应时间", "用户登录接口响应时间从 200ms 上升到 2000ms")

    def test_english_still_works(self):
        assert _text_matches(
            "database connection error", "the database had a connection timeout error"
        )

    def test_english_no_match(self):
        assert not _text_matches(
            "frontend styling issue", "the database had a connection timeout error"
        )

    def test_empty_query_matches_all(self):
        assert _text_matches("", "anything here")

    def test_short_chinese_query(self):
        assert _text_matches("数据库", "数据库连接池耗尽")

    def test_single_char_query_does_not_match_all(self):
        assert not _text_matches("我是谁", "数据库连接池耗尽")


class TestRecallChinese:
    def test_chinese_text_recall(self, provider: FileSystemMemoryProvider):
        provider.store(
            MemoryEntry(
                key="db-fail",
                content="部署到 staging 环境时数据库连接超时，PostgreSQL 连接池耗尽",
                layer=MemoryLayer.EPISODIC,
                tags=["issue-result"],
            )
        )
        provider.store(
            MemoryEntry(
                key="lint-fail",
                content="CI 流水线中 lint 检查失败：ruff 报告 E501 行超长",
                layer=MemoryLayer.EPISODIC,
                tags=["issue-result"],
            )
        )
        results = provider.recall(
            MemoryQuery(text="数据库连接问题", layer=MemoryLayer.EPISODIC, tags=["issue-result"])
        )
        assert len(results) >= 1
        assert results[0].key == "db-fail"


class TestIndexRebuild:
    def test_rebuild_from_files(self, tmp_path: Path):
        root = tmp_path / "mem"
        provider = FileSystemMemoryProvider(root)
        provider.store(MemoryEntry(key="persist", content="data", layer=MemoryLayer.SEMANTIC))

        # Remove SQLite index and create a new provider — should rebuild
        (root / "_index.db").unlink()
        for wal in root.glob("_index.db*"):
            wal.unlink(missing_ok=True)
        provider2 = FileSystemMemoryProvider(root)
        assert provider2.get("persist") is not None
        assert provider2.get("persist").content == "data"

    def test_corrupted_index_triggers_rebuild(self, tmp_path: Path):
        root = tmp_path / "mem"
        provider = FileSystemMemoryProvider(root)
        provider.store(MemoryEntry(key="safe", content="ok", layer=MemoryLayer.WORKING))

        # Corrupt the SQLite file — provider should rebuild from markdown
        (root / "_index.db").write_bytes(b"not a database!")
        for wal in root.glob("_index.db-*"):
            wal.unlink(missing_ok=True)
        provider2 = FileSystemMemoryProvider(root)
        assert provider2.get("safe") is not None

    def test_migrate_from_legacy_json(self, tmp_path: Path):
        """Legacy _index.json is auto-migrated to SQLite on first startup."""
        import json

        root = tmp_path / "mem"
        root.mkdir(parents=True)
        for layer in ("working", "episodic", "semantic", "procedural"):
            (root / layer).mkdir()

        # Write a markdown file + legacy JSON index
        md_content = "---\nkey: old-entry\nlayer: semantic\ntags: [legacy]\n---\nhello legacy"
        (root / "semantic" / "old-entry.md").write_text(md_content)
        legacy_index = {
            "old-entry": {
                "layer": "semantic",
                "tags": ["legacy"],
                "created_at": "2025-01-01",
                "updated_at": "2025-01-01",
            }
        }
        (root / "_index.json").write_text(json.dumps(legacy_index))

        provider = FileSystemMemoryProvider(root)
        entry = provider.get("old-entry")
        assert entry is not None
        assert entry.content == "hello legacy"
        assert entry.tags == ["legacy"]

        # JSON should be renamed
        assert not (root / "_index.json").exists()
        assert (root / "_index.json.migrated").exists()
