from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from spec_orch.domain.models import BuilderEvent, BuilderResult, Issue


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
        self, raw_events: list[dict[str, Any]],
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
