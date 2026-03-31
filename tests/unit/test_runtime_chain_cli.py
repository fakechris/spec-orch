from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from spec_orch.cli import app
from spec_orch.runtime_chain.models import (
    ChainPhase,
    RuntimeChainEvent,
    RuntimeChainStatus,
    RuntimeSubjectKind,
)
from spec_orch.runtime_chain.store import append_chain_event, write_chain_status


def _write_issue_chain(repo_root: Path, issue_id: str = "SPC-1") -> Path:
    chain_root = repo_root / ".spec_orch_runs" / issue_id / "telemetry" / "runtime_chain"
    append_chain_event(
        chain_root,
        RuntimeChainEvent(
            chain_id="issue-chain-1",
            span_id="issue-chain-1:issue",
            parent_span_id=None,
            subject_kind=RuntimeSubjectKind.ISSUE,
            subject_id=issue_id,
            phase=ChainPhase.STARTED,
            status_reason="issue_run_started",
            updated_at="2026-03-31T07:00:00+00:00",
        ),
    )
    append_chain_event(
        chain_root,
        RuntimeChainEvent(
            chain_id="issue-chain-1",
            span_id="issue-chain-1:issue",
            parent_span_id=None,
            subject_kind=RuntimeSubjectKind.ISSUE,
            subject_id=issue_id,
            phase=ChainPhase.DEGRADED,
            status_reason="waiting_for_human_review",
            updated_at="2026-03-31T07:05:00+00:00",
        ),
    )
    write_chain_status(
        chain_root,
        RuntimeChainStatus(
            chain_id="issue-chain-1",
            active_span_id="issue-chain-1:issue",
            subject_kind=RuntimeSubjectKind.ISSUE,
            subject_id=issue_id,
            phase=ChainPhase.DEGRADED,
            status_reason="waiting_for_human_review",
            updated_at="2026-03-31T07:05:00+00:00",
        ),
    )
    return chain_root


def _write_mission_chain(repo_root: Path, mission_id: str = "mission-1") -> Path:
    chain_root = repo_root / "docs" / "specs" / mission_id / "operator" / "runtime_chain"
    append_chain_event(
        chain_root,
        RuntimeChainEvent(
            chain_id="mission-chain-1",
            span_id="mission-chain-1:mission",
            parent_span_id=None,
            subject_kind=RuntimeSubjectKind.MISSION,
            subject_id=mission_id,
            phase=ChainPhase.STARTED,
            status_reason="mission_supervision_started",
            updated_at="2026-03-31T08:00:00+00:00",
        ),
    )
    append_chain_event(
        chain_root,
        RuntimeChainEvent(
            chain_id="mission-chain-1",
            span_id="mission-chain-1:round:01",
            parent_span_id="mission-chain-1:mission",
            subject_kind=RuntimeSubjectKind.ROUND,
            subject_id="round-01",
            phase=ChainPhase.HEARTBEAT,
            status_reason="supervisor_waiting",
            updated_at="2026-03-31T08:01:00+00:00",
        ),
    )
    append_chain_event(
        chain_root,
        RuntimeChainEvent(
            chain_id="mission-chain-2",
            span_id="mission-chain-2:mission",
            parent_span_id=None,
            subject_kind=RuntimeSubjectKind.MISSION,
            subject_id=mission_id,
            phase=ChainPhase.STARTED,
            status_reason="mission_supervision_started",
            updated_at="2026-03-31T09:00:00+00:00",
        ),
    )
    append_chain_event(
        chain_root,
        RuntimeChainEvent(
            chain_id="mission-chain-2",
            span_id="mission-chain-2:acceptance",
            parent_span_id="mission-chain-2:round:02",
            subject_kind=RuntimeSubjectKind.ACCEPTANCE,
            subject_id="acceptance-round-02",
            phase=ChainPhase.DEGRADED,
            status_reason="acceptance_model_waiting",
            updated_at="2026-03-31T09:02:00+00:00",
        ),
    )
    write_chain_status(
        chain_root,
        RuntimeChainStatus(
            chain_id="mission-chain-2",
            active_span_id="mission-chain-2:acceptance",
            subject_kind=RuntimeSubjectKind.ACCEPTANCE,
            subject_id="acceptance-round-02",
            phase=ChainPhase.DEGRADED,
            status_reason="acceptance_model_waiting",
            updated_at="2026-03-31T09:02:00+00:00",
        ),
    )
    return chain_root


def test_chain_status_reads_issue_runtime_chain_snapshot(tmp_path: Path) -> None:
    _write_issue_chain(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["chain", "status", "--issue-id", "SPC-1", "--repo-root", str(tmp_path), "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["chain_id"] == "issue-chain-1"
    assert payload["phase"] == "degraded"
    assert payload["status_reason"] == "waiting_for_human_review"
    assert payload["chain_root"].endswith(".spec_orch_runs/SPC-1/telemetry/runtime_chain")


def test_chain_tail_filters_latest_events_for_mission(tmp_path: Path) -> None:
    _write_mission_chain(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "chain",
            "tail",
            "--mission-id",
            "mission-1",
            "--repo-root",
            str(tmp_path),
            "--limit",
            "2",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["chain_root"].endswith("docs/specs/mission-1/operator/runtime_chain")
    assert payload["event_count"] == 2
    assert [event["chain_id"] for event in payload["events"]] == [
        "mission-chain-2",
        "mission-chain-2",
    ]
    assert payload["events"][-1]["status_reason"] == "acceptance_model_waiting"


def test_chain_show_filters_events_for_requested_chain(tmp_path: Path) -> None:
    _write_mission_chain(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "chain",
            "show",
            "mission-chain-1",
            "--mission-id",
            "mission-1",
            "--repo-root",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["chain_id"] == "mission-chain-1"
    assert payload["event_count"] == 2
    assert {event["chain_id"] for event in payload["events"]} == {"mission-chain-1"}
    assert payload["latest_event"]["status_reason"] == "supervisor_waiting"
