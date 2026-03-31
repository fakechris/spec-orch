from __future__ import annotations

from pathlib import Path

from spec_orch.runtime_chain.models import (
    ChainPhase,
    RuntimeChainEvent,
    RuntimeChainStatus,
    RuntimeSubjectKind,
)
from spec_orch.runtime_chain.store import (
    CHAIN_EVENTS_FILENAME,
    CHAIN_STATUS_FILENAME,
    append_chain_event,
    read_chain_events,
    read_chain_status,
    write_chain_status,
)


def _event(*, span_id: str, phase: ChainPhase) -> RuntimeChainEvent:
    return RuntimeChainEvent(
        chain_id="chain-mission-123",
        span_id=span_id,
        parent_span_id="span-mission-root",
        subject_kind=RuntimeSubjectKind.PACKET,
        subject_id="packet-01",
        phase=phase,
        status_reason="test",
        session_refs={"worker_session": "acpx-packet-01"},
        artifact_refs={"worker_turn": "workers/p01/telemetry/worker_turn.json"},
        updated_at="2026-03-31T12:00:00Z",
    )


def test_append_chain_event_creates_chain_events_jsonl(tmp_path: Path) -> None:
    event_path = append_chain_event(tmp_path, _event(span_id="span-01", phase=ChainPhase.STARTED))

    assert event_path == tmp_path / CHAIN_EVENTS_FILENAME
    assert event_path.exists()

    events = read_chain_events(tmp_path)

    assert [event.span_id for event in events] == ["span-01"]
    assert events[0].phase is ChainPhase.STARTED


def test_append_chain_event_preserves_existing_events(tmp_path: Path) -> None:
    append_chain_event(tmp_path, _event(span_id="span-01", phase=ChainPhase.STARTED))
    append_chain_event(tmp_path, _event(span_id="span-02", phase=ChainPhase.COMPLETED))

    events = read_chain_events(tmp_path)

    assert [(event.span_id, event.phase.value) for event in events] == [
        ("span-01", "started"),
        ("span-02", "completed"),
    ]


def test_write_chain_status_persists_latest_snapshot(tmp_path: Path) -> None:
    status = RuntimeChainStatus(
        chain_id="chain-mission-123",
        active_span_id="span-supervisor-01",
        subject_kind=RuntimeSubjectKind.SUPERVISOR,
        subject_id="round-01:supervisor",
        phase=ChainPhase.HEARTBEAT,
        status_reason="waiting_for_model",
        session_refs={"llm_request": "req-1"},
        artifact_refs={"round_summary": "rounds/round-01/round_summary.json"},
        updated_at="2026-03-31T12:01:00Z",
    )

    status_path = write_chain_status(tmp_path, status)

    assert status_path == tmp_path / CHAIN_STATUS_FILENAME
    assert status_path.exists()

    restored = read_chain_status(tmp_path)

    assert restored == status


def test_read_chain_status_returns_none_when_missing(tmp_path: Path) -> None:
    assert read_chain_status(tmp_path) is None
