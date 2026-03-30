from __future__ import annotations

from spec_orch.domain.execution_semantics import (
    ArtifactCarrierKind,
    ArtifactRef,
    ArtifactScope,
    ContinuityKind,
    ExecutionAttempt,
    ExecutionAttemptState,
    ExecutionOutcome,
    ExecutionOwnerKind,
    ExecutionStatus,
    ExecutionUnitKind,
    SubjectKind,
    SupervisionCycle,
)


def test_execution_semantics_enum_values_match_architecture_contract() -> None:
    assert [member.value for member in ExecutionUnitKind] == ["issue", "work_packet"]
    assert [member.value for member in ExecutionOwnerKind] == [
        "run_controller",
        "packet_executor",
        "round_worker",
    ]
    assert [member.value for member in ContinuityKind] == [
        "file_backed_run",
        "worker_session",
        "oneshot_worker",
        "subprocess_packet",
    ]
    assert [member.value for member in ExecutionAttemptState] == [
        "created",
        "running",
        "completed",
        "cancelled",
    ]
    assert [member.value for member in ExecutionStatus] == [
        "succeeded",
        "failed",
        "partial",
        "blocked",
    ]
    assert [member.value for member in ArtifactScope] == ["leaf", "round"]
    assert [member.value for member in SubjectKind] == [
        "issue",
        "work_packet",
        "round",
        "mission",
    ]
    assert [member.value for member in ArtifactCarrierKind] == [
        "json",
        "jsonl",
        "markdown",
        "directory",
        "file",
    ]


def test_execution_outcome_allows_sparse_leaf_outcomes() -> None:
    artifact = ArtifactRef(
        key="builder_report",
        scope=ArtifactScope.LEAF,
        producer_kind="builder_adapter",
        subject_kind=SubjectKind.WORK_PACKET,
        carrier_kind=ArtifactCarrierKind.JSON,
        path="docs/specs/mission-123/workers/p1/builder_report.json",
    )

    outcome = ExecutionOutcome(
        unit_kind=ExecutionUnitKind.WORK_PACKET,
        owner_kind=ExecutionOwnerKind.ROUND_WORKER,
        status=ExecutionStatus.SUCCEEDED,
        build={"succeeded": True},
        artifacts={"builder_report": artifact},
    )

    assert outcome.verification is None
    assert outcome.review is None
    assert outcome.gate is None
    assert outcome.artifacts["builder_report"] is artifact


def test_execution_attempt_supports_optional_continuity_id_and_completion() -> None:
    outcome = ExecutionOutcome(
        unit_kind=ExecutionUnitKind.WORK_PACKET,
        owner_kind=ExecutionOwnerKind.PACKET_EXECUTOR,
        status=ExecutionStatus.PARTIAL,
        build={"succeeded": True},
        artifacts={},
    )

    attempt = ExecutionAttempt(
        attempt_id="wave-1:packet-2",
        unit_kind=ExecutionUnitKind.WORK_PACKET,
        unit_id="packet-2",
        owner_kind=ExecutionOwnerKind.PACKET_EXECUTOR,
        continuity_kind=ContinuityKind.SUBPROCESS_PACKET,
        continuity_id=None,
        workspace_root="/tmp/spec-orch/packet-2",
        attempt_state=ExecutionAttemptState.COMPLETED,
        outcome=outcome,
    )

    assert attempt.continuity_id is None
    assert attempt.completed_at is None
    assert attempt.outcome.status is ExecutionStatus.PARTIAL


def test_execution_attempt_defaults_started_at_to_none_when_unknown() -> None:
    outcome = ExecutionOutcome(
        unit_kind=ExecutionUnitKind.WORK_PACKET,
        owner_kind=ExecutionOwnerKind.PACKET_EXECUTOR,
        status=ExecutionStatus.PARTIAL,
        build={"succeeded": True},
        artifacts={},
    )

    attempt = ExecutionAttempt(
        attempt_id="wave-1:packet-3",
        unit_kind=ExecutionUnitKind.WORK_PACKET,
        unit_id="packet-3",
        owner_kind=ExecutionOwnerKind.PACKET_EXECUTOR,
        continuity_kind=ContinuityKind.SUBPROCESS_PACKET,
        workspace_root="/tmp/spec-orch/packet-3",
        outcome=outcome,
    )

    assert attempt.started_at is None


def test_supervision_cycle_is_distinct_from_execution_attempt() -> None:
    cycle = SupervisionCycle(
        cycle_id="mission-123:round-4",
        mission_id="mission-123",
        round_id="round-4",
        packet_ids=["packet-1", "packet-2"],
    )

    assert cycle.cycle_id == "mission-123:round-4"
    assert cycle.packet_ids == ["packet-1", "packet-2"]
