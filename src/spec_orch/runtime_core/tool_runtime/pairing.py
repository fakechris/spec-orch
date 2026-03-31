from __future__ import annotations

import json
from pathlib import Path

from spec_orch.runtime_core.tool_runtime.models import ToolPairingRecord

TOOL_PAIRINGS_FILENAME = "tool_pairings.jsonl"


def append_tool_pairing(root: Path, record: ToolPairingRecord) -> Path:
    path = Path(root) / TOOL_PAIRINGS_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
    return path


def read_tool_pairings(root: Path) -> list[ToolPairingRecord]:
    path = Path(root) / TOOL_PAIRINGS_FILENAME
    if not path.exists():
        return []
    rows: list[ToolPairingRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(ToolPairingRecord.from_dict(payload))
    return rows


__all__ = [
    "TOOL_PAIRINGS_FILENAME",
    "append_tool_pairing",
    "read_tool_pairings",
]
