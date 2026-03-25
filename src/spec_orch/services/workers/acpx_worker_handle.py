from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from spec_orch.domain.compliance import default_turn_contract_compliance
from spec_orch.domain.models import BuilderResult
from spec_orch.services.io import atomic_write_json
from spec_orch.services.workers._acpx_utils import (
    build_acpx_command,
    build_acpx_env,
    cancel_acpx_session,
    collect_stdout_events,
    drain_stderr,
    ensure_acpx_session,
)

_WORKER_PREAMBLE = (
    "You are the SpecOrch mission worker for this workspace. "
    "Continue implementation directly and keep file paths relative to cwd."
)


class AcpxWorkerHandle:
    """WorkerHandle backed by a persistent ACPX session."""

    def __init__(
        self,
        *,
        session_id: str,
        agent: str = "opencode",
        model: str | None = None,
        permissions: str = "full-auto",
        executable: str = "npx",
        acpx_package: str = "acpx",
        absolute_timeout_seconds: float = 1800.0,
    ) -> None:
        self._session_id = session_id
        self.agent = agent
        self.model = model
        self.permissions = permissions
        self.executable = executable
        self.acpx_package = acpx_package
        self.absolute_timeout_seconds = absolute_timeout_seconds
        self._session_ready = False

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
        if not self._session_ready:
            ensure_acpx_session(
                workspace=workspace,
                executable=self.executable,
                acpx_package=self.acpx_package,
                agent=self.agent,
                session_name=self._session_id,
            )
            self._session_ready = True

        full_prompt = f"{_WORKER_PREAMBLE}\n\n{prompt}"
        command = build_acpx_command(
            executable=self.executable,
            acpx_package=self.acpx_package,
            agent=self.agent,
            prompt=full_prompt,
            model=self.model,
            session_name=self._session_id,
            permissions=self.permissions,
        )
        report_path = workspace / "builder_report.json"
        raw_events: list[dict[str, Any]] = []
        stdout_lines: list[str] = []
        stderr_lines: list[str] = []

        try:
            process = subprocess.Popen(
                command,
                cwd=workspace,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=build_acpx_env(),
            )
        except FileNotFoundError:
            return BuilderResult(
                succeeded=False,
                command=command,
                stdout="",
                stderr=f"ACPX executable not found: {self.executable}",
                report_path=report_path,
                adapter="acpx_worker",
                agent=self.agent,
            )

        stdout_thread = threading.Thread(
            target=collect_stdout_events,
            kwargs={
                "process": process,
                "stdout_lines": stdout_lines,
                "raw_events": raw_events,
                "event_logger": event_logger,
            },
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=drain_stderr,
            args=(process, stderr_lines),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

        timed_out = False
        try:
            process.wait(timeout=self.absolute_timeout_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            timed_out = True

        stdout_thread.join(timeout=5)
        stderr_thread.join(timeout=5)

        if timed_out:
            return BuilderResult(
                succeeded=False,
                command=command,
                stdout="".join(stdout_lines),
                stderr=f"Timeout after {self.absolute_timeout_seconds}s",
                report_path=report_path,
                adapter="acpx_worker",
                agent=self.agent,
            )

        succeeded = process.returncode == 0
        atomic_write_json(
            report_path,
            {
                "adapter": "acpx_worker",
                "agent": self.agent,
                "model": self.model,
                "succeeded": succeeded,
                "exit_code": process.returncode,
                "event_count": len(raw_events),
                "session_name": self._session_id,
            },
        )
        return BuilderResult(
            succeeded=succeeded,
            command=command,
            stdout="".join(stdout_lines),
            stderr="".join(stderr_lines),
            report_path=report_path,
            adapter="acpx_worker",
            agent=self.agent,
            metadata={"turn_contract_compliance": default_turn_contract_compliance()},
        )

    def cancel(self, workspace: Path) -> None:
        cancel_acpx_session(
            workspace=workspace,
            executable=self.executable,
            acpx_package=self.acpx_package,
            agent=self.agent,
            session_name=self._session_id,
        )

    def close(self, workspace: Path) -> None:
        return None
