"""Core data types for the memory subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class MemoryLayer(StrEnum):
    """Logical partitions for stored memories."""

    WORKING = "working"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"


@dataclass
class MemoryEntry:
    """A single unit of stored knowledge.

    Each entry belongs to exactly one layer and carries arbitrary metadata
    so higher-level services can attach domain-specific tags without
    changing the core schema.
    """

    key: str
    content: str
    layer: MemoryLayer
    metadata: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def touch(self) -> None:
        """Bump ``updated_at`` to the current time."""
        self.updated_at = datetime.now(UTC).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "content": self.content,
            "layer": self.layer.value,
            "metadata": self.metadata,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryEntry:
        now = datetime.now(UTC).isoformat()
        return cls(
            key=data["key"],
            content=data["content"],
            layer=MemoryLayer(data["layer"]),
            metadata=data.get("metadata", {}),
            tags=data.get("tags", []),
            created_at=data.get("created_at") or now,
            updated_at=data.get("updated_at") or now,
        )


@dataclass
class MemoryQuery:
    """Describes what to recall from memory.

    ``text`` is used for keyword / semantic matching (depending on the
    provider).  ``filters`` are provider-specific key-value constraints
    applied on metadata.
    """

    text: str = ""
    layer: MemoryLayer | None = None
    tags: list[str] = field(default_factory=list)
    filters: dict[str, Any] = field(default_factory=dict)
    top_k: int = 10
