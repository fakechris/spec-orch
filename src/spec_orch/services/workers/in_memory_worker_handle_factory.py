from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from spec_orch.domain.protocols import WorkerHandle


class InMemoryWorkerHandleFactory:
    """Simple mission-local WorkerHandleFactory backed by an in-memory dict."""

    def __init__(
        self,
        *,
        creator: Callable[[str, Path], WorkerHandle],
    ) -> None:
        self._creator = creator
        self._handles: dict[str, WorkerHandle] = {}

    def create(
        self,
        *,
        session_id: str,
        workspace: Path,
    ) -> WorkerHandle:
        handle = self._handles.get(session_id)
        if handle is None:
            handle = self._creator(session_id, workspace)
            self._handles[session_id] = handle
        return handle

    def get(self, session_id: str) -> WorkerHandle | None:
        return self._handles.get(session_id)

    def close_all(self, workspace: Path) -> None:
        for handle in list(self._handles.values()):
            handle.close(workspace)
        self._handles.clear()
