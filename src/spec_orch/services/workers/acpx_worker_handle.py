from __future__ import annotations

import json
import logging
import subprocess
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spec_orch.domain.compliance import default_turn_contract_compliance
from spec_orch.domain.models import BuilderResult
from spec_orch.runtime_chain.models import ChainPhase, RuntimeChainEvent, RuntimeSubjectKind
from spec_orch.runtime_chain.store import append_chain_event
from spec_orch.runtime_core.writers import write_worker_execution_payloads
from spec_orch.services.workers._acpx_utils import (
    build_acpx_command,
    build_acpx_env,
    cancel_acpx_session,
    drain_stderr,
    ensure_acpx_session,
)

_WORKER_PREAMBLE = (
    "You are the SpecOrch mission worker for this workspace. "
    "Continue implementation directly and keep file paths relative to cwd."
)

logger = logging.getLogger(__name__)


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
        startup_timeout_seconds: float = 30.0,
        idle_progress_timeout_seconds: float = 60.0,
        completion_quiet_period_seconds: float = 2.0,
        max_retries: int = 1,
        max_turns_per_session: int = 10,
        max_session_age_seconds: float = 1800.0,
    ) -> None:
        self._session_id = session_id
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
        self._session_ready = False
        self._session_generation = 0
        self._session_turns_completed = 0
        self._session_created_monotonic = time.monotonic()
        self._session_health = "healthy"

    @property
    def session_id(self) -> str:
        return self._active_session_name()

    def send(
        self,
        *,
        prompt: str,
        workspace: Path,
        event_logger: Callable[[dict[str, Any]], None] | None = None,
        chain_root: Path | None = None,
        chain_id: str | None = None,
        span_id: str | None = None,
        parent_span_id: str | None = None,
    ) -> BuilderResult:
        attempts = 0
        recycled = False
        last_result: BuilderResult | None = None
        while True:
            turn = self._run_turn_once(
                prompt=prompt,
                workspace=workspace,
                event_logger=event_logger,
                attempts=attempts,
                chain_root=chain_root,
                chain_id=chain_id,
                span_id=span_id,
                parent_span_id=parent_span_id,
            )
            last_result = turn
            terminal_reason = str(turn.metadata.get("terminal_reason", "")).strip()
            retryable = terminal_reason in {"startup_timeout", "reconnect_required"}
            had_progress = bool(turn.metadata.get("files_changed")) or bool(
                turn.metadata.get("commands_completed", 0)
            )
            if retryable and not had_progress and attempts < self.max_retries:
                attempts += 1
                recycled = True
                self._recycle_session(workspace)
                continue
            if recycled and last_result is not None:
                last_result.metadata["session_recycled"] = True
                report = json.loads(last_result.report_path.read_text(encoding="utf-8"))
                report["session_recycled"] = True
                last_result.report_path.write_text(
                    json.dumps(report, indent=2) + "\n",
                    encoding="utf-8",
                )
            return last_result

    def _run_turn_once(
        self,
        *,
        prompt: str,
        workspace: Path,
        event_logger: Callable[[dict[str, Any]], None] | None,
        attempts: int,
        chain_root: Path | None,
        chain_id: str | None,
        span_id: str | None,
        parent_span_id: str | None,
    ) -> BuilderResult:
        session_reused = self._session_turns_completed > 0
        self._ensure_session(workspace)

        full_prompt = f"{_WORKER_PREAMBLE}\n\n{prompt}"
        session_name = self._active_session_name()
        command = build_acpx_command(
            executable=self.executable,
            acpx_package=self.acpx_package,
            agent=self.agent,
            prompt=full_prompt,
            model=self.model,
            session_name=session_name,
            permissions=self.permissions,
        )
        report_path = workspace / "builder_report.json"
        telemetry_dir = workspace / "telemetry"
        telemetry_dir.mkdir(parents=True, exist_ok=True)
        incoming_path = telemetry_dir / "incoming_events.jsonl"
        worker_turn_path = telemetry_dir / "worker_turn.json"
        worker_health_path = telemetry_dir / "worker_health.json"
        raw_events: list[dict[str, Any]] = []
        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        state: dict[str, Any] = {
            "event_count": 0,
            "commands_completed": 0,
            "files_changed": [],
            "pending_tool_calls": set(),
            "saw_any_event": False,
            "saw_progress": False,
            "explicit_completion": False,
            "saw_failed_tool": False,
            "last_event_at": time.monotonic(),
            "last_progress_at": None,
        }
        if chain_root is not None and chain_id and span_id:
            append_chain_event(
                chain_root,
                RuntimeChainEvent(
                    chain_id=chain_id,
                    span_id=span_id,
                    parent_span_id=parent_span_id,
                    subject_kind=RuntimeSubjectKind.PACKET,
                    subject_id=self._session_id,
                    phase=ChainPhase.STARTED,
                    status_reason="worker_turn_started",
                    artifact_refs={"workspace": str(workspace)},
                    updated_at=datetime.now(UTC).isoformat(),
                ),
            )

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
                metadata={"terminal_reason": "process_spawn_failed"},
            )

        def _read_stdout() -> None:
            assert process.stdout is not None
            incoming_file = None
            try:
                incoming_file = incoming_path.open("a", encoding="utf-8")
            except OSError as exc:
                logger.warning("Failed to open incoming ACPX event log %s: %s", incoming_path, exc)

            try:
                for line in process.stdout:
                    stdout_lines.append(line)
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        event = json.loads(stripped)
                    except ValueError:
                        continue
                    if incoming_file is not None:
                        try:
                            incoming_file.write(line)
                            incoming_file.flush()
                        except OSError as exc:
                            logger.warning(
                                "Failed to write incoming ACPX event log %s: %s",
                                incoming_path,
                                exc,
                            )
                            incoming_file.close()
                            incoming_file = None
                    raw_events.append(event)
                    self._record_event_state(event, state)
                    if event_logger is not None:
                        event_logger(event)
            finally:
                if incoming_file is not None:
                    incoming_file.close()

        stdout_thread = threading.Thread(target=_read_stdout, daemon=True)
        stderr_thread = threading.Thread(
            target=drain_stderr,
            args=(process, stderr_lines),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

        terminal_reason = ""
        succeeded = False
        exit_code: int | None = None
        start = time.monotonic()
        while True:
            now = time.monotonic()
            polled = process.poll()
            stderr_text = "".join(stderr_lines)

            if polled is not None:
                exit_code = polled
                if polled == 0:
                    terminal_reason = "process_exit_success"
                    succeeded = True
                else:
                    terminal_reason = (
                        "reconnect_required"
                        if "agent needs reconnect" in stderr_text.lower()
                        else "process_exit_failure"
                    )
                    succeeded = False
                break

            if (
                state["explicit_completion"]
                and not state["pending_tool_calls"]
                and now - float(state["last_event_at"]) >= self.completion_quiet_period_seconds
            ):
                process.terminate()
                process.wait()
                exit_code = process.returncode
                terminal_reason = "event_completed"
                succeeded = True
                break

            if (
                state["saw_failed_tool"]
                and not state["saw_progress"]
                and not state["pending_tool_calls"]
                and now - float(state["last_event_at"]) >= self.completion_quiet_period_seconds
            ):
                process.terminate()
                process.wait()
                exit_code = process.returncode
                terminal_reason = "fatal_tool_failure"
                succeeded = False
                break

            if (
                not state["saw_progress"]
                and "agent needs reconnect" in stderr_text.lower()
                and now - start >= self.startup_timeout_seconds
            ):
                process.terminate()
                process.wait()
                exit_code = process.returncode
                terminal_reason = "reconnect_required"
                succeeded = False
                break

            if not state["saw_any_event"] and now - start >= self.startup_timeout_seconds:
                process.terminate()
                process.wait()
                exit_code = process.returncode
                terminal_reason = "startup_timeout"
                succeeded = False
                break

            if (
                state["saw_progress"]
                and state["last_progress_at"] is not None
                and now - float(state["last_progress_at"]) >= self.idle_progress_timeout_seconds
            ):
                process.terminate()
                process.wait()
                exit_code = process.returncode
                terminal_reason = "idle_timeout"
                succeeded = False
                break

            if now - start >= self.absolute_timeout_seconds:
                process.kill()
                process.wait()
                exit_code = process.returncode
                terminal_reason = "absolute_timeout"
                succeeded = False
                break

            time.sleep(0.01)

        stdout_thread.join(timeout=5)
        stderr_thread.join(timeout=5)

        if terminal_reason not in {"process_exit_success", "event_completed"}:
            self._session_health = "degraded"
            try:
                cancel_acpx_session(
                    workspace=workspace,
                    executable=self.executable,
                    acpx_package=self.acpx_package,
                    agent=self.agent,
                    session_name=session_name,
                )
            except RuntimeError as exc:
                logger.warning("ACPX worker cleanup degraded gracefully: %s", exc)
            self._session_ready = False
        else:
            self._session_health = "healthy"
            self._session_turns_completed += 1

        report_payload = {
            "adapter": "acpx_worker",
            "agent": self.agent,
            "model": self.model,
            "succeeded": succeeded,
            "exit_code": exit_code,
            "event_count": state["event_count"],
            "session_name": session_name,
            "terminal_reason": terminal_reason,
            "commands_completed": state["commands_completed"],
            "files_changed": list(state["files_changed"]),
            "retry_count": attempts,
            "session_reused": session_reused,
            "session_recycled": False,
            "session_health": self._session_health,
            "chain_id": chain_id,
            "span_id": span_id,
            "parent_span_id": parent_span_id,
        }
        write_worker_execution_payloads(
            workspace,
            builder_report=report_payload,
        )
        worker_turn_path.write_text(
            json.dumps(
                {
                    "session_name": session_name,
                    "terminal_reason": terminal_reason,
                    "succeeded": succeeded,
                    "retry_count": attempts,
                    "event_count": state["event_count"],
                    "commands_completed": state["commands_completed"],
                    "files_changed": list(state["files_changed"]),
                    "session_reused": session_reused,
                    "session_health": self._session_health,
                    "chain_id": chain_id,
                    "span_id": span_id,
                    "parent_span_id": parent_span_id,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        if chain_root is not None and chain_id and span_id:
            append_chain_event(
                chain_root,
                RuntimeChainEvent(
                    chain_id=chain_id,
                    span_id=span_id,
                    parent_span_id=parent_span_id,
                    subject_kind=RuntimeSubjectKind.PACKET,
                    subject_id=self._session_id,
                    phase=ChainPhase.COMPLETED if succeeded else ChainPhase.DEGRADED,
                    status_reason=terminal_reason,
                    artifact_refs={"builder_report": str(report_path)},
                    updated_at=datetime.now(UTC).isoformat(),
                ),
            )
        worker_health_path.write_text(
            json.dumps(
                {
                    "session_name": session_name,
                    "session_generation": self._session_generation,
                    "turns_completed": self._session_turns_completed,
                    "session_health": self._session_health,
                    "last_successful_progress_at": state["last_progress_at"],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return BuilderResult(
            succeeded=succeeded,
            command=command,
            stdout="".join(stdout_lines),
            stderr="".join(stderr_lines),
            report_path=report_path,
            adapter="acpx_worker",
            agent=self.agent,
            metadata={
                "turn_contract_compliance": default_turn_contract_compliance(),
                **report_payload,
            },
        )

    def _record_event_state(self, event: dict[str, Any], state: dict[str, Any]) -> None:
        now = time.monotonic()
        state["event_count"] += 1
        state["saw_any_event"] = True
        state["last_event_at"] = now

        event_type = str(event.get("type", "")).strip().lower()
        if event_type == "result":
            state["explicit_completion"] = True
            state["saw_progress"] = True
            state["last_progress_at"] = now
            return

        if str(event.get("method", "")).strip() != "session/update":
            return

        update = event.get("params", {}).get("update", {})
        session_update = str(update.get("sessionUpdate", "")).strip()
        tool_call_id = str(update.get("toolCallId", "")).strip()
        status = str(update.get("status", "")).strip().lower()
        title = str(update.get("title", "")).strip().lower()

        if session_update == "tool_call" and tool_call_id:
            state["pending_tool_calls"].add(tool_call_id)
            return

        if session_update == "tool_call_update":
            if tool_call_id and status in {"completed", "failed", "cancelled"}:
                state["pending_tool_calls"].discard(tool_call_id)
            if status == "completed":
                raw_input = update.get("rawInput", {})
                if title in {"bash"} or title.startswith("verify"):
                    state["commands_completed"] += 1
                    state["saw_progress"] = True
                    state["last_progress_at"] = now
                file_path = ""
                if isinstance(raw_input, dict):
                    file_path = str(
                        raw_input.get("filePath")
                        or raw_input.get("file_path")
                        or raw_input.get("path")
                        or ""
                    ).strip()
                if title in {"write", "edit"} or file_path:
                    if file_path and file_path not in state["files_changed"]:
                        state["files_changed"].append(file_path)
                    state["saw_progress"] = True
                    state["last_progress_at"] = now
            elif status == "failed":
                state["saw_failed_tool"] = True
            return

        if session_update in {"agent_turn_end", "agent_message_end", "turn_completed"}:
            state["explicit_completion"] = True

    def _active_session_name(self) -> str:
        if self._session_generation == 0:
            return self._session_id
        return f"{self._session_id}-retry-{self._session_generation}"

    def _ensure_session(self, workspace: Path) -> None:
        now = time.monotonic()
        if self._session_ready and (
            self._session_turns_completed >= self.max_turns_per_session
            or (now - self._session_created_monotonic) >= self.max_session_age_seconds
            or self._session_health != "healthy"
        ):
            self._recycle_session(workspace)
        if self._session_ready:
            return
        try:
            ensure_acpx_session(
                workspace=workspace,
                executable=self.executable,
                acpx_package=self.acpx_package,
                agent=self.agent,
                session_name=self._active_session_name(),
            )
        except RuntimeError as exc:
            raise RuntimeError(
                f"ACPX session ensure failed for {self._active_session_name()}: {exc}"
            ) from exc
        self._session_ready = True
        self._session_health = "healthy"
        self._session_created_monotonic = now

    def _recycle_session(self, workspace: Path) -> None:
        if self._session_ready:
            try:
                cancel_acpx_session(
                    workspace=workspace,
                    executable=self.executable,
                    acpx_package=self.acpx_package,
                    agent=self.agent,
                    session_name=self._active_session_name(),
                )
            except RuntimeError as exc:
                logger.warning("ACPX worker recycle degraded gracefully: %s", exc)
        self._session_generation += 1
        self._session_turns_completed = 0
        self._session_ready = False
        self._session_health = "closed"
        self._session_created_monotonic = time.monotonic()

    def cancel(self, workspace: Path) -> None:
        try:
            cancel_acpx_session(
                workspace=workspace,
                executable=self.executable,
                acpx_package=self.acpx_package,
                agent=self.agent,
                session_name=self._session_id,
            )
        except RuntimeError as exc:
            logger.warning("ACPX worker cancel degraded gracefully: %s", exc)
        finally:
            self._session_ready = False

    def close(self, workspace: Path) -> None:
        self._session_ready = False
        return None
