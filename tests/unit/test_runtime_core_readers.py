from __future__ import annotations

import json
from pathlib import Path

from spec_orch.runtime_core.readers import (
    read_issue_execution_attempt,
    read_round_supervision_cycle,
)
from spec_orch.services.execution_semantics_reader import (
    read_issue_execution_attempt as shim_read_issue_execution_attempt,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_service_reader_is_runtime_core_shim() -> None:
    assert shim_read_issue_execution_attempt is read_issue_execution_attempt


def test_runtime_core_round_reader_supports_embedded_decision(tmp_path: Path) -> None:
    round_dir = tmp_path / "docs/specs/mission-core/rounds/round-02"
    _write_json(
        round_dir / "round_summary.json",
        {
            "round_id": 2,
            "worker_results": [{"packet_id": "pkt-1"}],
            "decision": {
                "action": "ask_human",
                "summary": "Need approval before continue.",
            },
        },
    )

    payload = read_round_supervision_cycle(round_dir)

    assert payload is not None
    assert payload["decision"] == {
        "action": "ask_human",
        "summary": "Need approval before continue.",
    }
