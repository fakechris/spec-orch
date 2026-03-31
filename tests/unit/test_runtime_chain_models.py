from __future__ import annotations

from spec_orch.runtime_chain import models
from spec_orch.runtime_chain.models import (
    ChainPhase,
    RuntimeChainEvent,
    RuntimeChainStatus,
    RuntimeSubjectKind,
)


def test_runtime_chain_package_exposes_models_and_store_modules() -> None:
    from spec_orch import runtime_chain

    assert runtime_chain.__all__ == ["models", "store"]


def test_runtime_chain_event_round_trips_to_and_from_dict() -> None:
    event = RuntimeChainEvent(
        chain_id="chain-mission-123",
        span_id="span-round-01",
        parent_span_id="span-mission-root",
        subject_kind=RuntimeSubjectKind.ROUND,
        subject_id="round-01",
        phase=ChainPhase.HEARTBEAT,
        status_reason="waiting_for_supervisor_model",
        session_refs={"worker_session": "acpx-round-01"},
        artifact_refs={"round_summary": "rounds/round-01/round_summary.json"},
        updated_at="2026-03-31T12:00:00Z",
    )

    payload = event.to_dict()

    assert payload["chain_id"] == "chain-mission-123"
    assert payload["subject_kind"] == "round"
    assert payload["phase"] == "heartbeat"

    restored = RuntimeChainEvent.from_dict(payload)

    assert restored == event


def test_runtime_chain_status_round_trips_to_and_from_dict() -> None:
    status = RuntimeChainStatus(
        chain_id="chain-issue-123",
        active_span_id="span-supervisor-01",
        subject_kind=RuntimeSubjectKind.SUPERVISOR,
        subject_id="round-01:supervisor",
        phase=ChainPhase.DEGRADED,
        status_reason="llm_timeout_fallback",
        session_refs={"llm_request": "req-123"},
        artifact_refs={"decision_record": "rounds/round-01/decision_record.json"},
        updated_at="2026-03-31T12:01:00Z",
    )

    payload = status.to_dict()

    assert payload["phase"] == "degraded"
    assert payload["active_span_id"] == "span-supervisor-01"

    restored = RuntimeChainStatus.from_dict(payload)

    assert restored == status


def test_runtime_chain_model_exports_are_stable() -> None:
    assert models.__all__ == [
        "ChainPhase",
        "RuntimeChainEvent",
        "RuntimeChainStatus",
        "RuntimeSubjectKind",
    ]
