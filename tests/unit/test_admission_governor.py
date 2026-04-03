from __future__ import annotations

from pathlib import Path


def test_admission_governor_defers_when_daemon_budget_is_saturated(tmp_path: Path) -> None:
    from spec_orch.services.admission_governor import (
        AdmissionGovernor,
        load_admission_governor_snapshot,
    )

    governor = AdmissionGovernor(tmp_path, max_concurrent=1)

    decision = governor.evaluate_issue(
        "SPC-412",
        in_progress_count=1,
        is_hotfix=False,
        recorded_at="2026-04-03T10:00:00+00:00",
    )

    assert decision["decision"] == "defer"
    assert decision["required_budgets"] == ["daemon:max_concurrent"]
    assert decision["granted_budgets"] == []
    assert decision["queue_position"] == 2
    assert decision["pressure_reason"] == "max_concurrent_limit"

    governor.record_decision(decision)

    snapshot = load_admission_governor_snapshot(tmp_path)

    assert snapshot["queue"] == [
        {
            "queue_entry_id": "SPC-412:daemon_admission",
            "workspace_id": "SPC-412",
            "subject_id": "SPC-412",
            "queue_name": "daemon_admission",
            "position": 2,
            "queue_state": "defer",
            "claimed_by_agent_id": "daemon",
            "claimed_at": "2026-04-03T10:00:00+00:00",
        }
    ]
    assert snapshot["resource_budgets"][0]["budget_key"] == "daemon:max_concurrent"
    assert snapshot["resource_budgets"][0]["budget_state"] == "saturated"
    assert snapshot["pressure_signals"][0]["pressure_kind"] == "concurrency"
    assert snapshot["admission_decisions"][0]["decision"] == "defer"


def test_admission_governor_allows_workspace_id_to_differ_from_subject_id(
    tmp_path: Path,
) -> None:
    from spec_orch.services.admission_governor import (
        AdmissionGovernor,
        load_admission_governor_snapshot,
    )

    governor = AdmissionGovernor(tmp_path, max_concurrent=1)

    decision = governor.evaluate_issue(
        "SPC-412",
        workspace_id="mission-412",
        in_progress_count=1,
        is_hotfix=False,
        recorded_at="2026-04-03T10:00:00+00:00",
    )

    assert decision["workspace_id"] == "mission-412"
    assert decision["subject_id"] == "SPC-412"

    governor.record_decision(decision)
    snapshot = load_admission_governor_snapshot(tmp_path)

    assert snapshot["queue"][0]["workspace_id"] == "mission-412"
    assert snapshot["queue"][0]["subject_id"] == "SPC-412"
    assert snapshot["admission_decisions"][0]["workspace_id"] == "mission-412"
    assert snapshot["admission_decisions"][0]["subject_id"] == "SPC-412"
