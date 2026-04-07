from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


class DaemonStateStore:
    """Durable daemon state substrate backed by SQLite WAL.

    This replaces the most fragile parts of the legacy file-based daemon state:
    - `daemon_state.json`
    - per-issue `.lock` files
    - per-issue `.retry_at` files
    """

    DB_NAME = "daemon_state.db"
    LEGACY_STATE_FILE = "daemon_state.json"

    def __init__(self, lockdir: Path) -> None:
        self._lockdir = Path(lockdir)
        self._lockdir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._lockdir / self.DB_NAME
        self._db = self._open_db()
        self._maybe_migrate_legacy_json()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def _open_db(self) -> sqlite3.Connection:
        db = sqlite3.connect(str(self._db_path), check_same_thread=False)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=NORMAL")
        db.execute(
            """CREATE TABLE IF NOT EXISTS issue_runtime_state (
                issue_id     TEXT PRIMARY KEY,
                processed    INTEGER NOT NULL DEFAULT 0,
                triaged      INTEGER NOT NULL DEFAULT 0,
                in_progress  INTEGER NOT NULL DEFAULT 0,
                dead_letter  INTEGER NOT NULL DEFAULT 0,
                retry_count  INTEGER NOT NULL DEFAULT 0,
                retry_at     REAL,
                pr_commit    TEXT NOT NULL DEFAULT '',
                updated_at   REAL NOT NULL DEFAULT 0
            )"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS reaction_marks (
                mark       TEXT PRIMARY KEY,
                created_at REAL NOT NULL DEFAULT 0
            )"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS daemon_meta (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            )"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS issue_claims (
                issue_id     TEXT PRIMARY KEY,
                owner        TEXT NOT NULL,
                expires_at   REAL NOT NULL,
                updated_at   REAL NOT NULL DEFAULT 0
            )"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS daemon_locks (
                lock_name    TEXT PRIMARY KEY,
                owner        TEXT NOT NULL,
                pid          INTEGER NOT NULL,
                expires_at   REAL NOT NULL,
                updated_at   REAL NOT NULL DEFAULT 0
            )"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS execution_intents (
                issue_id      TEXT PRIMARY KEY,
                raw_issue     TEXT NOT NULL,
                is_hotfix     INTEGER NOT NULL DEFAULT 0,
                enqueued_at   REAL NOT NULL DEFAULT 0,
                updated_at    REAL NOT NULL DEFAULT 0
            )"""
        )
        db.commit()
        return db

    def _maybe_migrate_legacy_json(self) -> None:
        legacy = self._lockdir / self.LEGACY_STATE_FILE
        if not legacy.exists():
            return
        try:
            payload = json.loads(legacy.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        if not isinstance(payload, dict):
            return
        if self._db.execute("SELECT COUNT(*) FROM issue_runtime_state").fetchone()[0] > 0:
            return
        snapshot = {
            "processed": payload.get("processed", []),
            "triaged": payload.get("triaged", []),
            "pr_commits": payload.get("pr_commits", {}),
            "retry_counts": payload.get("retry_counts", {}),
            "retry_at": {},
            "dead_letter": payload.get("dead_letter", []),
            "in_progress": payload.get("in_progress", []),
            "reaction_marks": payload.get("reaction_marks", []),
            "last_poll": payload.get("last_poll", ""),
        }
        self.save_snapshot(snapshot)
        legacy.rename(legacy.with_suffix(".json.migrated"))

    def load_snapshot(self) -> dict[str, Any]:
        processed: list[str] = []
        triaged: list[str] = []
        dead_letter: list[str] = []
        in_progress: list[str] = []
        retry_counts: dict[str, int] = {}
        retry_at: dict[str, float] = {}
        pr_commits: dict[str, str] = {}

        rows = self._db.execute(
            """SELECT issue_id, processed, triaged, in_progress, dead_letter,
                      retry_count, retry_at, pr_commit
               FROM issue_runtime_state"""
        ).fetchall()
        for row in rows:
            issue_id = str(row[0])
            if int(row[1] or 0):
                processed.append(issue_id)
            if int(row[2] or 0):
                triaged.append(issue_id)
            if int(row[3] or 0):
                in_progress.append(issue_id)
            if int(row[4] or 0):
                dead_letter.append(issue_id)
            count = int(row[5] or 0)
            if count > 0:
                retry_counts[issue_id] = count
            retry_epoch = row[6]
            if retry_epoch is not None:
                retry_at[issue_id] = float(retry_epoch)
            pr_commit = str(row[7] or "").strip()
            if pr_commit:
                pr_commits[issue_id] = pr_commit

        reaction_marks = [
            str(mark)
            for (mark,) in self._db.execute(
                "SELECT mark FROM reaction_marks ORDER BY mark"
            ).fetchall()
        ]
        queued_execution = [
            str(issue_id)
            for (issue_id,) in self._db.execute(
                "SELECT issue_id FROM execution_intents ORDER BY enqueued_at, issue_id"
            ).fetchall()
        ]
        last_poll_row = self._db.execute(
            "SELECT value FROM daemon_meta WHERE key = 'last_poll'"
        ).fetchone()
        last_poll = str(last_poll_row[0]) if last_poll_row else ""
        if (
            not processed
            and not triaged
            and not dead_letter
            and not in_progress
            and not retry_counts
            and not pr_commits
            and not reaction_marks
            and not queued_execution
            and not last_poll
        ):
            return {}
        return {
            "processed": sorted(processed),
            "triaged": sorted(triaged),
            "pr_commits": pr_commits,
            "retry_counts": retry_counts,
            "retry_at": retry_at,
            "dead_letter": sorted(dead_letter),
            "in_progress": sorted(in_progress),
            "reaction_marks": reaction_marks,
            "queued_execution": queued_execution,
            "last_poll": last_poll,
        }

    def save_snapshot(self, snapshot: dict[str, Any]) -> None:
        now = time.time()
        processed = {str(item) for item in snapshot.get("processed", []) if str(item).strip()}
        triaged = {str(item) for item in snapshot.get("triaged", []) if str(item).strip()}
        dead_letter = {str(item) for item in snapshot.get("dead_letter", []) if str(item).strip()}
        in_progress = {str(item) for item in snapshot.get("in_progress", []) if str(item).strip()}
        retry_counts = {
            str(key): max(0, int(value))
            for key, value in dict(snapshot.get("retry_counts", {})).items()
            if str(key).strip()
        }
        retry_at = {
            str(key): float(value)
            for key, value in dict(snapshot.get("retry_at", {})).items()
            if str(key).strip()
        }
        pr_commits = {
            str(key): str(value)
            for key, value in dict(snapshot.get("pr_commits", {})).items()
            if str(key).strip() and str(value).strip()
        }
        reaction_marks = {
            str(item) for item in snapshot.get("reaction_marks", []) if str(item).strip()
        }
        all_issue_ids = (
            processed
            | triaged
            | dead_letter
            | in_progress
            | set(retry_counts)
            | set(retry_at)
            | set(pr_commits)
        )

        with self._db:
            # UPSERT each issue instead of DELETE-all + re-INSERT.
            for issue_id in all_issue_ids:
                self._db.execute(
                    """INSERT INTO issue_runtime_state (
                           issue_id, processed, triaged, in_progress, dead_letter,
                           retry_count, retry_at, pr_commit, updated_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(issue_id) DO UPDATE SET
                           processed   = excluded.processed,
                           triaged     = excluded.triaged,
                           in_progress = excluded.in_progress,
                           dead_letter = excluded.dead_letter,
                           retry_count = excluded.retry_count,
                           retry_at    = excluded.retry_at,
                           pr_commit   = excluded.pr_commit,
                           updated_at  = excluded.updated_at""",
                    (
                        issue_id,
                        1 if issue_id in processed else 0,
                        1 if issue_id in triaged else 0,
                        1 if issue_id in in_progress else 0,
                        1 if issue_id in dead_letter else 0,
                        retry_counts.get(issue_id, 0),
                        retry_at.get(issue_id),
                        pr_commits.get(issue_id, ""),
                        now,
                    ),
                )
            # Prune rows for issues no longer referenced.
            if all_issue_ids:
                placeholders = ",".join("?" for _ in all_issue_ids)
                self._db.execute(
                    f"DELETE FROM issue_runtime_state WHERE issue_id NOT IN ({placeholders})",
                    tuple(all_issue_ids),
                )
            else:
                self._db.execute("DELETE FROM issue_runtime_state")

            # UPSERT reaction marks + prune stale ones.
            for mark in reaction_marks:
                self._db.execute(
                    """INSERT INTO reaction_marks(mark, created_at) VALUES (?, ?)
                       ON CONFLICT(mark) DO NOTHING""",
                    (mark, now),
                )
            if reaction_marks:
                placeholders = ",".join("?" for _ in reaction_marks)
                self._db.execute(
                    f"DELETE FROM reaction_marks WHERE mark NOT IN ({placeholders})",
                    tuple(reaction_marks),
                )
            else:
                self._db.execute("DELETE FROM reaction_marks")

            self._db.execute(
                "INSERT OR REPLACE INTO daemon_meta(key, value) VALUES ('last_poll', ?)",
                (str(snapshot.get("last_poll", "") or ""),),
            )

    def issue_is_claimed(self, issue_id: str, *, now: float | None = None) -> bool:
        row = self._db.execute(
            "SELECT expires_at FROM issue_claims WHERE issue_id = ?",
            (issue_id,),
        ).fetchone()
        if row is None:
            return False
        current = time.time() if now is None else float(now)
        return float(row[0] or 0) > current

    def try_claim_issue(
        self,
        issue_id: str,
        *,
        owner: str,
        lease_seconds: float,
        now: float | None = None,
    ) -> bool:
        current = time.time() if now is None else float(now)
        expires_at = current + max(float(lease_seconds), 1.0)
        with self._db:
            row = self._db.execute(
                "SELECT owner, expires_at FROM issue_claims WHERE issue_id = ?",
                (issue_id,),
            ).fetchone()
            if row is not None:
                existing_owner = str(row[0] or "")
                existing_expires = float(row[1] or 0)
                if existing_expires > current and existing_owner != owner:
                    return False
            self._db.execute(
                """INSERT OR REPLACE INTO issue_claims(issue_id, owner, expires_at, updated_at)
                   VALUES (?, ?, ?, ?)""",
                (issue_id, owner, expires_at, current),
            )
        return True

    def release_issue_claim(self, issue_id: str) -> None:
        with self._db:
            self._db.execute("DELETE FROM issue_claims WHERE issue_id = ?", (issue_id,))

    def acquire_daemon_lock(
        self,
        *,
        owner: str,
        pid: int,
        lease_seconds: float,
        now: float | None = None,
        lock_name: str = "spec_orch_daemon",
    ) -> bool:
        current = time.time() if now is None else float(now)
        expires_at = current + max(float(lease_seconds), 1.0)
        with self._db:
            row = self._db.execute(
                "SELECT owner, expires_at FROM daemon_locks WHERE lock_name = ?",
                (lock_name,),
            ).fetchone()
            if row is not None:
                existing_owner = str(row[0] or "")
                existing_expires = float(row[1] or 0)
                if existing_expires > current and existing_owner != owner:
                    return False
            self._db.execute(
                """INSERT OR REPLACE INTO daemon_locks(
                       lock_name, owner, pid, expires_at, updated_at
                   )
                   VALUES (?, ?, ?, ?, ?)""",
                (lock_name, owner, int(pid), expires_at, current),
            )
        return True

    def renew_daemon_lock(
        self,
        *,
        owner: str,
        pid: int,
        lease_seconds: float,
        now: float | None = None,
        lock_name: str = "spec_orch_daemon",
    ) -> bool:
        return self.acquire_daemon_lock(
            owner=owner,
            pid=pid,
            lease_seconds=lease_seconds,
            now=now,
            lock_name=lock_name,
        )

    def release_daemon_lock(self, *, owner: str, lock_name: str = "spec_orch_daemon") -> None:
        with self._db:
            self._db.execute(
                "DELETE FROM daemon_locks WHERE lock_name = ? AND owner = ?",
                (lock_name, owner),
            )

    def enqueue_execution_intent(
        self,
        *,
        issue_id: str,
        raw_issue: dict[str, Any],
        is_hotfix: bool,
        enqueued_at: float | None = None,
    ) -> None:
        current = time.time() if enqueued_at is None else float(enqueued_at)
        with self._db:
            self._db.execute(
                """INSERT OR REPLACE INTO execution_intents(
                       issue_id, raw_issue, is_hotfix, enqueued_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?)""",
                (
                    issue_id,
                    json.dumps(raw_issue, sort_keys=True),
                    1 if is_hotfix else 0,
                    current,
                    current,
                ),
            )

    def list_execution_intents(self) -> list[dict[str, Any]]:
        rows = self._db.execute(
            """SELECT issue_id, raw_issue, is_hotfix, enqueued_at
               FROM execution_intents
               ORDER BY enqueued_at, issue_id"""
        ).fetchall()
        intents: list[dict[str, Any]] = []
        for issue_id, raw_issue, is_hotfix, enqueued_at in rows:
            try:
                payload = json.loads(str(raw_issue))
            except json.JSONDecodeError:
                payload = {}
            intents.append(
                {
                    "issue_id": str(issue_id),
                    "raw_issue": payload if isinstance(payload, dict) else {},
                    "is_hotfix": bool(int(is_hotfix or 0)),
                    "enqueued_at": float(enqueued_at or 0),
                }
            )
        return intents

    def pop_next_execution_intent(self) -> dict[str, Any] | None:
        with self._db:
            row = self._db.execute(
                """SELECT issue_id, raw_issue, is_hotfix, enqueued_at
                   FROM execution_intents
                   ORDER BY enqueued_at, issue_id
                   LIMIT 1"""
            ).fetchone()
            if row is None:
                return None
            issue_id, raw_issue, is_hotfix, enqueued_at = row
            self._db.execute(
                "DELETE FROM execution_intents WHERE issue_id = ?",
                (str(issue_id),),
            )
        try:
            payload = json.loads(str(raw_issue))
        except json.JSONDecodeError:
            payload = {}
        return {
            "issue_id": str(issue_id),
            "raw_issue": payload if isinstance(payload, dict) else {},
            "is_hotfix": bool(int(is_hotfix or 0)),
            "enqueued_at": float(enqueued_at or 0),
        }

    def delete_execution_intent(self, issue_id: str) -> None:
        with self._db:
            self._db.execute(
                "DELETE FROM execution_intents WHERE issue_id = ?",
                (issue_id,),
            )

    # ---- Per-issue transactional state changes ----

    def _ensure_issue_row(self, issue_id: str, *, now: float | None = None) -> None:
        """Insert a row for *issue_id* if it doesn't exist yet."""
        current = time.time() if now is None else now
        self._db.execute(
            """INSERT OR IGNORE INTO issue_runtime_state
               (issue_id, updated_at) VALUES (?, ?)""",
            (issue_id, current),
        )

    def mark_in_progress(self, issue_id: str) -> None:
        """Atomically mark an issue as in-progress."""
        now = time.time()
        with self._db:
            self._ensure_issue_row(issue_id, now=now)
            self._db.execute(
                """UPDATE issue_runtime_state
                   SET in_progress = 1, updated_at = ?
                   WHERE issue_id = ?""",
                (now, issue_id),
            )

    def mark_processed(self, issue_id: str) -> None:
        """Atomically mark an issue as processed (and clear in_progress)."""
        now = time.time()
        with self._db:
            self._ensure_issue_row(issue_id, now=now)
            self._db.execute(
                """UPDATE issue_runtime_state
                   SET processed = 1, in_progress = 0, updated_at = ?
                   WHERE issue_id = ?""",
                (now, issue_id),
            )

    def mark_triaged(self, issue_id: str) -> None:
        """Atomically mark an issue as triaged."""
        now = time.time()
        with self._db:
            self._ensure_issue_row(issue_id, now=now)
            self._db.execute(
                """UPDATE issue_runtime_state
                   SET triaged = 1, updated_at = ?
                   WHERE issue_id = ?""",
                (now, issue_id),
            )

    def clear_triaged(self, issue_id: str) -> None:
        """Atomically clear the triaged flag for an issue."""
        now = time.time()
        with self._db:
            self._db.execute(
                """UPDATE issue_runtime_state
                   SET triaged = 0, updated_at = ?
                   WHERE issue_id = ?""",
                (now, issue_id),
            )

    def clear_in_progress(self, issue_id: str) -> None:
        """Atomically clear the in_progress flag for an issue."""
        now = time.time()
        with self._db:
            self._db.execute(
                """UPDATE issue_runtime_state
                   SET in_progress = 0, updated_at = ?
                   WHERE issue_id = ?""",
                (now, issue_id),
            )

    def mark_dead_letter(self, issue_id: str) -> None:
        """Atomically move an issue to the dead-letter queue."""
        now = time.time()
        with self._db:
            self._ensure_issue_row(issue_id, now=now)
            self._db.execute(
                """UPDATE issue_runtime_state
                   SET dead_letter = 1, in_progress = 0,
                       retry_count = 0, retry_at = NULL, updated_at = ?
                   WHERE issue_id = ?""",
                (now, issue_id),
            )

    def clear_dead_letter(self, issue_id: str) -> None:
        """Atomically remove an issue from the dead-letter queue."""
        now = time.time()
        with self._db:
            self._db.execute(
                """UPDATE issue_runtime_state
                   SET dead_letter = 0, processed = 0,
                       retry_count = 0, retry_at = NULL, updated_at = ?
                   WHERE issue_id = ?""",
                (now, issue_id),
            )

    def clear_all_dead_letter(self) -> int:
        """Atomically clear all dead-letter entries. Returns count removed."""
        with self._db:
            row = self._db.execute(
                "SELECT COUNT(*) FROM issue_runtime_state WHERE dead_letter = 1"
            ).fetchone()
            count = int(row[0]) if row else 0
            self._db.execute(
                """UPDATE issue_runtime_state
                   SET dead_letter = 0, processed = 0,
                       retry_count = 0, retry_at = NULL, updated_at = ?
                   WHERE dead_letter = 1""",
                (time.time(),),
            )
        return count

    def increment_retry(self, issue_id: str, *, max_retries: int, base_delay: int) -> str:
        """Atomically increment retry count. Returns 'retry' or 'dead_letter'."""
        now = time.time()
        with self._db:
            self._ensure_issue_row(issue_id, now=now)
            row = self._db.execute(
                "SELECT retry_count FROM issue_runtime_state WHERE issue_id = ?",
                (issue_id,),
            ).fetchone()
            count = (int(row[0]) if row else 0) + 1
            if count >= max_retries:
                self._db.execute(
                    """UPDATE issue_runtime_state
                       SET dead_letter = 1, in_progress = 0,
                           retry_count = 0, retry_at = NULL, updated_at = ?
                       WHERE issue_id = ?""",
                    (now, issue_id),
                )
                return "dead_letter"
            delay = base_delay * (2 ** (count - 1))
            retry_at = now + delay
            self._db.execute(
                """UPDATE issue_runtime_state
                   SET retry_count = ?, retry_at = ?, updated_at = ?
                   WHERE issue_id = ?""",
                (count, retry_at, now, issue_id),
            )
        return "retry"

    def set_pr_commit(self, issue_id: str, commit_sha: str) -> None:
        """Atomically record the PR commit SHA for an issue."""
        now = time.time()
        with self._db:
            self._ensure_issue_row(issue_id, now=now)
            self._db.execute(
                """UPDATE issue_runtime_state
                   SET pr_commit = ?, updated_at = ?
                   WHERE issue_id = ?""",
                (commit_sha, now, issue_id),
            )

    def add_reaction_mark(self, mark: str) -> None:
        """Atomically add a reaction mark."""
        with self._db:
            self._db.execute(
                """INSERT OR IGNORE INTO reaction_marks(mark, created_at)
                   VALUES (?, ?)""",
                (mark, time.time()),
            )

    def get_issue_state(self, issue_id: str) -> dict[str, Any] | None:
        """Return the full state row for a single issue, or None."""
        row = self._db.execute(
            """SELECT processed, triaged, in_progress, dead_letter,
                      retry_count, retry_at, pr_commit
               FROM issue_runtime_state WHERE issue_id = ?""",
            (issue_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "processed": bool(row[0]),
            "triaged": bool(row[1]),
            "in_progress": bool(row[2]),
            "dead_letter": bool(row[3]),
            "retry_count": int(row[4]),
            "retry_at": float(row[5]) if row[5] is not None else None,
            "pr_commit": str(row[6] or ""),
        }

    def is_processed(self, issue_id: str) -> bool:
        """Check if an issue has been processed."""
        row = self._db.execute(
            "SELECT processed FROM issue_runtime_state WHERE issue_id = ?",
            (issue_id,),
        ).fetchone()
        return bool(row and row[0])

    def is_in_progress(self, issue_id: str) -> bool:
        """Check if an issue is currently in progress."""
        row = self._db.execute(
            "SELECT in_progress FROM issue_runtime_state WHERE issue_id = ?",
            (issue_id,),
        ).fetchone()
        return bool(row and row[0])

    def is_dead_letter(self, issue_id: str) -> bool:
        """Check if an issue is in the dead-letter queue."""
        row = self._db.execute(
            "SELECT dead_letter FROM issue_runtime_state WHERE issue_id = ?",
            (issue_id,),
        ).fetchone()
        return bool(row and row[0])

    def should_backoff(self, issue_id: str) -> bool:
        """Check if an issue is in retry backoff (retry_at > now)."""
        row = self._db.execute(
            "SELECT retry_at FROM issue_runtime_state WHERE issue_id = ?",
            (issue_id,),
        ).fetchone()
        if row is None or row[0] is None:
            return False
        return float(row[0]) > time.time()

    def list_in_progress(self) -> list[str]:
        """Return all issue IDs currently marked as in_progress."""
        rows = self._db.execute(
            "SELECT issue_id FROM issue_runtime_state WHERE in_progress = 1"
        ).fetchall()
        return [str(row[0]) for row in rows]

    def list_dead_letter(self) -> list[str]:
        """Return all issue IDs in the dead-letter queue."""
        rows = self._db.execute(
            "SELECT issue_id FROM issue_runtime_state WHERE dead_letter = 1 ORDER BY issue_id"
        ).fetchall()
        return [str(row[0]) for row in rows]

    def has_reaction_mark(self, mark: str) -> bool:
        """Check if a reaction mark exists."""
        row = self._db.execute("SELECT 1 FROM reaction_marks WHERE mark = ?", (mark,)).fetchone()
        return row is not None
