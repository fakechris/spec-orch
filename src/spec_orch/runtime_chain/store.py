from __future__ import annotations

import json
from pathlib import Path

from spec_orch.runtime_chain.models import RuntimeChainEvent, RuntimeChainStatus
from spec_orch.services.io import atomic_write_json

CHAIN_EVENTS_FILENAME = "chain_events.jsonl"
CHAIN_STATUS_FILENAME = "chain_status.json"


def append_chain_event(root: Path, event: RuntimeChainEvent) -> Path:
    path = Path(root) / CHAIN_EVENTS_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
    return path


def read_chain_events(root: Path) -> list[RuntimeChainEvent]:
    path = Path(root) / CHAIN_EVENTS_FILENAME
    if not path.exists():
        return []
    events: list[RuntimeChainEvent] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            events.append(RuntimeChainEvent.from_dict(payload))
    return events


def write_chain_status(root: Path, status: RuntimeChainStatus) -> Path:
    path = Path(root) / CHAIN_STATUS_FILENAME
    atomic_write_json(path, status.to_dict())
    return path


def read_chain_status(root: Path) -> RuntimeChainStatus | None:
    path = Path(root) / CHAIN_STATUS_FILENAME
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    return RuntimeChainStatus.from_dict(payload)


def read_chain_lineage(chain_root: Path) -> dict[str, str] | None:
    """Read the mission chain lineage ref from the root event of a chain.

    Returns the ``mission_chain_ref`` dict from the first event's
    ``session_refs`` if present, otherwise ``None``.
    """
    events = read_chain_events(chain_root)
    if not events:
        return None
    root_event = events[0]
    ref = root_event.session_refs.get("mission_chain_ref")
    if isinstance(ref, dict):
        return {str(k): str(v) for k, v in ref.items()}
    return None


__all__ = [
    "CHAIN_EVENTS_FILENAME",
    "CHAIN_STATUS_FILENAME",
    "append_chain_event",
    "read_chain_events",
    "read_chain_lineage",
    "read_chain_status",
    "write_chain_status",
]
