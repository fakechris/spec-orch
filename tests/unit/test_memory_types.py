"""Tests for memory subsystem types."""

from spec_orch.services.memory.types import MemoryEntry, MemoryLayer, MemoryQuery


class TestMemoryLayer:
    def test_values(self):
        assert MemoryLayer.WORKING == "working"
        assert MemoryLayer.EPISODIC == "episodic"
        assert MemoryLayer.SEMANTIC == "semantic"
        assert MemoryLayer.PROCEDURAL == "procedural"

    def test_from_string(self):
        assert MemoryLayer("episodic") == MemoryLayer.EPISODIC


class TestMemoryEntry:
    def test_roundtrip(self):
        entry = MemoryEntry(
            key="test-key",
            content="hello world",
            layer=MemoryLayer.WORKING,
            tags=["a", "b"],
            metadata={"foo": "bar"},
        )
        d = entry.to_dict()
        restored = MemoryEntry.from_dict(d)
        assert restored.key == entry.key
        assert restored.content == entry.content
        assert restored.layer == entry.layer
        assert restored.tags == entry.tags
        assert restored.metadata == entry.metadata

    def test_touch_updates_timestamp(self):
        entry = MemoryEntry(key="k", content="c", layer=MemoryLayer.WORKING)
        old = entry.updated_at
        entry.touch()
        assert entry.updated_at >= old

    def test_to_dict_layer_is_string(self):
        entry = MemoryEntry(key="k", content="c", layer=MemoryLayer.SEMANTIC)
        d = entry.to_dict()
        assert d["layer"] == "semantic"
        assert isinstance(d["layer"], str)


class TestMemoryQuery:
    def test_defaults(self):
        q = MemoryQuery()
        assert q.text == ""
        assert q.layer is None
        assert q.top_k == 10
        assert q.tags == []
        assert q.filters == {}

    def test_with_layer(self):
        q = MemoryQuery(text="search", layer=MemoryLayer.EPISODIC, top_k=5)
        assert q.layer == MemoryLayer.EPISODIC
        assert q.top_k == 5
