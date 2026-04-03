from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from typing import Any, cast


def _serialize(value: Any) -> Any:
    if is_dataclass(value):
        return {item.name: _serialize(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    return value


def _serialize_dict(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], _serialize(value))


@dataclass(slots=True)
class SubjectRef:
    subject_id: str
    subject_kind: str
    subject_title: str = ""
    source_ref: str = ""
    owner_ref: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _serialize_dict(self)


@dataclass(slots=True)
class ExecutionSession:
    execution_session_id: str
    run_id: str
    agent_id: str
    runtime_id: str
    phase: str
    health: str
    status_reason: str
    queue_state: str
    last_event_at: str
    available_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _serialize_dict(self)


@dataclass(slots=True)
class Agent:
    agent_id: str
    name: str
    role: str
    status: str
    runtime_id: str
    active_workspace_id: str
    last_active_at: str
    recent_subject_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _serialize_dict(self)


@dataclass(slots=True)
class Runtime:
    runtime_id: str
    runtime_kind: str
    mode: str
    health: str
    heartbeat_at: str
    usage_summary: dict[str, Any] = field(default_factory=dict)
    activity_summary: dict[str, Any] = field(default_factory=dict)
    degradation_flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _serialize_dict(self)


@dataclass(slots=True)
class ActiveWork:
    active_work_id: str
    workspace_id: str
    subject_id: str
    subject_kind: str
    agent_id: str
    runtime_id: str
    phase: str
    health: str
    status_reason: str
    started_at: str
    updated_at: str
    available_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _serialize_dict(self)


@dataclass(slots=True)
class QueueEntry:
    queue_entry_id: str
    workspace_id: str
    subject_id: str
    queue_name: str
    position: int
    queue_state: str
    claimed_by_agent_id: str
    claimed_at: str

    def to_dict(self) -> dict[str, Any]:
        return _serialize_dict(self)


@dataclass(slots=True)
class ResourceBudget:
    budget_id: str
    workspace_id: str
    subject_id: str
    subject_kind: str
    budget_key: str
    budget_state: str
    remaining_steps: int
    remaining_loop_budget: int
    continuation_count: int
    recent_token_growth: int
    justified: bool
    recorded_at: str

    def to_dict(self) -> dict[str, Any]:
        return _serialize_dict(self)


@dataclass(slots=True)
class PressureSignal:
    pressure_signal_id: str
    workspace_id: str
    subject_id: str
    subject_kind: str
    budget_key: str
    pressure_kind: str
    severity: str
    reason: str
    details: dict[str, Any] = field(default_factory=dict)
    recorded_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _serialize_dict(self)


@dataclass(slots=True)
class AdmissionDecision:
    admission_decision_id: str
    workspace_id: str
    subject_id: str
    subject_kind: str
    decision: str
    required_budgets: list[str] = field(default_factory=list)
    granted_budgets: list[str] = field(default_factory=list)
    queue_position: int | None = None
    pressure_reason: str = ""
    degrade_reason: str = ""
    recorded_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _serialize_dict(self)


@dataclass(slots=True)
class OperatorIntervention:
    intervention_id: str
    workspace_id: str
    action: str
    requested_by: str
    requested_at: str
    outcome: str
    outcome_reason: str
    audit_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _serialize_dict(self)


@dataclass(slots=True)
class ExecutionEvent:
    event_id: str
    workspace_id: str
    execution_session_id: str
    event_type: str
    event_summary: str
    event_source: str
    created_at: str
    artifact_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _serialize_dict(self)


@dataclass(slots=True)
class ArtifactEnvelope:
    artifact_key: str
    producer_kind: str
    carrier_kind: str
    subject_kind: str
    scope: str
    path: str

    def to_dict(self) -> dict[str, Any]:
        return _serialize_dict(self)


@dataclass(slots=True)
class EvidenceBundle:
    evidence_bundle_id: str
    workspace_id: str
    origin_run_id: str
    bundle_kind: str
    artifact_refs: list[ArtifactEnvelope] = field(default_factory=list)
    route_refs: list[str] = field(default_factory=list)
    step_refs: list[str] = field(default_factory=list)
    evidence_summary: str = ""
    collected_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _serialize_dict(self)


@dataclass(slots=True)
class Observation:
    summary: str
    route: str = ""
    details: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    critique_axis: str = ""
    operator_task: str = ""
    why_it_matters: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _serialize_dict(self)


@dataclass(slots=True)
class CandidateFinding:
    finding_id: str
    claim: str
    surface: str = ""
    route: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    confidence: float = 0.0
    impact_if_true: str = ""
    repro_status: str = ""
    hold_reason: str = ""
    promotion_test: str = ""
    recommended_next_step: str = ""
    dedupe_key: str = ""
    critique_axis: str = ""
    operator_task: str = ""
    why_it_matters: str = ""
    baseline_ref: str = ""
    origin_step: str = ""
    graph_profile: str = ""
    compare_overlay: bool = False
    source_observation_id: str = ""
    reviewer_identity: str = ""
    review_note: str = ""
    dismissal_reason: str = ""
    superseded_by: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _serialize_dict(self)


@dataclass(slots=True)
class Judgment:
    judgment_id: str
    workspace_id: str
    base_run_mode: str
    graph_profile: str
    risk_posture: str
    judgment_class: str
    review_state: str
    confidence: float
    impact_if_true: str
    repro_status: str
    recommended_next_step: str
    summary: str = ""
    candidate_finding: CandidateFinding | None = None
    observation: Observation | None = None

    def to_dict(self) -> dict[str, Any]:
        return _serialize_dict(self)


@dataclass(slots=True)
class JudgmentTimelineEntry:
    timeline_entry_id: str
    workspace_id: str
    judgment_id: str
    event_type: str
    event_summary: str
    created_at: str
    artifact_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _serialize_dict(self)


@dataclass(slots=True)
class CompareOverlay:
    compare_overlay_id: str
    workspace_id: str
    baseline_ref: str
    compare_state: str
    drift_summary: str
    artifact_drift_refs: list[str] = field(default_factory=list)
    judgment_drift_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _serialize_dict(self)


@dataclass(slots=True)
class SurfacePack:
    surface_pack_id: str
    workspace_id: str
    surface_name: str
    active_axes: list[str] = field(default_factory=list)
    known_routes: list[str] = field(default_factory=list)
    graph_profiles: list[str] = field(default_factory=list)
    baseline_refs: list[str] = field(default_factory=list)
    pack_key: str = ""
    safe_action_budget: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _serialize_dict(self)


@dataclass(slots=True)
class PromotedFinding:
    promoted_finding_id: str
    workspace_id: str
    origin_judgment_ref: str
    origin_review_ref: str
    promotion_target: str
    promoted_at: str
    promoted_by: str
    promotion_reason: str

    def to_dict(self) -> dict[str, Any]:
        return _serialize_dict(self)


@dataclass(slots=True)
class MemoryEntryRef:
    memory_ref_id: str
    origin_finding_ref: str
    memory_layer: str
    distillation_summary: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return _serialize_dict(self)


@dataclass(slots=True)
class EvolutionProposalRef:
    evolution_ref_id: str
    origin_finding_ref: str
    proposal_kind: str
    proposal_summary: str
    review_state: str
    promotion_state: str

    def to_dict(self) -> dict[str, Any]:
        return _serialize_dict(self)


@dataclass(slots=True)
class LearningLineage:
    learning_lineage_id: str
    workspace_id: str
    promoted_refs: list[str] = field(default_factory=list)
    memory_refs: list[MemoryEntryRef] = field(default_factory=list)
    fixture_refs: list[str] = field(default_factory=list)
    policy_refs: list[str] = field(default_factory=list)
    evolution_refs: list[EvolutionProposalRef] = field(default_factory=list)
    status: str = "pending"

    def to_dict(self) -> dict[str, Any]:
        return _serialize_dict(self)


@dataclass(slots=True)
class Workspace:
    workspace_id: str
    workspace_kind: str
    workspace_title: str
    subject_id: str
    subject_kind: str
    source_system: str
    state_summary: str
    created_at: str
    updated_at: str
    active_execution_session_id: str
    active_judgment_id: str
    learning_timeline_id: str
    subject: SubjectRef
    active_execution: ExecutionSession
    active_judgment: Judgment
    learning_lineage: LearningLineage

    def to_dict(self) -> dict[str, Any]:
        return _serialize_dict(self)


__all__ = [
    "ActiveWork",
    "AdmissionDecision",
    "Agent",
    "ArtifactEnvelope",
    "CandidateFinding",
    "CompareOverlay",
    "EvidenceBundle",
    "EvolutionProposalRef",
    "ExecutionEvent",
    "ExecutionSession",
    "Judgment",
    "JudgmentTimelineEntry",
    "LearningLineage",
    "MemoryEntryRef",
    "Observation",
    "OperatorIntervention",
    "PressureSignal",
    "PromotedFinding",
    "QueueEntry",
    "ResourceBudget",
    "Runtime",
    "SurfacePack",
    "SubjectRef",
    "Workspace",
]
