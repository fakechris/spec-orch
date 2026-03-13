from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from spec_orch.domain.models import (
    BuilderEvent,
    BuilderResult,
    ConversationMessage,
    ExecutionPlan,
    Issue,
    Mission,
    PacketResult,
    ParallelConfig,
    PlannerResult,
    SpecSnapshot,
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
    ) -> PlannerResult:
        """Analyse the issue and return questions + optional spec draft."""
        ...

    def answer_questions(
        self,
        *,
        snapshot: SpecSnapshot,
        issue: Issue,
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
