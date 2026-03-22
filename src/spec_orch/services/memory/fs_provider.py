"""File-system-backed MemoryProvider.

Each :class:`MemoryEntry` is persisted as a Markdown file with YAML
front-matter.  A SQLite database (``_index.db``) is maintained
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
      _index.db            # SQLite WAL — replaces legacy _index.json
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

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


_CJK_RANGE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")


def _tokenize(text: str) -> list[str]:
    """Split text into meaningful tokens with CJK-aware segmentation.

    Uses jieba when installed (``pip install spec-orch[cjk]``).
    Falls back to character bigrams for CJK text when jieba is unavailable.
    """
    text = text.lower()
    if _CJK_RANGE.search(text):
        try:
            import jieba  # type: ignore[import-untyped]  # lazy: ~1s dict load on first call

            tokens = [w.strip() for w in jieba.cut(text) if w.strip()]
            multi = [w for w in tokens if len(w) > 1]
            return multi if multi else tokens
        except ImportError:
            chars = [c for c in text if _CJK_RANGE.match(c)]
            if len(chars) < 2:
                return chars
            return [chars[i] + chars[i + 1] for i in range(len(chars) - 1)]
    return [w for w in text.split() if len(w) > 2]


def _text_matches(query_text: str, content: str) -> bool:
    """Word-level matching: at least half of the query tokens must appear (rounded up)."""
    words = _tokenize(query_text)
    if not words:
        return True
    content_lower = content.lower()
    hits = sum(1 for w in words if w in content_lower)
    threshold = max(1, (len(words) + 1) // 2)
    return hits >= threshold


class FileSystemMemoryProvider:
    """Store memories as Markdown files with YAML front-matter.

    Uses a SQLite database (WAL mode) for the key index instead of a
    JSON file.  This avoids O(N) full-rewrite on every ``store()`` and
    supports efficient filtered queries via SQL indexes.
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._db_path = root / "_index.db"
        self._lock = threading.Lock()
        self._ensure_dirs()
        self._db = self._open_db()
        self._maybe_migrate_json()

    # -- MemoryProvider interface --------------------------------------------

    def store(self, entry: MemoryEntry) -> str:
        entry.touch()
        path = self._entry_path(entry)
        path.parent.mkdir(parents=True, exist_ok=True)

        with self._lock:
            row = self._db.execute(
                "SELECT layer FROM memory_index WHERE key = ?", (entry.key,)
            ).fetchone()
            if row and row[0] != entry.layer.value:
                old_path = self._root / row[0] / f"{_sanitise_key(entry.key)}.md"
                old_path.unlink(missing_ok=True)

            path.write_text(_render_frontmatter(entry) + entry.content, encoding="utf-8")
            tags_json = json.dumps(entry.tags, ensure_ascii=False)
            self._db.execute(
                """INSERT OR REPLACE INTO memory_index
                   (key, layer, tags, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (entry.key, entry.layer.value, tags_json, entry.created_at, entry.updated_at),
            )
            self._db.commit()
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
        with self._lock:
            row = self._db.execute(
                "SELECT layer FROM memory_index WHERE key = ?", (key,)
            ).fetchone()
            if row is None:
                return False
            path = self._root / row[0] / f"{_sanitise_key(key)}.md"
            path.unlink(missing_ok=True)
            self._db.execute("DELETE FROM memory_index WHERE key = ?", (key,))
            self._db.commit()
        return True

    def list_keys(
        self,
        *,
        layer: str | None = None,
        tags: list[str] | None = None,
        limit: int = 100,
    ) -> list[str]:
        return self._filtered_keys(layer=layer, tags=tags, limit=limit)

    def get(self, key: str) -> MemoryEntry | None:
        row = self._db.execute("SELECT layer FROM memory_index WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        path = self._root / row[0] / f"{_sanitise_key(key)}.md"
        if not path.exists():
            with self._lock:
                self._db.execute("DELETE FROM memory_index WHERE key = ?", (key,))
                self._db.commit()
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
        sql = "SELECT key, layer, tags, created_at, updated_at FROM memory_index"
        params: list[Any] = []
        clauses: list[str] = []
        if layer:
            clauses.append("layer = ?")
            params.append(layer)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY updated_at DESC"
        if limit:
            sql += " LIMIT ?"
            params.append(limit)

        rows = self._db.execute(sql, params).fetchall()
        results: list[dict[str, Any]] = []
        for key, lyr, tags_json, created, updated in rows:
            row_tags: list[str] = json.loads(tags_json) if tags_json else []
            if tags and not set(tags).issubset(set(row_tags)):
                continue
            results.append(
                {
                    "key": key,
                    "layer": lyr,
                    "tags": row_tags,
                    "created_at": created or "",
                    "updated_at": updated or "",
                }
            )
        return results

    # -- internals -----------------------------------------------------------

    def _ensure_dirs(self) -> None:
        for layer in MemoryLayer:
            (self._root / layer.value).mkdir(parents=True, exist_ok=True)

    def _entry_path(self, entry: MemoryEntry) -> Path:
        return self._root / entry.layer.value / f"{_sanitise_key(entry.key)}.md"

    def _open_db(self) -> sqlite3.Connection:
        """Open (or create) the SQLite index with WAL mode.

        If the file is corrupted, it is deleted and recreated (the
        authoritative data lives in the Markdown files).
        """
        try:
            return self._init_db_connection(self._db_path)
        except sqlite3.DatabaseError:
            logger.warning("Corrupted SQLite index, recreating: %s", self._db_path)
            self._db_path.unlink(missing_ok=True)
            for wal_file in self._root.glob("_index.db-*"):
                wal_file.unlink(missing_ok=True)
            return self._init_db_connection(self._db_path)

    @staticmethod
    def _init_db_connection(db_path: Path) -> sqlite3.Connection:
        db = sqlite3.connect(str(db_path), check_same_thread=False)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=NORMAL")
        db.execute(
            """CREATE TABLE IF NOT EXISTS memory_index (
                key        TEXT PRIMARY KEY,
                layer      TEXT NOT NULL,
                tags       TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT ''
            )"""
        )
        db.execute("CREATE INDEX IF NOT EXISTS idx_layer ON memory_index(layer)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_updated ON memory_index(updated_at)")
        db.commit()
        return db

    def _maybe_migrate_json(self) -> None:
        """One-time migration from legacy _index.json to SQLite."""
        json_path = self._root / "_index.json"
        if not json_path.exists():
            count = self._db.execute("SELECT COUNT(*) FROM memory_index").fetchone()[0]
            if count == 0:
                self._rebuild_index()
            return

        try:
            data: dict[str, dict[str, Any]] = json.loads(json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Corrupted legacy _index.json during migration: %s", exc)
            self._rebuild_index()
            json_path.unlink(missing_ok=True)
            return

        with self._lock:
            for key, info in data.items():
                tags_json = json.dumps(info.get("tags", []), ensure_ascii=False)
                self._db.execute(
                    """INSERT OR REPLACE INTO memory_index
                       (key, layer, tags, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        key,
                        info.get("layer", "working"),
                        tags_json,
                        info.get("created_at", ""),
                        info.get("updated_at", ""),
                    ),
                )
            self._db.commit()

        migrated = json_path.with_suffix(".json.migrated")
        json_path.rename(migrated)
        logger.info(
            "Migrated %d entries from _index.json to SQLite; legacy file renamed to %s",
            len(data),
            migrated.name,
        )

    def _rebuild_index(self) -> None:
        """Scan Markdown files and populate the SQLite index from scratch."""
        with self._lock:
            self._db.execute("DELETE FROM memory_index")
            for layer in MemoryLayer:
                layer_dir = self._root / layer.value
                if not layer_dir.is_dir():
                    continue
                for md_file in layer_dir.glob("*.md"):
                    entry = self._read_entry(md_file)
                    if entry:
                        tags_json = json.dumps(entry.tags, ensure_ascii=False)
                        self._db.execute(
                            """INSERT OR REPLACE INTO memory_index
                               (key, layer, tags, created_at, updated_at)
                               VALUES (?, ?, ?, ?, ?)""",
                            (
                                entry.key,
                                entry.layer.value,
                                tags_json,
                                entry.created_at,
                                entry.updated_at,
                            ),
                        )
            self._db.commit()

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
        limit: int | None = None,
    ) -> list[str]:
        sql = "SELECT key, tags FROM memory_index"
        params: list[Any] = []
        clauses: list[str] = []
        if layer:
            clauses.append("layer = ?")
            params.append(layer)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY updated_at DESC"
        if limit:
            sql += " LIMIT ?"
            params.append(limit)

        rows = self._db.execute(sql, params).fetchall()
        if not tags:
            return [row[0] for row in rows]
        required = set(tags)
        return [
            row[0] for row in rows if required.issubset(set(json.loads(row[1]) if row[1] else []))
        ]
