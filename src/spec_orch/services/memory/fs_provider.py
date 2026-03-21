"""File-system-backed MemoryProvider.

Each :class:`MemoryEntry` is persisted as a Markdown file with YAML
front-matter.  A lightweight JSON index (``_index.json``) is maintained
alongside the Markdown files for fast key listing and filtering.

Directory layout::

    <root>/
      working/
        <key>.md
      episodic/
        <key>.md
      semantic/
        <key>.md
      procedural/
        <key>.md
      _index.json          # { key: {layer, tags, created_at, updated_at} }
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from spec_orch.services.io import atomic_write_json
from spec_orch.services.memory.types import MemoryEntry, MemoryLayer, MemoryQuery

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_SAFE_KEY_RE = re.compile(r"[^a-zA-Z0-9_\-.]")


def _sanitise_key(key: str) -> str:
    """Turn an arbitrary key string into a filesystem-safe filename stem."""
    return _SAFE_KEY_RE.sub("_", key)[:200]


def _parse_yaml_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Minimal YAML-subset parser for front-matter we control.

    We only emit simple scalars, lists of strings, and flat dicts so a
    full YAML library is not needed.
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text

    meta: dict[str, Any] = {}
    body = text[m.end() :]
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ": " not in line:
            continue
        k, v = line.split(": ", 1)
        k = k.strip()
        v = v.strip()
        if v.startswith("[") and v.endswith("]"):
            meta[k] = [s.strip().strip("'\"") for s in v[1:-1].split(",") if s.strip()]
        elif v in ("true", "True"):
            meta[k] = True
        elif v in ("false", "False"):
            meta[k] = False
        else:
            stripped = v.strip("'\"")
            try:
                meta[k] = int(stripped)
            except ValueError:
                try:
                    meta[k] = float(stripped)
                except ValueError:
                    meta[k] = stripped
    return meta, body


def _render_frontmatter(entry: MemoryEntry) -> str:
    tags_str = "[" + ", ".join(entry.tags) + "]" if entry.tags else "[]"
    lines = [
        "---",
        f"key: {entry.key}",
        f"layer: {entry.layer.value}",
        f"tags: {tags_str}",
        f"created_at: {entry.created_at}",
        f"updated_at: {entry.updated_at}",
    ]
    for mk, mv in sorted(entry.metadata.items()):
        mv_str = "[" + ", ".join(str(x) for x in mv) + "]" if isinstance(mv, list) else str(mv)
        lines.append(f"{mk}: {mv_str}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def _text_matches(query_text: str, content: str) -> bool:
    """Word-level matching: at least half of the query words must appear."""
    words = [w for w in query_text.lower().split() if len(w) > 2]
    if not words:
        return True
    content_lower = content.lower()
    hits = sum(1 for w in words if w in content_lower)
    return hits >= max(1, len(words) // 2)


class FileSystemMemoryProvider:
    """Store memories as Markdown files with YAML front-matter."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._index_path = root / "_index.json"
        self._index: dict[str, dict[str, Any]] = {}
        self._ensure_dirs()
        self._load_index()

    # -- MemoryProvider interface --------------------------------------------

    def store(self, entry: MemoryEntry) -> str:
        entry.touch()
        path = self._entry_path(entry)
        path.parent.mkdir(parents=True, exist_ok=True)

        # If key exists in a *different* layer, remove the old file
        old = self._index.get(entry.key)
        if old and old.get("layer") != entry.layer.value:
            old_path = self._root / old["layer"] / f"{_sanitise_key(entry.key)}.md"
            old_path.unlink(missing_ok=True)

        path.write_text(_render_frontmatter(entry) + entry.content, encoding="utf-8")
        self._index[entry.key] = {
            "layer": entry.layer.value,
            "tags": entry.tags,
            "created_at": entry.created_at,
            "updated_at": entry.updated_at,
        }
        self._save_index()
        return entry.key

    def recall(self, query: MemoryQuery) -> list[MemoryEntry]:
        candidates = self._filtered_keys(
            layer=query.layer.value if query.layer else None,
            tags=query.tags or None,
        )
        results: list[MemoryEntry] = []
        for key in candidates:
            entry = self.get(key)
            if entry is None:
                continue
            if query.filters and not all(
                entry.metadata.get(k) == v for k, v in query.filters.items()
            ):
                continue
            if query.text and not _text_matches(query.text, entry.content):
                continue
            results.append(entry)
            if len(results) >= query.top_k:
                break
        return results

    def forget(self, key: str) -> bool:
        info = self._index.pop(key, None)
        if info is None:
            return False
        path = self._root / info["layer"] / f"{_sanitise_key(key)}.md"
        path.unlink(missing_ok=True)
        self._save_index()
        return True

    def list_keys(
        self,
        *,
        layer: str | None = None,
        tags: list[str] | None = None,
        limit: int = 100,
    ) -> list[str]:
        return self._filtered_keys(layer=layer, tags=tags)[:limit]

    def get(self, key: str) -> MemoryEntry | None:
        info = self._index.get(key)
        if info is None:
            return None
        path = self._root / info["layer"] / f"{_sanitise_key(key)}.md"
        if not path.exists():
            self._index.pop(key, None)
            self._save_index()
            return None
        return self._read_entry(path)

    def list_summaries(
        self,
        *,
        layer: str | None = None,
        tags: list[str] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return lightweight summaries from the index without reading files."""
        keys = self._filtered_keys(layer=layer, tags=tags)[:limit]
        results: list[dict[str, Any]] = []
        for key in keys:
            info = self._index.get(key, {})
            results.append(
                {
                    "key": key,
                    "layer": info.get("layer", "working"),
                    "tags": info.get("tags", []),
                    "created_at": info.get("created_at", ""),
                    "updated_at": info.get("updated_at", ""),
                }
            )
        return results

    # -- internals -----------------------------------------------------------

    def _ensure_dirs(self) -> None:
        for layer in MemoryLayer:
            (self._root / layer.value).mkdir(parents=True, exist_ok=True)

    def _entry_path(self, entry: MemoryEntry) -> Path:
        return self._root / entry.layer.value / f"{_sanitise_key(entry.key)}.md"

    def _load_index(self) -> None:
        if self._index_path.exists():
            try:
                self._index = json.loads(self._index_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Corrupted memory index, rebuilding: %s", exc)
                self._rebuild_index()
        else:
            self._rebuild_index()

    def _save_index(self) -> None:
        atomic_write_json(self._index_path, self._index)

    def _rebuild_index(self) -> None:
        self._index = {}
        for layer in MemoryLayer:
            layer_dir = self._root / layer.value
            if not layer_dir.is_dir():
                continue
            for md_file in layer_dir.glob("*.md"):
                entry = self._read_entry(md_file)
                if entry:
                    self._index[entry.key] = {
                        "layer": entry.layer.value,
                        "tags": entry.tags,
                        "created_at": entry.created_at,
                        "updated_at": entry.updated_at,
                    }
        self._save_index()

    def _read_entry(self, path: Path) -> MemoryEntry | None:
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            return None
        meta, body = _parse_yaml_frontmatter(raw)
        if "key" not in meta:
            return None
        known_keys = {"key", "layer", "tags", "created_at", "updated_at"}
        extra_meta = {k: v for k, v in meta.items() if k not in known_keys}
        return MemoryEntry.from_dict(
            {
                "key": meta["key"],
                "content": body.strip(),
                "layer": meta.get("layer", "working"),
                "metadata": extra_meta,
                "tags": meta.get("tags", []),
                "created_at": meta.get("created_at") or None,
                "updated_at": meta.get("updated_at") or None,
            }
        )

    def _filtered_keys(
        self,
        layer: str | None = None,
        tags: list[str] | None = None,
    ) -> list[str]:
        keys: list[str] = []
        for key, info in self._index.items():
            if layer and info.get("layer") != layer:
                continue
            if tags:
                entry_tags = set(info.get("tags", []))
                if not set(tags).issubset(entry_tags):
                    continue
            keys.append(key)
        return sorted(keys, key=lambda k: self._index[k].get("updated_at", ""), reverse=True)
