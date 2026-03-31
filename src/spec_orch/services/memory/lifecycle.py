"""Lifecycle helpers for session, consolidation, and shared memory hygiene."""

from __future__ import annotations

import json
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


class MemoryLifecycleManager:
    def __init__(self, root: Path, provider: MemoryProvider) -> None:
        self._root = Path(root)
        self._provider = provider

    def should_snapshot_session(self, event_count: int, *, every_n_events: int = 2) -> bool:
        return event_count > 0 and every_n_events > 0 and event_count % every_n_events == 0

    def record_session_snapshot(self, snapshot: SessionMemorySnapshot) -> str:
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
        lock_path = self._root / f"{lock_name}.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = lock_path.open("x", encoding="utf-8")
        except FileExistsError as exc:
            raise RuntimeError(f"consolidation lock already held: {lock_name}") from exc
        try:
            fd.write(datetime.now(UTC).isoformat())
            fd.flush()
            yield lock_path
        finally:
            fd.close()
            lock_path.unlink(missing_ok=True)

    def _write_snapshots(self, snapshots: list[SessionMemorySnapshot]) -> None:
        path = self._root / "session_snapshots.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps(snapshot.to_dict(), ensure_ascii=False) for snapshot in snapshots]
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    @staticmethod
    def _read_json_dict(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}
