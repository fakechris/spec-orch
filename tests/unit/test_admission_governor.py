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
    assert decision["required_budgets"] == [
        "daemon:max_concurrent",
        "mission:max_concurrent",
        "worker:max_concurrent",
        "verifier:max_concurrent",
    ]
    assert decision["granted_budgets"] == []
    assert decision["queue_position"] == 2
    assert decision["pressure_reason"] == "daemon_concurrency_limit"
    assert [scope["runtime_role"] for scope in decision["budget_scopes"]] == [
        "daemon",
        "mission",
        "worker",
        "verifier",
    ]
    assert decision["budget_scopes"][0]["budget_state"] == "saturated"
    assert decision["budget_scopes"][0]["reason"] == "daemon_concurrency_limit"

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
    assert [item["subject_kind"] for item in snapshot["resource_budgets"]] == [
        "daemon",
        "mission",
        "worker",
        "verifier",
    ]
    assert snapshot["resource_budgets"][0]["budget_key"] == "daemon:max_concurrent"
    assert snapshot["resource_budgets"][0]["budget_state"] == "saturated"
    assert snapshot["pressure_signals"][0]["pressure_kind"] == "concurrency"
    assert snapshot["pressure_signals"][0]["subject_kind"] == "daemon"
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


def test_admission_governor_degrades_when_verifier_budget_is_saturated(
    tmp_path: Path,
) -> None:
    from spec_orch.services.admission_governor import (
        AdmissionGovernor,
        load_admission_governor_snapshot,
    )

    governor = AdmissionGovernor(tmp_path, max_concurrent=2, verifier_max_concurrent=1)

    decision = governor.evaluate_issue(
        "SPC-413",
        in_progress_count=0,
        mission_in_progress_count=0,
        worker_in_progress_count=0,
        verifier_in_progress_count=1,
        is_hotfix=False,
        recorded_at="2026-04-03T10:05:00+00:00",
    )

    assert decision["decision"] == "degrade"
    assert decision["pressure_reason"] == "verifier_capacity_limit"
    assert decision["degrade_reason"] == "verification_capacity_saturated"
    assert "verifier:max_concurrent" not in decision["granted_budgets"]

    governor.record_decision(decision)
    snapshot = load_admission_governor_snapshot(tmp_path)

    assert snapshot["queue"] == []
    verifier_budget = next(
        item for item in snapshot["resource_budgets"] if item["subject_kind"] == "verifier"
    )
    assert verifier_budget["budget_key"] == "verifier:max_concurrent"
    assert verifier_budget["budget_state"] == "saturated"
    verifier_signal = next(
        item for item in snapshot["pressure_signals"] if item["subject_kind"] == "verifier"
    )
    assert verifier_signal["reason"] == "verifier_capacity_limit"
    assert snapshot["admission_decisions"][0]["decision"] == "degrade"


def test_admission_governor_rejects_when_worker_budget_hits_hard_limit(
    tmp_path: Path,
) -> None:
    from spec_orch.services.admission_governor import (
        AdmissionGovernor,
        load_admission_governor_snapshot,
    )

    governor = AdmissionGovernor(tmp_path, max_concurrent=2, worker_max_concurrent=1)

    decision = governor.evaluate_issue(
        "SPC-414",
        in_progress_count=0,
        mission_in_progress_count=0,
        worker_in_progress_count=1,
        verifier_in_progress_count=0,
        is_hotfix=False,
        recorded_at="2026-04-03T10:07:00+00:00",
    )

    assert decision["decision"] == "reject"
    assert decision["pressure_reason"] == "worker_capacity_hard_limit"
    assert decision["queue_position"] is None

    governor.record_decision(decision)
    snapshot = load_admission_governor_snapshot(tmp_path)

    assert snapshot["queue"] == []
    worker_budget = next(
        item for item in snapshot["resource_budgets"] if item["subject_kind"] == "worker"
    )
    assert worker_budget["budget_key"] == "worker:max_concurrent"
    assert worker_budget["budget_state"] == "saturated"
    worker_signal = next(
        item for item in snapshot["pressure_signals"] if item["subject_kind"] == "worker"
    )
    assert worker_signal["reason"] == "worker_capacity_hard_limit"
    assert snapshot["admission_decisions"][0]["decision"] == "reject"
