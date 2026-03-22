"""Async derivation queue for background memory processing.

Provides a lightweight SQLite-based task queue that supports both
synchronous (inline) and asynchronous (daemon-driven) execution.
Heavy memory operations like compact, profile refresh, and recipe
extraction are enqueued as tasks and processed in batches.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DerivationTask:
    """A unit of background derivation work."""

    task_id: str
    task_type: str
    payload: dict[str, Any]
    status: str = "pending"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None


class DerivationQueue:
    """SQLite-backed task queue for derivation work.

    Schema is co-located with the memory index DB for simplicity.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        self._db = self._open_db()

    def _open_db(self) -> sqlite3.Connection:
        db = sqlite3.connect(str(self._db_path), check_same_thread=False)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=NORMAL")
        db.execute(
            """CREATE TABLE IF NOT EXISTS derivation_queue (
                task_id      TEXT PRIMARY KEY,
                task_type    TEXT NOT NULL,
                payload      TEXT NOT NULL DEFAULT '{}',
                status       TEXT NOT NULL DEFAULT 'pending',
                created_at   TEXT NOT NULL DEFAULT '',
                started_at   TEXT DEFAULT NULL,
                completed_at TEXT DEFAULT NULL,
                error        TEXT DEFAULT NULL
            )"""
        )
        db.execute("CREATE INDEX IF NOT EXISTS idx_dq_status ON derivation_queue(status)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_dq_type ON derivation_queue(task_type)")
        db.commit()
        return db

    def enqueue(self, task_type: str, payload: dict[str, Any] | None = None) -> str:
        """Add a task to the queue. Returns the task_id."""
        task_id = str(uuid.uuid4())[:12]
        now = datetime.now(UTC).isoformat()
        payload_json = json.dumps(payload or {}, ensure_ascii=False)
        with self._lock:
            self._db.execute(
                """INSERT INTO derivation_queue
                   (task_id, task_type, payload, status, created_at)
                   VALUES (?, ?, ?, 'pending', ?)""",
                (task_id, task_type, payload_json, now),
            )
            self._db.commit()
        logger.debug("Enqueued derivation task %s: %s", task_id, task_type)
        return task_id

    def dequeue(self, batch_size: int = 5) -> list[DerivationTask]:
        """Fetch up to batch_size pending tasks, marking them in-progress."""
        now = datetime.now(UTC).isoformat()
        with self._lock:
            rows = self._db.execute(
                """SELECT task_id, task_type, payload, created_at
                   FROM derivation_queue
                   WHERE status = 'pending'
                   ORDER BY created_at ASC
                   LIMIT ?""",
                (batch_size,),
            ).fetchall()
            tasks = []
            for task_id, task_type, payload_json, created_at in rows:
                self._db.execute(
                    "UPDATE derivation_queue SET status = 'running', started_at = ? "
                    "WHERE task_id = ?",
                    (now, task_id),
                )
                tasks.append(
                    DerivationTask(
                        task_id=task_id,
                        task_type=task_type,
                        payload=json.loads(payload_json),
                        status="running",
                        created_at=created_at,
                        started_at=now,
                    )
                )
            self._db.commit()
        return tasks

    def complete(self, task_id: str, *, error: str | None = None) -> None:
        """Mark a task as completed (or failed if error is provided)."""
        now = datetime.now(UTC).isoformat()
        status = "failed" if error else "completed"
        with self._lock:
            self._db.execute(
                "UPDATE derivation_queue SET status = ?, completed_at = ?, error = ? "
                "WHERE task_id = ?",
                (status, now, error, task_id),
            )
            self._db.commit()

    def pending_count(self) -> int:
        """Return count of pending tasks."""
        row = self._db.execute(
            "SELECT COUNT(*) FROM derivation_queue WHERE status = 'pending'"
        ).fetchone()
        return row[0] if row else 0

    def cleanup(self, *, max_age_days: int = 7) -> int:
        """Remove completed/failed tasks older than max_age_days."""
        from datetime import timedelta

        cutoff = (datetime.now(UTC) - timedelta(days=max_age_days)).isoformat()
        with self._lock:
            cursor = self._db.execute(
                "DELETE FROM derivation_queue "
                "WHERE status IN ('completed', 'failed') AND completed_at < ?",
                (cutoff,),
            )
            self._db.commit()
        return cursor.rowcount


class DerivationWorker:
    """Executes derivation tasks from the queue.

    Each task_type maps to a handler callable. Unknown types are skipped
    with a warning.
    """

    def __init__(self, queue: DerivationQueue) -> None:
        self._queue = queue
        self._handlers: dict[str, Callable[[dict[str, Any]], None]] = {}

    def register(self, task_type: str, handler: Callable[[dict[str, Any]], None]) -> None:
        """Register a handler for a task type."""
        self._handlers[task_type] = handler

    def process_batch(self, batch_size: int = 5) -> int:
        """Dequeue and process up to batch_size tasks. Returns count processed."""
        tasks = self._queue.dequeue(batch_size)
        processed = 0
        for task in tasks:
            handler = self._handlers.get(task.task_type)
            if handler is None:
                logger.warning(
                    "No handler for derivation task type: %s (id=%s)",
                    task.task_type,
                    task.task_id,
                )
                self._queue.complete(task.task_id, error="no_handler")
                continue
            try:
                handler(task.payload)
                self._queue.complete(task.task_id)
                processed += 1
            except Exception as exc:
                logger.warning(
                    "Derivation task %s failed: %s",
                    task.task_id,
                    exc,
                    exc_info=True,
                )
                self._queue.complete(task.task_id, error=str(exc)[:500])
        return processed

    def tick(self, batch_size: int = 5) -> int:
        """Alias for process_batch — designed for daemon tick loops."""
        return self.process_batch(batch_size)
