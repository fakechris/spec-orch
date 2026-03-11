from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from spec_orch.domain.models import BuilderResult, Issue


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


@runtime_checkable
class IssueSource(Protocol):
    def load(self, issue_id: str) -> Issue: ...
