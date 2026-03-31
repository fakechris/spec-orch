"""Lifecycle helpers for session, consolidation, and shared memory hygiene."""

from __future__ import annotations

import hashlib
import json
import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from spec_orch.services.io import atomic_write_json
from spec_orch.services.memory.types import MemoryEntry, MemoryLayer

if TYPE_CHECKING:
    from collections.abc import Iterator

    from spec_orch.services.memory.protocol import MemoryProvider


class MemoryWriteScope(StrEnum):
    SESSION = "session"
    EXTRACTED = "extracted"
    CONSOLIDATED = "consolidated"
    SHARED = "shared"


@dataclass(slots=True)
class SessionMemorySnapshot:
    snapshot_id: str
    session_id: str
    subject_kind: str
    subject_id: str
    event_count: int
    facts: list[str]
    artifact_refs: dict[str, str] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "session_id": self.session_id,
            "subject_kind": self.subject_kind,
            "subject_id": self.subject_id,
            "event_count": self.event_count,
            "facts": list(self.facts),
            "artifact_refs": dict(self.artifact_refs),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SessionMemorySnapshot:
        return cls(
            snapshot_id=str(payload.get("snapshot_id", "")),
            session_id=str(payload.get("session_id", "")),
            subject_kind=str(payload.get("subject_kind", "")),
            subject_id=str(payload.get("subject_id", "")),
            event_count=int(payload.get("event_count", 0)),
            facts=[str(item) for item in payload.get("facts", []) if str(item).strip()],
            artifact_refs=dict(payload.get("artifact_refs") or {}),
            created_at=str(payload.get("created_at", datetime.now(UTC).isoformat())),
        )


@dataclass(slots=True)
class SessionSnapshotCadenceDecision:
    should_snapshot: bool
    reason: str


@dataclass(slots=True)
class SharedMemorySyncEvent:
    sync_id: str
    repo_scope: str
    source: str
    freshness_key: str
    status: str
    content_hash: str
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "sync_id": self.sync_id,
            "repo_scope": self.repo_scope,
            "source": self.source,
            "freshness_key": self.freshness_key,
            "status": self.status,
            "content_hash": self.content_hash,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SharedMemorySyncEvent:
        return cls(
            sync_id=str(payload.get("sync_id", "")),
            repo_scope=str(payload.get("repo_scope", "")),
            source=str(payload.get("source", "")),
            freshness_key=str(payload.get("freshness_key", "")),
            status=str(payload.get("status", "")),
            content_hash=str(payload.get("content_hash", "")),
            created_at=str(payload.get("created_at", datetime.now(UTC).isoformat())),
        )


class MemoryLifecycleManager:
    def __init__(self, root: Path, provider: MemoryProvider) -> None:
        self._root = Path(root)
        self._provider = provider

    def should_snapshot_session(self, event_count: int, *, every_n_events: int = 2) -> bool:
        return event_count > 0 and every_n_events > 0 and event_count % every_n_events == 0

    def evaluate_snapshot_cadence(
        self,
        *,
        event_count: int,
        token_growth: int = 0,
        tool_calls: int = 0,
        natural_break: bool = False,
        every_n_events: int = 2,
    ) -> SessionSnapshotCadenceDecision:
        if natural_break and event_count > 0:
            return SessionSnapshotCadenceDecision(True, "natural_breakpoint")
        if token_growth >= 4000:
            return SessionSnapshotCadenceDecision(True, "token_growth_threshold")
        if tool_calls >= 6:
            return SessionSnapshotCadenceDecision(True, "tool_call_threshold")
        if self.should_snapshot_session(event_count, every_n_events=every_n_events):
            return SessionSnapshotCadenceDecision(True, "event_count_threshold")
        return SessionSnapshotCadenceDecision(False, "below_threshold")

    def record_session_snapshot(self, snapshot: SessionMemorySnapshot) -> str:
        existing_key = self._dedupe_existing_snapshot(snapshot)
        if existing_key is not None:
            return existing_key
        snapshots = self.read_session_snapshots()
        snapshots.append(snapshot)
        self._write_snapshots(snapshots)
        entry = MemoryEntry(
            key=f"session-snapshot-{snapshot.session_id}-{snapshot.event_count}",
            content="\n".join(snapshot.facts),
            layer=MemoryLayer.WORKING,
            tags=["session-memory", f"subject:{snapshot.subject_kind}"],
            metadata={
                "session_id": snapshot.session_id,
                "snapshot_id": snapshot.snapshot_id,
                "subject_kind": snapshot.subject_kind,
                "subject_id": snapshot.subject_id,
                "event_count": snapshot.event_count,
                "artifact_refs": snapshot.artifact_refs,
                "write_scope": MemoryWriteScope.SESSION.value,
                "entity_scope": snapshot.subject_kind,
                "entity_id": snapshot.subject_id,
                "relation_type": "observed",
            },
            created_at=snapshot.created_at,
            updated_at=snapshot.created_at,
        )
        return self._provider.store(entry)

    def read_session_snapshots(self) -> list[SessionMemorySnapshot]:
        path = self._root / "session_snapshots.jsonl"
        if not path.exists():
            return []
        snapshots: list[SessionMemorySnapshot] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                snapshots.append(SessionMemorySnapshot.from_dict(payload))
        return snapshots

    def reserve_shared_memory_write(self, freshness_key: str, *, ttl_seconds: int = 3600) -> bool:
        path = self._root / "shared_memory_claims.json"
        with self._json_lock("shared_memory_claims", stale_after_seconds=max(ttl_seconds, 300)):
            claims = self._read_json_dict(path)
            now = datetime.now(UTC)
            existing = claims.get(freshness_key)
            if isinstance(existing, dict):
                claimed_at = str(existing.get("claimed_at", ""))
                try:
                    existing_dt = datetime.fromisoformat(claimed_at)
                except ValueError:
                    existing_dt = None
                if existing_dt is not None and existing_dt > now - timedelta(seconds=ttl_seconds):
                    return False
            claims[freshness_key] = {"claimed_at": now.isoformat()}
            atomic_write_json(path, claims)
            return True

    @contextmanager
    def consolidation_lock(self, lock_name: str = "consolidation") -> Iterator[Path]:
        with self._json_lock(lock_name, stale_after_seconds=900) as lock_path:
            yield lock_path

    def validate_shared_memory_content(
        self,
        *,
        repo_scope: str,
        content: str,
    ) -> tuple[bool, str]:
        if not repo_scope.strip():
            return False, "repo_scope_required"
        if not re.fullmatch(r"[A-Za-z0-9._/-]+", repo_scope):
            return False, "invalid_repo_scope"
        lowered = content.lower()
        risky_markers = ("api_key", "secret", "token=", "password")
        if any(marker in lowered for marker in risky_markers):
            return False, "secret_like_content"
        return True, "ok"

    def record_shared_memory_sync(
        self,
        *,
        sync_id: str,
        repo_scope: str,
        source: str,
        freshness_key: str,
        content: str,
        status: str = "written",
    ) -> SharedMemorySyncEvent:
        allowed, reason = self.validate_shared_memory_content(
            repo_scope=repo_scope,
            content=content,
        )
        event = SharedMemorySyncEvent(
            sync_id=sync_id,
            repo_scope=repo_scope,
            source=source,
            freshness_key=freshness_key,
            status=status if allowed else f"blocked:{reason}",
            content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest()[:16],
        )
        path = self._root / "shared_memory_sync.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        return event

    def read_shared_memory_sync_events(self) -> list[SharedMemorySyncEvent]:
        path = self._root / "shared_memory_sync.jsonl"
        if not path.exists():
            return []
        rows: list[SharedMemorySyncEvent] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                rows.append(SharedMemorySyncEvent.from_dict(payload))
        return rows

    def _write_snapshots(self, snapshots: list[SessionMemorySnapshot]) -> None:
        path = self._root / "session_snapshots.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        if not snapshots:
            return
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(snapshots[-1].to_dict(), ensure_ascii=False) + "\n")

    def _dedupe_existing_snapshot(self, snapshot: SessionMemorySnapshot) -> str | None:
        for existing in reversed(self.read_session_snapshots()):
            if existing.session_id != snapshot.session_id:
                continue
            if existing.subject_id != snapshot.subject_id:
                continue
            if self._snapshot_fingerprint(existing) == self._snapshot_fingerprint(snapshot):
                return f"session-snapshot-{existing.session_id}-{existing.event_count}"
        return None

    @staticmethod
    def _snapshot_fingerprint(snapshot: SessionMemorySnapshot) -> str:
        return json.dumps(
            {
                "subject_kind": snapshot.subject_kind,
                "subject_id": snapshot.subject_id,
                "facts": snapshot.facts,
                "artifact_refs": snapshot.artifact_refs,
            },
            ensure_ascii=False,
            sort_keys=True,
        )

    @staticmethod
    def _read_json_dict(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    @contextmanager
    def _json_lock(
        self,
        lock_name: str,
        *,
        stale_after_seconds: int,
    ) -> Iterator[Path]:
        lock_path = self._root / f"{lock_name}.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = lock_path.open("x", encoding="utf-8")
        except FileExistsError as exc:
            try:
                created_at = datetime.fromisoformat(lock_path.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                created_at = None
            if created_at is not None and created_at < datetime.now(UTC) - timedelta(
                seconds=stale_after_seconds
            ):
                lock_path.unlink(missing_ok=True)
                fd = lock_path.open("x", encoding="utf-8")
            else:
                raise RuntimeError(f"lock already held: {lock_name}") from exc
        try:
            fd.write(datetime.now(UTC).isoformat())
            fd.flush()
            yield lock_path
        finally:
            fd.close()
            lock_path.unlink(missing_ok=True)
