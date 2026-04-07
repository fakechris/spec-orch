"""Backward-compatible re-export hub for all domain models.

All types are now defined in bounded-context submodules:

- ``domain.issue``        — Issue, RunState, verification, builder, review
- ``domain.gate``         — GateInput, GateVerdict, GateFlowControl
- ``domain.flow``         — FlowType, FlowStep, FlowGraph
- ``domain.mission``      — Mission, ExecutionPlan, rounds, parallel execution
- ``domain.acceptance``   — AcceptanceFinding, AcceptanceCampaign, etc.
- ``domain.conversation`` — Question, Decision, SpecSnapshot, threads, deviations
- ``domain.evolution``    — EvolutionProposal, EvolutionOutcome

Existing ``from spec_orch.domain.models import X`` imports continue to work.
"""

from __future__ import annotations

# --- acceptance ---
from spec_orch.domain.acceptance import (
    AcceptanceCampaign,
    AcceptanceFinding,
    AcceptanceInteractionStep,
    AcceptanceIssueProposal,
    AcceptanceMode,
    AcceptanceReviewResult,
    _coerce_confidence_score,
)

# --- conversation / spec ---
from spec_orch.domain.conversation import (
    ConversationMessage,
    ConversationThread,
    Decision,
    DeviationResolution,
    DeviationSeverity,
    PlannerResult,
    Question,
    SpecDeviation,
    SpecSnapshot,
    ThreadStatus,
)

# --- evolution ---
from spec_orch.domain.evolution import (
    EvolutionChangeType,
    EvolutionOutcome,
    EvolutionProposal,
    EvolutionValidationMethod,
)

# --- flow ---
from spec_orch.domain.flow import (
    FlowGraph,
    FlowStep,
    FlowTransitionEvent,
    FlowType,
)

# --- gate ---
from spec_orch.domain.gate import (
    GateFlowControl,
    GateInput,
    GateVerdict,
)

# --- issue ---
from spec_orch.domain.issue import (
    TERMINAL_STATES,
    ArtifactManifest,
    BuilderEvent,
    BuilderResult,
    Finding,
    Issue,
    IssueContext,
    ReviewMeta,
    ReviewSummary,
    RunResult,
    RunState,
    VerificationDetail,
    VerificationSummary,
    validate_transition,
)

# --- mission ---
from spec_orch.domain.mission import (
    ExecutionPlan,
    ExecutionPlanResult,
    Mission,
    MissionExecutionResult,
    MissionPhase,
    MissionStatus,
    PacketResult,
    ParallelConfig,
    PlanPatch,
    PlanStatus,
    RoundAction,
    RoundArtifacts,
    RoundDecision,
    RoundStatus,
    RoundSummary,
    SessionOps,
    VisualEvaluationResult,
    Wave,
    WaveResult,
    WorkPacket,
    project_mission_status,
)

__all__ = [
    # issue
    "ArtifactManifest",
    "BuilderEvent",
    "BuilderResult",
    "Finding",
    "Issue",
    "IssueContext",
    "ReviewMeta",
    "ReviewSummary",
    "RunResult",
    "RunState",
    "TERMINAL_STATES",
    "VerificationDetail",
    "VerificationSummary",
    "validate_transition",
    # gate
    "GateFlowControl",
    "GateInput",
    "GateVerdict",
    # flow
    "FlowGraph",
    "FlowStep",
    "FlowTransitionEvent",
    "FlowType",
    # mission
    "ExecutionPlan",
    "ExecutionPlanResult",
    "Mission",
    "MissionExecutionResult",
    "MissionPhase",
    "MissionStatus",
    "PacketResult",
    "ParallelConfig",
    "PlanPatch",
    "PlanStatus",
    "project_mission_status",
    "RoundAction",
    "RoundArtifacts",
    "RoundDecision",
    "RoundStatus",
    "RoundSummary",
    "SessionOps",
    "VisualEvaluationResult",
    "Wave",
    "WaveResult",
    "WorkPacket",
    # acceptance
    "AcceptanceCampaign",
    "AcceptanceFinding",
    "AcceptanceInteractionStep",
    "AcceptanceIssueProposal",
    "AcceptanceMode",
    "AcceptanceReviewResult",
    "_coerce_confidence_score",
    # conversation / spec
    "ConversationMessage",
    "ConversationThread",
    "Decision",
    "DeviationResolution",
    "DeviationSeverity",
    "PlannerResult",
    "Question",
    "SpecDeviation",
    "SpecSnapshot",
    "ThreadStatus",
    # evolution
    "EvolutionChangeType",
    "EvolutionOutcome",
    "EvolutionProposal",
    "EvolutionValidationMethod",
]
