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
            cjk_chars = [c for c in text if _CJK_RANGE.match(c)]
            bigrams = (
                [cjk_chars[i] + cjk_chars[i + 1] for i in range(len(cjk_chars) - 1)]
                if len(cjk_chars) >= 2
                else cjk_chars
            )
            non_cjk = [w for w in re.findall(r"[a-z0-9._+-]+", text) if len(w) > 2]
            return bigrams + non_cjk
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


def _fts5_available(db: sqlite3.Connection) -> bool:
    """Check if FTS5 extension is compiled into this SQLite build."""
    try:
        db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_probe USING fts5(x)")
        db.execute("DROP TABLE IF EXISTS _fts5_probe")
        return True
    except sqlite3.OperationalError:
        return False


def _init_fts5(db: sqlite3.Connection) -> bool:
    """Create the FTS5 content-sync table if FTS5 is available.

    Uses external content mode: the FTS index references memory_index
    for the actual content column, so no data duplication.
    """
    if not _fts5_available(db):
        return False
    db.execute(
        """CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
            key, content_text,
            tokenize='unicode61'
        )"""
    )
    return True


def rrf_fuse(
    *ranked_lists: list[str],
    k: int = 60,
) -> list[str]:
    """Reciprocal Rank Fusion across multiple ranked key lists.

    Returns keys sorted by descending RRF score.
    """
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, key in enumerate(ranked):
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores, key=lambda x: scores[x], reverse=True)


def _migrate_add_relation_columns(db: sqlite3.Connection) -> None:
    """Add entity_scope/entity_id/relation_type columns if missing (v2 migration)."""
    cols = {row[1] for row in db.execute("PRAGMA table_info(memory_index)").fetchall()}
    new_cols = [
        ("entity_scope", "TEXT NOT NULL DEFAULT ''"),
        ("entity_id", "TEXT NOT NULL DEFAULT ''"),
        ("relation_type", "TEXT NOT NULL DEFAULT 'observed'"),
    ]
    for name, typedef in new_cols:
        if name not in cols:
            db.execute(f"ALTER TABLE memory_index ADD COLUMN {name} {typedef}")
            logger.info("Migrated memory_index: added column %s", name)


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
        self._fts_enabled = _init_fts5(self._db)
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
            entity_scope = str(entry.metadata.get("entity_scope", ""))
            entity_id = str(entry.metadata.get("entity_id", ""))
            relation_type = str(entry.metadata.get("relation_type", "observed"))
            self._db.execute(
                """INSERT OR REPLACE INTO memory_index
                   (key, layer, tags, created_at, updated_at,
                    entity_scope, entity_id, relation_type)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry.key,
                    entry.layer.value,
                    tags_json,
                    entry.created_at,
                    entry.updated_at,
                    entity_scope,
                    entity_id,
                    relation_type,
                ),
            )
            if self._fts_enabled:
                self._upsert_fts(entry.key, entry.content)
            self._db.commit()
        return entry.key

    def search_fts(self, text: str, *, top_k: int = 20) -> list[str]:
        """Full-text search via FTS5. Returns ranked key list.

        Splits query into individual terms joined with OR for broad matching.
        Falls back to empty for CJK-heavy queries since unicode61 tokenizer
        handles CJK poorly; the caller should use _text_matches instead.
        """
        if not self._fts_enabled or not text.strip():
            return []
        if _CJK_RANGE.search(text):
            return []
        terms = [w for w in re.split(r"\s+", text.strip()) if len(w) > 1]
        if not terms:
            return []
        escaped = [f'"{t.replace(chr(34), "")}"' for t in terms]
        match_expr = " OR ".join(escaped)
        try:
            rows = self._db.execute(
                "SELECT key FROM memory_fts WHERE memory_fts MATCH ? ORDER BY rank LIMIT ?",
                (match_expr, top_k),
            ).fetchall()
            return [r[0] for r in rows]
        except sqlite3.OperationalError:
            logger.debug("FTS5 search failed for: %s", text[:80], exc_info=True)
            return []

    def recall(self, query: MemoryQuery) -> list[MemoryEntry]:
        layer_str = query.layer.value if query.layer else None

        fts_keys: list[str] = []
        if query.text and self._fts_enabled:
            fts_keys = self.search_fts(query.text, top_k=query.top_k * 3)

        use_fts = bool(fts_keys)

        if use_fts:
            index_keys = self._filtered_keys(layer=layer_str, tags=query.tags or None)
            index_set = set(index_keys)
            if layer_str or query.tags:
                candidates = [k for k in rrf_fuse(fts_keys, index_keys) if k in index_set]
            else:
                candidates = fts_keys
        else:
            candidates = self._filtered_keys(layer=layer_str, tags=query.tags or None)

        results: list[MemoryEntry] = []
        for key in candidates:
            entry = self.get(key)
            if entry is None:
                continue
            if query.filters and not all(
                entry.metadata.get(k) == v for k, v in query.filters.items()
            ):
                continue
            if query.text and not use_fts and not _text_matches(query.text, entry.content):
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
            if self._fts_enabled:
                self._delete_fts(key)
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
        with self._lock:
            row = self._db.execute(
                "SELECT layer FROM memory_index WHERE key = ?", (key,)
            ).fetchone()
            if row is None:
                return None
            layer = row[0]
            path = self._root / layer / f"{_sanitise_key(key)}.md"
            if not path.exists():
                self._db.execute(
                    "DELETE FROM memory_index WHERE key = ? AND layer = ?", (key, layer)
                )
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
        if limit and not tags:
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
            if limit and len(results) >= limit:
                break
        return results

    # -- FTS helpers ----------------------------------------------------------

    def _upsert_fts(self, key: str, content: str) -> None:
        """Insert or replace a document in the FTS5 index."""
        self._db.execute("DELETE FROM memory_fts WHERE key = ?", (key,))
        self._db.execute(
            "INSERT INTO memory_fts (key, content_text) VALUES (?, ?)",
            (key, content),
        )

    def _delete_fts(self, key: str) -> None:
        """Remove a document from the FTS5 index."""
        self._db.execute("DELETE FROM memory_fts WHERE key = ?", (key,))

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
                key           TEXT PRIMARY KEY,
                layer         TEXT NOT NULL,
                tags          TEXT NOT NULL DEFAULT '[]',
                created_at    TEXT NOT NULL DEFAULT '',
                updated_at    TEXT NOT NULL DEFAULT '',
                entity_scope  TEXT NOT NULL DEFAULT '',
                entity_id     TEXT NOT NULL DEFAULT '',
                relation_type TEXT NOT NULL DEFAULT 'observed'
            )"""
        )
        _migrate_add_relation_columns(db)
        db.execute("CREATE INDEX IF NOT EXISTS idx_layer ON memory_index(layer)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_updated ON memory_index(updated_at)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_entity ON memory_index(entity_scope, entity_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_relation ON memory_index(relation_type)")
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
                       (key, layer, tags, created_at, updated_at,
                        entity_scope, entity_id, relation_type)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        key,
                        info.get("layer", "working"),
                        tags_json,
                        info.get("created_at", ""),
                        info.get("updated_at", ""),
                        "",
                        "",
                        "observed",
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
            if self._fts_enabled:
                self._db.execute("DELETE FROM memory_fts")
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
                               (key, layer, tags, created_at, updated_at,
                                entity_scope, entity_id, relation_type)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                entry.key,
                                entry.layer.value,
                                tags_json,
                                entry.created_at,
                                entry.updated_at,
                                str(entry.metadata.get("entity_scope", "")),
                                str(entry.metadata.get("entity_id", "")),
                                str(entry.metadata.get("relation_type", "observed")),
                            ),
                        )
                        if self._fts_enabled:
                            self._upsert_fts(entry.key, entry.content)
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
        entity_scope: str | None = None,
        entity_id: str | None = None,
        exclude_relation_types: list[str] | None = None,
    ) -> list[str]:
        sql = "SELECT key, tags FROM memory_index"
        params: list[Any] = []
        clauses: list[str] = []
        if layer:
            clauses.append("layer = ?")
            params.append(layer)
        if entity_scope:
            clauses.append("entity_scope = ?")
            params.append(entity_scope)
        if entity_id:
            clauses.append("entity_id = ?")
            params.append(entity_id)
        if exclude_relation_types:
            placeholders = ", ".join("?" for _ in exclude_relation_types)
            clauses.append(f"relation_type NOT IN ({placeholders})")
            params.extend(exclude_relation_types)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY updated_at DESC"
        if limit and not tags:
            sql += " LIMIT ?"
            params.append(limit)

        rows = self._db.execute(sql, params).fetchall()
        if not tags:
            return [row[0] for row in rows]
        required = set(tags)
        result = [
            row[0] for row in rows if required.issubset(set(json.loads(row[1]) if row[1] else []))
        ]
        return result[:limit] if limit else result
