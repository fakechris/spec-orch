from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from spec_orch.domain.models import BuilderResult, Issue
from spec_orch.domain.protocols import BuilderAdapter


class OneShotWorkerHandle:
    """WorkerHandle backed by a normal one-shot BuilderAdapter invocation."""

    def __init__(self, *, session_id: str, builder_adapter: BuilderAdapter) -> None:
        self._session_id = session_id
        self._builder_adapter = builder_adapter
        self._closed = False

    @property
    def session_id(self) -> str:
        return self._session_id

    def send(
        self,
        *,
        prompt: str,
        workspace: Path,
        event_logger: Callable[[dict[str, Any]], None] | None = None,
    ) -> BuilderResult:
        issue = Issue(
            issue_id=self._session_id,
            title=f"Worker {self._session_id}",
            summary=prompt,
            builder_prompt=prompt,
        )
        prepare = getattr(self._builder_adapter, "prepare", None)
        if callable(prepare):
            prepare(issue=issue, workspace=workspace)
        return self._builder_adapter.run(
            issue=issue,
            workspace=workspace,
            event_logger=event_logger,
        )

    def cancel(self, workspace: Path) -> None:
        return None

    def close(self, workspace: Path) -> None:
        self._closed = True
