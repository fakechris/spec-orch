"""Tests for cross-chain lineage: mission -> round -> issue tracing."""

from __future__ import annotations

from pathlib import Path

from spec_orch.runtime_chain.models import (
    ChainPhase,
    RuntimeChainEvent,
    RuntimeSubjectKind,
    build_chain_lineage_ref,
)
from spec_orch.runtime_chain.store import (
    append_chain_event,
    read_chain_events,
    read_chain_lineage,
)


def test_build_chain_lineage_ref_creates_correct_dict() -> None:
    ref = build_chain_lineage_ref(
        chain_id="chain_xyz",
        mission_span_id="chain_xyz:mission",
        round_span_id="chain_xyz:round:01",
    )

    assert ref == {
        "mission_chain_id": "chain_xyz",
        "mission_span_id": "chain_xyz:mission",
        "round_span_id": "chain_xyz:round:01",
    }


def test_issue_chain_event_with_session_refs_persists_and_reads_back(
    tmp_path: Path,
) -> None:
    lineage = build_chain_lineage_ref(
        chain_id="chain_abc",
        mission_span_id="chain_abc:mission",
        round_span_id="chain_abc:round:02",
    )
    event = RuntimeChainEvent(
        chain_id="run-001",
        span_id="run-001:issue",
        parent_span_id=None,
        subject_kind=RuntimeSubjectKind.ISSUE,
        subject_id="ISSUE-42",
        phase=ChainPhase.STARTED,
        status_reason="issue_run_started",
        session_refs={"mission_chain_ref": lineage},
        artifact_refs={"workspace": "/tmp/ws"},
        updated_at="2026-04-06T10:00:00Z",
    )

    append_chain_event(tmp_path, event)
    events = read_chain_events(tmp_path)

    assert len(events) == 1
    restored = events[0]
    assert restored.session_refs["mission_chain_ref"] == {
        "mission_chain_id": "chain_abc",
        "mission_span_id": "chain_abc:mission",
        "round_span_id": "chain_abc:round:02",
    }


def test_read_chain_lineage_returns_mission_reference(tmp_path: Path) -> None:
    lineage = build_chain_lineage_ref(
        chain_id="chain_m1",
        mission_span_id="chain_m1:mission",
        round_span_id="chain_m1:round:03",
    )
    root_event = RuntimeChainEvent(
        chain_id="run-099",
        span_id="run-099:issue",
        parent_span_id=None,
        subject_kind=RuntimeSubjectKind.ISSUE,
        subject_id="ISSUE-99",
        phase=ChainPhase.STARTED,
        status_reason="issue_run_started",
        session_refs={"mission_chain_ref": lineage},
        updated_at="2026-04-06T11:00:00Z",
    )
    # Also append a child event without lineage to ensure only root is checked
    child_event = RuntimeChainEvent(
        chain_id="run-099",
        span_id="run-099:issue:builder",
        parent_span_id="run-099:issue",
        subject_kind=RuntimeSubjectKind.ISSUE,
        subject_id="ISSUE-99",
        phase=ChainPhase.STARTED,
        status_reason="builder_started",
        updated_at="2026-04-06T11:01:00Z",
    )
    append_chain_event(tmp_path, root_event)
    append_chain_event(tmp_path, child_event)

    result = read_chain_lineage(tmp_path)

    assert result == {
        "mission_chain_id": "chain_m1",
        "mission_span_id": "chain_m1:mission",
        "round_span_id": "chain_m1:round:03",
    }


def test_read_chain_lineage_returns_none_when_no_events(tmp_path: Path) -> None:
    assert read_chain_lineage(tmp_path) is None


def test_read_chain_lineage_returns_none_when_no_lineage_ref(
    tmp_path: Path,
) -> None:
    event = RuntimeChainEvent(
        chain_id="run-standalone",
        span_id="run-standalone:issue",
        parent_span_id=None,
        subject_kind=RuntimeSubjectKind.ISSUE,
        subject_id="ISSUE-50",
        phase=ChainPhase.STARTED,
        status_reason="issue_run_started",
        updated_at="2026-04-06T12:00:00Z",
    )
    append_chain_event(tmp_path, event)

    assert read_chain_lineage(tmp_path) is None
