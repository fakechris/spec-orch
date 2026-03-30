from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ExecutionUnitKind(StrEnum):
    ISSUE = "issue"
    WORK_PACKET = "work_packet"


class ExecutionOwnerKind(StrEnum):
    RUN_CONTROLLER = "run_controller"
    PACKET_EXECUTOR = "packet_executor"
    ROUND_WORKER = "round_worker"


class ContinuityKind(StrEnum):
    FILE_BACKED_RUN = "file_backed_run"
    WORKER_SESSION = "worker_session"
    ONESHOT_WORKER = "oneshot_worker"
    SUBPROCESS_PACKET = "subprocess_packet"


class ExecutionAttemptState(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ExecutionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"
    BLOCKED = "blocked"


class ArtifactScope(StrEnum):
    LEAF = "leaf"
    ROUND = "round"


class SubjectKind(StrEnum):
    ISSUE = "issue"
    WORK_PACKET = "work_packet"
    ROUND = "round"
    MISSION = "mission"


class ArtifactCarrierKind(StrEnum):
    JSON = "json"
    JSONL = "jsonl"
    MARKDOWN = "markdown"
    DIRECTORY = "directory"
    FILE = "file"


@dataclass(slots=True)
class ArtifactRef:
    key: str
    scope: ArtifactScope
    producer_kind: str
    subject_kind: SubjectKind
    carrier_kind: ArtifactCarrierKind
    path: str


@dataclass(slots=True)
class ExecutionOutcome:
    unit_kind: ExecutionUnitKind
    owner_kind: ExecutionOwnerKind
    status: ExecutionStatus
    build: Any
    verification: Any | None = None
    review: Any | None = None
    gate: Any | None = None
    artifacts: dict[str, ArtifactRef | None] = field(default_factory=dict)


@dataclass(slots=True)
class ExecutionAttempt:
    attempt_id: str
    unit_kind: ExecutionUnitKind
    unit_id: str
    owner_kind: ExecutionOwnerKind
    continuity_kind: ContinuityKind
    workspace_root: str
    outcome: ExecutionOutcome
    continuity_id: str | None = None
    attempt_state: ExecutionAttemptState = ExecutionAttemptState.CREATED
    started_at: str | None = None
    completed_at: str | None = None


@dataclass(slots=True)
class SupervisionCycle:
    cycle_id: str
    mission_id: str
    round_id: str
    packet_ids: list[str] = field(default_factory=list)


__all__ = [
    "ArtifactCarrierKind",
    "ArtifactRef",
    "ArtifactScope",
    "ContinuityKind",
    "ExecutionAttempt",
    "ExecutionAttemptState",
    "ExecutionOutcome",
    "ExecutionOwnerKind",
    "ExecutionStatus",
    "ExecutionUnitKind",
    "SubjectKind",
    "SupervisionCycle",
]
