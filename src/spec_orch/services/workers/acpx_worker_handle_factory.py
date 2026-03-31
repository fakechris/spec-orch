from __future__ import annotations

from pathlib import Path

from spec_orch.domain.protocols import WorkerHandle
from spec_orch.services.workers.acpx_worker_handle import AcpxWorkerHandle


class AcpxWorkerHandleFactory:
    """Mission-local factory for ACPX-backed persistent worker sessions."""

    def __init__(
        self,
        *,
        agent: str = "opencode",
        model: str | None = None,
        permissions: str = "full-auto",
        executable: str = "npx",
        acpx_package: str = "acpx",
        absolute_timeout_seconds: float = 1800.0,
        startup_timeout_seconds: float = 30.0,
        idle_progress_timeout_seconds: float = 60.0,
        completion_quiet_period_seconds: float = 2.0,
        max_retries: int = 1,
        max_turns_per_session: int = 10,
        max_session_age_seconds: float = 1800.0,
    ) -> None:
        self.agent = agent
        self.model = model
        self.permissions = permissions
        self.executable = executable
        self.acpx_package = acpx_package
        self.absolute_timeout_seconds = absolute_timeout_seconds
        self.startup_timeout_seconds = startup_timeout_seconds
        self.idle_progress_timeout_seconds = idle_progress_timeout_seconds
        self.completion_quiet_period_seconds = completion_quiet_period_seconds
        self.max_retries = max_retries
        self.max_turns_per_session = max_turns_per_session
        self.max_session_age_seconds = max_session_age_seconds
        self._handles: dict[str, AcpxWorkerHandle] = {}

    def create(
        self,
        *,
        session_id: str,
        workspace: Path,
    ) -> WorkerHandle:
        handle = self._handles.get(session_id)
        if handle is None:
            handle = AcpxWorkerHandle(
                session_id=session_id,
                agent=self.agent,
                model=self.model,
                permissions=self.permissions,
                executable=self.executable,
                acpx_package=self.acpx_package,
                absolute_timeout_seconds=self.absolute_timeout_seconds,
                startup_timeout_seconds=self.startup_timeout_seconds,
                idle_progress_timeout_seconds=self.idle_progress_timeout_seconds,
                completion_quiet_period_seconds=self.completion_quiet_period_seconds,
                max_retries=self.max_retries,
                max_turns_per_session=self.max_turns_per_session,
                max_session_age_seconds=self.max_session_age_seconds,
            )
            self._handles[session_id] = handle
        return handle

    def get(self, session_id: str) -> WorkerHandle | None:
        return self._handles.get(session_id)

    def close_all(self, workspace: Path) -> None:
        errors: list[Exception] = []
        for handle in list(self._handles.values()):
            try:
                handle.close(workspace)
            except Exception as exc:
                errors.append(exc)
        self._handles.clear()
        if errors:
            raise RuntimeError(
                f"Failed to close {len(errors)} ACPX worker handle(s): {errors[0]}"
            ) from errors[0]
