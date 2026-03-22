"""Pluggable memory subsystem for spec-orch.

Provides a unified interface for storing and retrieving organizational
knowledge across four layers: working, episodic, semantic, procedural.
"""

from spec_orch.services.memory.analytics import MemoryAnalytics
from spec_orch.services.memory.distiller import MemoryDistiller
from spec_orch.services.memory.fs_provider import FileSystemMemoryProvider
from spec_orch.services.memory.protocol import MemoryProvider
from spec_orch.services.memory.recorder import MemoryRecorder
from spec_orch.services.memory.types import (
    MemoryEntry,
    MemoryLayer,
    MemoryQuery,
)

__all__ = [
    "FileSystemMemoryProvider",
    "MemoryAnalytics",
    "MemoryDistiller",
    "MemoryEntry",
    "MemoryLayer",
    "MemoryProvider",
    "MemoryQuery",
    "MemoryRecorder",
]
