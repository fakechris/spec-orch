from __future__ import annotations

import json
from pathlib import Path

from spec_orch.runtime_core.tool_runtime.models import ToolLifecycleEvent

TOOL_LIFECYCLE_FILENAME = "tool_lifecycle.jsonl"


def append_tool_lifecycle_event(root: Path, event: ToolLifecycleEvent) -> Path:
    path = Path(root) / TOOL_LIFECYCLE_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
    return path


def read_tool_lifecycle_events(root: Path) -> list[ToolLifecycleEvent]:
    path = Path(root) / TOOL_LIFECYCLE_FILENAME
    if not path.exists():
        return []
    rows: list[ToolLifecycleEvent] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(ToolLifecycleEvent.from_dict(payload))
    return rows
