from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from spec_orch.domain.models import (
    AcceptanceCampaign,
    AcceptanceReviewResult,
    BuilderEvent,
    BuilderResult,
    ConversationMessage,
    EvolutionOutcome,
    EvolutionProposal,
    ExecutionPlan,
    Issue,
    Mission,
    PacketResult,
    ParallelConfig,
    PlannerResult,
    ReviewSummary,
    RoundArtifacts,
    RoundDecision,
    RoundSummary,
    SpecSnapshot,
    VisualEvaluationResult,
    Wave,
    WaveResult,
    WorkPacket,
)


@runtime_checkable
class BuilderAdapter(Protocol):
    ADAPTER_NAME: str
    AGENT_NAME: str

    def run(
        self,
        *,
        issue: Issue,
        workspace: Path,
        run_id: str | None = None,
        event_logger: Callable[[dict[str, Any]], None] | None = None,
    ) -> BuilderResult: ...

    def can_handle(self, issue: Issue) -> bool:
        """Return True if this adapter can handle the given issue."""
        return True

    def prepare(self, *, issue: Issue, workspace: Path) -> None:
        """Optional pre-run setup (install deps, pull images, etc.)."""

    def collect_artifacts(self, workspace: Path) -> list[Path]:
        """Return paths to artifacts produced by this adapter."""
        return []

    def map_events(
        self,
        raw_events: list[dict[str, Any]],
    ) -> list[BuilderEvent]:
        """Map vendor-specific raw events to BuilderEvent.

        Adapters should override this to convert their native event
        format into the vendor-neutral model used by ComplianceEngine.
        Default returns an empty list.
        """
        return []


@runtime_checkable
class ReviewAdapter(Protocol):
    """Produces a ReviewSummary for a builder run.

    Implementations:
      - LocalReviewAdapter  — writes a JSON report to the workspace
      - LLMReviewAdapter    — uses an LLM to review the diff
    """

    ADAPTER_NAME: str

    def initialize(
        self,
        *,
        issue_id: str,
        workspace: Path,
        builder_turn_contract_compliance: dict[str, Any] | None = None,
    ) -> ReviewSummary: ...

    def review(
        self,
        *,
        issue_id: str,
        workspace: Path,
        verdict: str,
        reviewed_by: str,
        builder_turn_contract_compliance: dict[str, Any] | None = None,
    ) -> ReviewSummary: ...


@runtime_checkable
class IssueSource(Protocol):
    def load(self, issue_id: str) -> Issue: ...


@runtime_checkable
class PlannerAdapter(Protocol):
    """Drives the Spec stage: analyses an issue, generates questions, and drafts a spec.

    Implementations:
      - LiteLLMPlannerAdapter  — autonomous, calls an LLM
      - (none needed for coding-environment mode — the human drives via CLI)
    """

    ADAPTER_NAME: str

    def plan(
        self,
        *,
        issue: Issue,
        workspace: Path,
        existing_snapshot: SpecSnapshot | None = None,
        context: Any | None = None,
    ) -> PlannerResult:
        """Analyse the issue and return questions + optional spec draft."""
        ...

    def answer_questions(
        self,
        *,
        snapshot: SpecSnapshot,
        issue: Issue,
        context: Any | None = None,
    ) -> SpecSnapshot:
        """Use the LLM to autonomously answer unresolved blocking questions.

        Returns an updated snapshot with answers filled in and decisions recorded.
        Used in one-shot / daemon mode where no human is available.
        """
        ...


@runtime_checkable
class ScoperAdapter(Protocol):
    """Breaks a Mission into a wave-based ExecutionPlan (DAG of WorkPackets)."""

    ADAPTER_NAME: str

    def scope(
        self,
        *,
        mission: Mission,
        codebase_context: dict[str, Any],
        context: Any | None = None,
    ) -> ExecutionPlan:
        """Analyse the mission spec and produce a DAG of waves and work packets."""
        ...


@runtime_checkable
class PacketExecutor(Protocol):
    """Executes a single WorkPacket as an async subprocess."""

    async def execute_packet(
        self,
        packet: WorkPacket,
        wave_id: int,
        cancel_event: asyncio.Event,
    ) -> PacketResult: ...


@runtime_checkable
class WaveExecutor(Protocol):
    """Executes all packets in a wave with concurrency control."""

    async def execute_wave(
        self,
        wave: list[WorkPacket],
        wave_id: int,
        config: ParallelConfig,
        cancel_event: asyncio.Event,
    ) -> WaveResult: ...


@runtime_checkable
class WorkerHandle(Protocol):
    """Persistent or one-shot coding worker used by supervised mission rounds."""

    @property
    def session_id(self) -> str:
        """Unique identifier for this worker session."""
        ...

    def send(
        self,
        *,
        prompt: str,
        workspace: Path,
        event_logger: Callable[[dict[str, Any]], None] | None = None,
    ) -> BuilderResult:
        """Send work to this worker and return a standard BuilderResult."""
        ...

    def cancel(self, workspace: Path) -> None:
        """Cancel in-flight work for this session if supported."""
        ...

    def close(self, workspace: Path) -> None:
        """Release resources associated with this worker handle."""
        ...


@runtime_checkable
class SupervisorAdapter(Protocol):
    """Reviews one round of mission execution and decides the next action."""

    ADAPTER_NAME: str

    def review_round(
        self,
        *,
        round_artifacts: RoundArtifacts,
        plan: ExecutionPlan,
        round_history: list[RoundSummary],
        context: Any | None = None,
    ) -> RoundDecision:
        """Produce a structured round decision from current artifacts and history."""
        ...


@runtime_checkable
class WorkerHandleFactory(Protocol):
    """Creates and manages worker handles for a mission."""

    def create(
        self,
        *,
        session_id: str,
        workspace: Path,
    ) -> WorkerHandle:
        """Create or resume a worker session."""
        ...

    def get(self, session_id: str) -> WorkerHandle | None:
        """Return an existing handle if one is available."""
        ...

    def close_all(self, workspace: Path) -> None:
        """Close all active worker handles for this mission."""
        ...


@runtime_checkable
class VisualEvaluatorAdapter(Protocol):
    """Optional visual evaluator that inspects a round before supervisor review."""

    ADAPTER_NAME: str

    def evaluate_round(
        self,
        *,
        mission_id: str,
        round_id: int,
        wave: Wave,
        worker_results: list[tuple[WorkPacket, BuilderResult]],
        repo_root: Path,
        round_dir: Path,
    ) -> VisualEvaluationResult | None:
        """Return visual evaluation artifacts or None when evaluation is skipped."""
        ...


@runtime_checkable
class AcceptanceEvaluatorAdapter(Protocol):
    """Independent evaluator that judges round output using browser/runtime evidence."""

    ADAPTER_NAME: str

    def evaluate_acceptance(
        self,
        *,
        mission_id: str,
        round_id: int,
        round_dir: Path,
        worker_results: list[tuple[WorkPacket, BuilderResult]],
        artifacts: dict[str, Any],
        repo_root: Path,
        campaign: AcceptanceCampaign | None = None,
    ) -> AcceptanceReviewResult | None:
        """Return acceptance review artifacts or None when evaluation is skipped."""
        ...


@runtime_checkable
class LifecycleEvolver(Protocol):
    """Unified lifecycle for all evolution pipeline nodes.

    Supersedes the simpler ``services.evolver_protocol.Evolver`` with a
    structured four-phase lifecycle:
      observe  → collect evidence from recent runs
      propose  → generate change proposals from evidence
      validate → verify a proposal before applying
      promote  → apply a validated proposal
    """

    EVOLVER_NAME: str

    def observe(
        self,
        run_dirs: list[Path],
        *,
        context: Any | None = None,
    ) -> list[dict[str, Any]]:
        """Collect evidence from recent runs."""
        ...

    def propose(
        self,
        evidence: list[dict[str, Any]],
        *,
        context: Any | None = None,
    ) -> list[EvolutionProposal]:
        """Generate change proposals from evidence."""
        ...

    def validate(self, proposal: EvolutionProposal) -> EvolutionOutcome:
        """Validate a proposal before promoting."""
        ...

    def promote(self, proposal: EvolutionProposal) -> bool:
        """Apply a validated proposal."""
        ...


@runtime_checkable
class ConversationAdapter(Protocol):
    """Transport-agnostic conversation channel.

    Implementations:
      - SlackConversationAdapter  — Slack Bolt + Socket Mode
      - LinearConversationAdapter — polls Linear issue comments
      - CLIConversationAdapter    — stdin/stdout for local TUI
    """

    ADAPTER_NAME: str

    def listen(
        self,
        callback: Callable[[ConversationMessage], str | None],
    ) -> None:
        """Start listening for incoming messages. Calls *callback* on each.

        The callback returns an optional reply string; the adapter is
        responsible for sending it back through its channel.
        This method blocks until ``stop()`` is called.
        """
        ...

    def reply(self, thread_id: str, content: str) -> None:
        """Send a reply to a specific thread."""
        ...

    def stop(self) -> None:
        """Graceful shutdown."""
        ...
