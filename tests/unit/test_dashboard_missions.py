from __future__ import annotations

import json
from pathlib import Path


def test_mission_evidence_counts_prefers_decision_core_approval_history(tmp_path: Path) -> None:
    from spec_orch.dashboard.missions import _mission_evidence_counts

    specs_dir = tmp_path / "docs" / "specs" / "mission-evidence"
    rounds_dir = specs_dir / "rounds"
    operator_dir = specs_dir / "operator"
    (rounds_dir / "round-01").mkdir(parents=True)
    operator_dir.mkdir(parents=True)

    (rounds_dir / "round-01" / "round_summary.json").write_text("{}", encoding="utf-8")
    (operator_dir / "intervention_responses.jsonl").write_text(
        json.dumps(
            {
                "timestamp": "2026-03-30T02:00:00+00:00",
                "intervention_id": "int-1",
                "decision_record_id": "mission-evidence-round-1-review",
                "action_key": "approve",
                "label": "Approve",
                "message": "@approve Approve this round.",
                "channel": "web-dashboard",
                "status": "applied",
                "effect": "approval_granted",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    counts = _mission_evidence_counts(specs_dir)

    assert counts == {
        "round_count": 1,
        "visual_round_count": 0,
        "approval_action_count": 1,
    }
