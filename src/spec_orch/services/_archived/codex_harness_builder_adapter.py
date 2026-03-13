from __future__ import annotations

import json
import os
import select
import subprocess
import tempfile
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spec_orch.domain.compliance import (
    default_turn_contract_compliance,
    evaluate_pre_action_narration_compliance,
)
from spec_orch.domain.models import BuilderResult, Issue


class CodexHarnessTransportError(RuntimeError):
    """Raised when the Codex app-server transport cannot be used."""

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class CodexHarnessBuilderAdapter:
    ADAPTER_NAME = "codex_harness"
    AGENT_NAME = "codex"
    PREAMBLE = (
        "## FORBIDDEN BEFORE FIRST ACTION\n"
        "- No plan narration\n"
        "- No skill/process references\n"
        '- No "I will now..." sentences\n'
        "Any output before exec_command_begin is non-compliant.\n\n"
        "## FIRST ACTION REQUIREMENT\n"
        "Your first output token must begin a concrete action:\n"
        "a shell command, a file edit, or a test run.\n\n"
        "## ALLOWED NARRATION (only after first action)\n"
        "One sentence max. Impact-focused. No headings.\n\n"
        "CRITICAL INSTRUCTIONS - FOLLOW EXACTLY:\n"
        "- DO NOT describe what you are about to do\n"
        "- DO NOT explain your plan or approach before acting\n"
        '- DO NOT narrate steps like "First I will read the repo, then I will..."\n'
        "- DO NOT reference skill docs or planning process\n"
        "- START with the first concrete action: a command, a code edit, or a test run\n"
        "- If you must explain, do it AFTER the action, in one sentence max\n\n"
        "You are the SpecOrch builder for this issue workspace. "
        "Minimize workflow narration, tool-loading commentary, and process summaries. "
        "Move directly into implementation and verification. "
        "Only stop to explain when blocked, when requesting approval, or when reporting the final outcome."
    )

    def __init__(
        self,
        *,
        executable: str = "codex",
        command: Sequence[str] | None = None,
        request_timeout_seconds: float = 30.0,
        idle_timeout_seconds: float = 30.0,
        stalled_timeout_seconds: float = 300.0,
        absolute_timeout_seconds: float = 1800.0,
    ) -> None:
        self.executable = executable
        self.command = (
            list(command)
            if command is not None
            else [
                executable,
                "app-server",
                "--listen",
                "stdio://",
            ]
        )
        self.request_timeout_seconds = request_timeout_seconds
        self.idle_timeout_seconds = idle_timeout_seconds
        self.stalled_timeout_seconds = stalled_timeout_seconds
        self.absolute_timeout_seconds = absolute_timeout_seconds

    def run(
        self,
        *,
        issue: Issue,
        workspace: Path,
        run_id: str | None = None,
        event_logger: Callable[[dict[str, Any]], None] | None = None,
    ) -> BuilderResult:
        report_path = workspace / "builder_report.json"
        telemetry_dir = workspace / "telemetry"
        telemetry_dir.mkdir(parents=True, exist_ok=True)
        if not issue.builder_prompt:
            result = BuilderResult(
                succeeded=True,
                command=self.command,
                stdout="",
                stderr="",
                report_path=report_path,
                skipped=True,
                adapter=self.ADAPTER_NAME,
                agent=self.AGENT_NAME,
                metadata={
                    "transport": "app_server_stdio",
                    "turn_contract_compliance": default_turn_contract_compliance(),
                },
            )
            self._write_report(result)
            return result

        try:
            with _CodexHarnessSession(
                command=self.command,
                cwd=workspace,
                env=self._build_env(issue),
                request_timeout_seconds=self.request_timeout_seconds,
                idle_timeout_seconds=self.idle_timeout_seconds,
                stalled_timeout_seconds=self.stalled_timeout_seconds,
                absolute_timeout_seconds=self.absolute_timeout_seconds,
                raw_in_path=telemetry_dir / "raw_harness_in.jsonl",
                raw_out_path=telemetry_dir / "raw_harness_out.jsonl",
                raw_err_path=telemetry_dir / "raw_harness_err.log",
                incoming_events_path=telemetry_dir / "incoming_events.jsonl",
                state_path=telemetry_dir / "harness_state.json",
                run_id=run_id,
                event_logger=event_logger,
            ) as session:
                session.initialize()
                thread_id = session.start_thread(cwd=workspace)
                turn_id = session.start_turn(
                    thread_id=thread_id,
                    turn_input=self._build_turn_input(issue.builder_prompt),
                )
                completed = session.wait_for_turn_completion(
                    thread_id=thread_id,
                    turn_id=turn_id,
                )
        except FileNotFoundError as exc:
            raise CodexHarnessTransportError(str(exc)) from exc
        except (BrokenPipeError, TimeoutError, json.JSONDecodeError, KeyError) as exc:
            raise CodexHarnessTransportError(str(exc)) from exc

        result = BuilderResult(
            succeeded=completed["status"] == "completed",
            command=self.command,
            stdout=completed["final_message"],
            stderr=completed["stderr"],
            report_path=report_path,
            adapter=self.ADAPTER_NAME,
            agent=self.AGENT_NAME,
            metadata={
                "transport": "app_server_stdio",
                "run_id": run_id,
                "thread_id": thread_id,
                "turn_id": turn_id,
                "plan": completed["plan"],
                "event_count": completed["event_count"],
                "observation": completed["observation"],
                "turn_contract_compliance": evaluate_pre_action_narration_compliance(
                    telemetry_dir / "incoming_events.jsonl"
                ),
            },
        )
        self._write_report(result)
        return result

    def _build_env(self, issue: Issue) -> dict[str, str]:
        env = dict(os.environ)
        env.update(
            {
                "SPEC_ORCH_BUILDER_ADAPTER": self.ADAPTER_NAME,
                "SPEC_ORCH_BUILDER_AGENT": self.AGENT_NAME,
                "SPEC_ORCH_ISSUE_ID": issue.issue_id,
            }
        )
        return env

    def _write_report(self, result: BuilderResult) -> None:
        result.report_path.write_text(
            json.dumps(
                {
                    "succeeded": result.succeeded,
                    "skipped": result.skipped,
                    "command": result.command,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "adapter": result.adapter,
                    "agent": result.agent,
                    "metadata": result.metadata,
                },
                indent=2,
            )
            + "\n"
        )

    def _build_turn_input(self, prompt: str) -> list[dict[str, str]]:
        return [
            {
                "type": "text",
                "text": f"{self.PREAMBLE}\n\nIssue builder prompt:\n{prompt}",
            }
        ]


class _CodexHarnessSession:
    def __init__(
        self,
        *,
        command: list[str],
        cwd: Path,
        env: dict[str, str],
        request_timeout_seconds: float,
        idle_timeout_seconds: float,
        stalled_timeout_seconds: float,
        absolute_timeout_seconds: float,
        raw_in_path: Path | None = None,
        raw_out_path: Path | None = None,
        raw_err_path: Path | None = None,
        incoming_events_path: Path | None = None,
        state_path: Path | None = None,
        run_id: str | None = None,
        event_logger: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.command = command
        self.cwd = cwd
        self.env = env
        self.request_timeout_seconds = request_timeout_seconds
        self.idle_timeout_seconds = idle_timeout_seconds
        self.stalled_timeout_seconds = stalled_timeout_seconds
        self.absolute_timeout_seconds = absolute_timeout_seconds
        self.raw_in_path = raw_in_path
        self.raw_out_path = raw_out_path
        self.raw_err_path = raw_err_path
        self.incoming_events_path = incoming_events_path
        self.state_path = state_path
        self.run_id = run_id
        self.event_logger = event_logger
        self._next_id = 1
        self.process: subprocess.Popen[str] | None = None
        self._stderr_file: tempfile.TemporaryFile[str] | None = None
        self._thread_id: str | None = None
        self._turn_id: str | None = None
        self._turn_status: str = "not_started"
        self._started_monotonic: float | None = None
        self._started_at: str | None = None
        self._last_protocol_monotonic: float | None = None
        self._last_protocol_at: str | None = None
        self._last_protocol_kind: str | None = None
        self._last_output_monotonic: float | None = None
        self._last_output_at: str | None = None
        self._last_output_kind: str | None = None
        self._last_output_excerpt: str | None = None
        self._last_agent_excerpt: str | None = None
        self._last_command_output_excerpt: str | None = None
        self._last_progress_monotonic: float | None = None
        self._last_progress_at: str | None = None
        self._last_progress_kind: str | None = None
        self._last_progress_excerpt: str | None = None
        self._last_protocol_excerpt: str | None = None
        self._timeout_reason: str | None = None
        self._stdout_buffer = b""
        self._agent_message_fragments: dict[str, str] = {}

    def __enter__(self) -> _CodexHarnessSession:
        if self.raw_err_path is not None:
            self.raw_err_path.parent.mkdir(parents=True, exist_ok=True)
            self._stderr_file = self.raw_err_path.open(mode="w+", encoding="utf-8")
        else:
            self._stderr_file = tempfile.TemporaryFile(mode="w+")
        self.process = subprocess.Popen(
            self.command,
            cwd=self.cwd,
            env=self.env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._stderr_file,
        )
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        if self._stderr_file is not None:
            self._stderr_file.close()

    def initialize(self) -> None:
        self._request(
            "initialize",
            {
                "clientInfo": {"name": "spec-orch", "version": "0.1.0"},
                "capabilities": {"experimentalApi": True},
            },
        )

    def start_thread(self, *, cwd: Path) -> str:
        response = self._request(
            "thread/start",
            {
                "cwd": str(cwd),
                "approvalPolicy": "on-request",
                "sandbox": "workspace-write",
                "personality": "pragmatic",
                "serviceName": "spec-orch-builder",
            },
        )
        thread_id = response["thread"]["id"]
        self._thread_id = thread_id
        self._emit_event(
            event_type="thread_started",
            message="Started Codex thread.",
            data={"thread_id": thread_id},
        )
        return thread_id

    def start_turn(self, *, thread_id: str, turn_input: list[dict[str, str]]) -> str:
        response = self._request(
            "turn/start",
            {
                "threadId": thread_id,
                "input": turn_input,
            },
        )
        turn_id = response["turn"]["id"]
        self._begin_turn_observation(thread_id=thread_id, turn_id=turn_id)
        self._emit_event(
            event_type="turn_started",
            message="Started Codex turn.",
            data={"thread_id": thread_id, "turn_id": turn_id},
        )
        return turn_id

    def wait_for_turn_completion(self, *, thread_id: str, turn_id: str) -> dict[str, Any]:
        final_message_parts: list[str] = []
        plan_items: list[str] = []
        event_count = 0

        while True:
            message = self._read_turn_message()
            if "method" in message and "id" in message:
                self._handle_server_request(message)
                continue
            if "method" not in message:
                continue
            event_count += 1
            self._record_activity(message)
            if message["method"] == "item/agentMessage/delta":
                params = message["params"]
                if params["threadId"] == thread_id and params["turnId"] == turn_id:
                    final_message_parts.append(params["delta"])
            elif message["method"] == "turn/plan/updated":
                params = message["params"]
                if params["threadId"] == thread_id and params["turnId"] == turn_id:
                    plan_items = [
                        item.get("text", "") for item in params.get("items", []) if item.get("text")
                    ]
            elif message["method"] == "turn/completed":
                params = message["params"]
                if params["threadId"] == thread_id and params["turn"]["id"] == turn_id:
                    event_type = (
                        "turn_completed"
                        if params["turn"]["status"] == "completed"
                        else "turn_failed"
                    )
                    self._emit_event(
                        event_type=event_type,
                        severity="info" if event_type == "turn_completed" else "error",
                        message="Codex turn finished.",
                        data={
                            "thread_id": thread_id,
                            "turn_id": turn_id,
                            "status": params["turn"]["status"],
                        },
                    )
                    self._turn_status = params["turn"]["status"]
                    self._write_state()
                    return {
                        "status": params["turn"]["status"],
                        "final_message": "".join(final_message_parts),
                        "plan": plan_items,
                        "event_count": event_count,
                        "stderr": self._drain_stderr(),
                        "observation": self._observation_snapshot(),
                    }

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        self._write_message(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }
        )

        deadline = time.monotonic() + self.request_timeout_seconds
        while time.monotonic() < deadline:
            message = self._read_message(deadline=deadline)
            if "method" in message and "id" in message:
                self._handle_server_request(message)
                continue
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise CodexHarnessTransportError(json.dumps(message["error"]))
            return message["result"]

        raise CodexHarnessTransportError(
            f"timed out waiting for response to {method}",
            details={"request_method": method},
        )

    def _write_message(self, payload: dict[str, Any]) -> None:
        if self.process is None or self.process.stdin is None:
            raise CodexHarnessTransportError("Codex app-server stdin is not available")
        serialized = json.dumps(payload)
        if self.raw_in_path is not None:
            with self.raw_in_path.open("a", encoding="utf-8") as handle:
                handle.write(serialized + "\n")
        self.process.stdin.write((serialized + "\n").encode("utf-8"))
        self.process.stdin.flush()

    def _read_message(self, *, deadline: float) -> dict[str, Any]:
        if self.process is None:
            raise CodexHarnessTransportError("Codex app-server stdout is not available")
        while True:
            buffered = self._read_buffered_line()
            if buffered is not None:
                message = json.loads(buffered)
                self._record_incoming_message(message)
                return message
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CodexHarnessTransportError("timed out waiting for Codex app-server output")
            ready, _, _ = select.select([self.process.stdout], [], [], remaining)
            if not ready:
                self._check_process_exit()
                raise CodexHarnessTransportError("timed out waiting for Codex app-server output")
            self._fill_stdout_buffer()

    def _read_turn_message(self) -> dict[str, Any]:
        if self.process is None:
            raise CodexHarnessTransportError("Codex app-server stdout is not available")

        while True:
            buffered = self._read_buffered_line()
            if buffered is not None:
                message = json.loads(buffered)
                self._record_incoming_message(message)
                return message
            timeout = self._next_wait_timeout()
            ready, _, _ = select.select([self.process.stdout], [], [], min(timeout, 0.25))
            if ready:
                self._fill_stdout_buffer()
                continue
            self._check_turn_timeout()
            self._check_process_exit()

    def _fill_stdout_buffer(self) -> None:
        if self.process is None or self.process.stdout is None:
            raise CodexHarnessTransportError("Codex app-server stdout is not available")
        chunk = os.read(self.process.stdout.fileno(), 4096)
        if chunk == b"":
            stderr = self._drain_stderr()
            raise CodexHarnessTransportError(
                f"Codex app-server closed the stdio stream unexpectedly. stderr={stderr}"
            )
        self._stdout_buffer += chunk

    def _read_buffered_line(self) -> str | None:
        newline_index = self._stdout_buffer.find(b"\n")
        if newline_index == -1:
            return None
        line = self._stdout_buffer[: newline_index + 1]
        self._stdout_buffer = self._stdout_buffer[newline_index + 1 :]
        decoded = line.decode("utf-8")
        if self.raw_out_path is not None:
            with self.raw_out_path.open("a", encoding="utf-8") as handle:
                handle.write(decoded)
        return decoded

    def _handle_server_request(self, message: dict[str, Any]) -> None:
        method = message["method"]
        request_id = message["id"]
        params = message.get("params", {})

        if method == "item/commandExecution/requestApproval":
            self._mark_progress("approval_requested")
            self._emit_event(
                event_type="approval_requested",
                message="Command execution requested approval.",
                data={
                    "thread_id": params.get("threadId"),
                    "turn_id": params.get("turnId"),
                    "item_id": params.get("itemId"),
                    "approval_type": "command",
                },
            )
            self._write_message(
                {"jsonrpc": "2.0", "id": request_id, "result": {"decision": "accept"}}
            )
            self._emit_event(
                event_type="approval_resolved",
                message="Command execution approval accepted.",
                data={
                    "thread_id": params.get("threadId"),
                    "turn_id": params.get("turnId"),
                    "item_id": params.get("itemId"),
                    "approval_type": "command",
                    "decision": "accept",
                },
            )
            self._mark_progress("approval_resolved")
            return

        if method == "item/fileChange/requestApproval":
            self._mark_progress("approval_requested")
            self._emit_event(
                event_type="approval_requested",
                message="File change requested approval.",
                data={
                    "thread_id": params.get("threadId"),
                    "turn_id": params.get("turnId"),
                    "item_id": params.get("itemId"),
                    "approval_type": "file_change",
                },
            )
            self._write_message(
                {"jsonrpc": "2.0", "id": request_id, "result": {"decision": "accept"}}
            )
            self._emit_event(
                event_type="approval_resolved",
                message="File change approval accepted.",
                data={
                    "thread_id": params.get("threadId"),
                    "turn_id": params.get("turnId"),
                    "item_id": params.get("itemId"),
                    "approval_type": "file_change",
                    "decision": "accept",
                },
            )
            self._mark_progress("approval_resolved")
            return

        raise CodexHarnessTransportError(f"unexpected server request: {method}")

    def _emit_event(
        self,
        *,
        event_type: str,
        message: str,
        data: dict[str, Any],
        severity: str = "info",
    ) -> None:
        if self.event_logger is None:
            return
        payload = {
            "event_type": event_type,
            "message": message,
            "severity": severity,
            "run_id": self.run_id,
            "component": "builder",
            "adapter": CodexHarnessBuilderAdapter.ADAPTER_NAME,
            "agent": CodexHarnessBuilderAdapter.AGENT_NAME,
            "data": data,
        }
        self.event_logger(payload)

    def _begin_turn_observation(self, *, thread_id: str, turn_id: str) -> None:
        now = time.monotonic()
        now_iso = self._now_iso()
        self._thread_id = thread_id
        self._turn_id = turn_id
        self._turn_status = "in_progress"
        self._started_monotonic = now
        self._started_at = now_iso
        self._last_protocol_monotonic = now
        self._last_protocol_at = now_iso
        self._last_protocol_kind = "turn_started"
        self._last_protocol_excerpt = f"Turn {turn_id} started."
        self._last_progress_monotonic = now
        self._last_progress_at = now_iso
        self._last_progress_kind = "turn_started"
        self._last_progress_excerpt = f"Turn {turn_id} started."
        self._timeout_reason = None
        self._write_state()

    def _record_activity(self, message: dict[str, Any]) -> None:
        method = message["method"]
        excerpt = self._activity_excerpt(message)
        self._mark_protocol(method, excerpt=excerpt)
        output_kind = self._output_kind(method)
        if output_kind is not None:
            self._mark_output(output_kind, excerpt=excerpt)
        progress_kind = self._progress_kind(method)
        if progress_kind is not None:
            self._mark_progress(progress_kind, excerpt=excerpt)

    def _mark_protocol(self, kind: str, *, excerpt: str | None = None) -> None:
        now = time.monotonic()
        self._last_protocol_monotonic = now
        self._last_protocol_at = self._now_iso()
        self._last_protocol_kind = kind
        self._last_protocol_excerpt = excerpt
        self._write_state()

    def _mark_output(self, kind: str, *, excerpt: str | None = None) -> None:
        self._last_output_monotonic = time.monotonic()
        self._last_output_at = self._now_iso()
        self._last_output_kind = kind
        self._last_output_excerpt = excerpt
        if kind == "agent_message_delta":
            self._last_agent_excerpt = excerpt
        if kind == "command_output_delta":
            self._last_command_output_excerpt = excerpt
        self._write_state()

    def _mark_progress(self, kind: str, *, excerpt: str | None = None) -> None:
        self._last_progress_monotonic = time.monotonic()
        self._last_progress_at = self._now_iso()
        self._last_progress_kind = kind
        self._last_progress_excerpt = excerpt
        self._write_state()

    def _check_turn_timeout(self) -> None:
        absolute_seconds = self._seconds_since(self._started_monotonic)
        idle_seconds = self._seconds_since(self._last_protocol_monotonic)
        stalled_seconds = self._seconds_since(self._last_progress_monotonic)
        if absolute_seconds >= self.absolute_timeout_seconds:
            self._raise_turn_timeout("absolute_timeout")
        if idle_seconds >= self.idle_timeout_seconds:
            self._raise_turn_timeout("idle_timeout")
        if stalled_seconds >= self.stalled_timeout_seconds:
            self._raise_turn_timeout("stalled_timeout")

    def _raise_turn_timeout(self, reason: str) -> None:
        self._timeout_reason = reason
        self._turn_status = "timed_out"
        self._write_state()
        snapshot = self._observation_snapshot()
        self._emit_event(
            event_type="turn_timeout",
            severity="error",
            message="Codex turn exceeded liveness policy.",
            data={
                "thread_id": self._thread_id,
                "turn_id": self._turn_id,
                "reason": reason,
                "last_progress_kind": self._last_progress_kind,
                "idle_seconds": snapshot["idle_seconds"],
                "stalled_seconds": snapshot["stalled_seconds"],
                "elapsed_seconds": snapshot["elapsed_seconds"],
            },
        )
        raise CodexHarnessTransportError(
            f"{reason.replace('_', ' ')} while waiting for Codex turn {self._turn_id}",
            details=snapshot,
        )

    def _next_wait_timeout(self) -> float:
        remaining = [
            self.absolute_timeout_seconds - self._seconds_since(self._started_monotonic),
            self.idle_timeout_seconds - self._seconds_since(self._last_protocol_monotonic),
            self.stalled_timeout_seconds - self._seconds_since(self._last_progress_monotonic),
        ]
        positives = [value for value in remaining if value > 0]
        if not positives:
            return 0.0
        return min(positives)

    def _check_process_exit(self) -> None:
        if self.process is None:
            return
        return_code = self.process.poll()
        if return_code is None:
            return
        stderr = self._drain_stderr()
        raise CodexHarnessTransportError(
            f"Codex app-server exited unexpectedly with code {return_code}. stderr={stderr}",
            details={
                "return_code": return_code,
                "observation": self._observation_snapshot(),
            },
        )

    def _observation_snapshot(self) -> dict[str, Any]:
        return {
            "status": self._turn_status,
            "run_id": self.run_id,
            "thread_id": self._thread_id,
            "turn_id": self._turn_id,
            "process_id": None if self.process is None else self.process.pid,
            "started_at": self._started_at,
            "last_protocol_at": self._last_protocol_at,
            "last_protocol_kind": self._last_protocol_kind,
            "last_protocol_excerpt": self._last_protocol_excerpt,
            "last_output_at": self._last_output_at,
            "last_output_kind": self._last_output_kind,
            "last_output_excerpt": self._last_output_excerpt,
            "last_agent_excerpt": self._last_agent_excerpt,
            "last_command_output_excerpt": self._last_command_output_excerpt,
            "last_progress_at": self._last_progress_at,
            "last_progress_kind": self._last_progress_kind,
            "last_progress_excerpt": self._last_progress_excerpt,
            "elapsed_seconds": self._seconds_since(self._started_monotonic),
            "idle_seconds": self._seconds_since(self._last_protocol_monotonic),
            "stalled_seconds": self._seconds_since(self._last_progress_monotonic),
            "timeout_reason": self._timeout_reason,
            "timeout_policy": {
                "request_timeout_seconds": self.request_timeout_seconds,
                "idle_timeout_seconds": self.idle_timeout_seconds,
                "stalled_timeout_seconds": self.stalled_timeout_seconds,
                "absolute_timeout_seconds": self.absolute_timeout_seconds,
            },
        }

    def _write_state(self) -> None:
        if self.state_path is None:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(self._observation_snapshot(), indent=2) + "\n",
            encoding="utf-8",
        )

    def _seconds_since(self, started: float | None) -> float | None:
        if started is None:
            return None
        return max(0.0, round(time.monotonic() - started, 3))

    def _output_kind(self, method: str) -> str | None:
        if method == "item/agentMessage/delta":
            return "agent_message_delta"
        if method == "item/commandExecution/outputDelta":
            return "command_output_delta"
        return None

    def _progress_kind(self, method: str) -> str | None:
        if method == "item/agentMessage/delta":
            return "agent_message_delta"
        if method == "item/commandExecution/outputDelta":
            return "command_output_delta"
        if method == "turn/plan/updated":
            return "plan_updated"
        if method == "turn/completed":
            return "turn_completed"
        if method == "item/started":
            return "item_started"
        if method == "item/completed":
            return "item_completed"
        return None

    def _record_incoming_message(self, message: dict[str, Any]) -> None:
        if self.incoming_events_path is None:
            return
        observed_at = self._now_iso()
        params = message.get("params", {})
        payload = {
            "observed_at": observed_at,
            "run_id": self.run_id,
            "thread_id": params.get("threadId"),
            "turn_id": params.get("turnId"),
            "item_id": params.get("itemId"),
            "request_id": message.get("id"),
            "method": message.get("method"),
            "kind": self._incoming_kind(message),
            "excerpt": self._message_excerpt(message),
        }
        self.incoming_events_path.parent.mkdir(parents=True, exist_ok=True)
        with self.incoming_events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")

    def _incoming_kind(self, message: dict[str, Any]) -> str:
        method = message.get("method")
        if method is None:
            if "error" in message:
                return "response_error"
            return "response"
        return self._output_kind(method) or self._progress_kind(method) or method

    def _message_excerpt(self, message: dict[str, Any]) -> str | None:
        method = message.get("method")
        params = message.get("params", {})
        if method == "item/agentMessage/delta":
            return self._trim_excerpt(params.get("delta"))
        if method == "item/commandExecution/outputDelta":
            return self._trim_excerpt(params.get("delta"))
        if method == "turn/plan/updated":
            items = [item.get("text", "") for item in params.get("items", []) if item.get("text")]
            return self._trim_excerpt(" | ".join(items))
        if method == "item/started":
            item = params.get("item", {})
            item_type = item.get("type") or "unknown"
            item_id = item.get("id") or params.get("itemId") or "unknown"
            return self._trim_excerpt(f"{item_type}:{item_id}")
        if method == "item/completed":
            item = params.get("item", {})
            item_type = item.get("type") or "unknown"
            item_id = item.get("id") or params.get("itemId") or "unknown"
            return self._trim_excerpt(f"{item_type}:{item_id}")
        if method == "turn/completed":
            turn = params.get("turn", {})
            return self._trim_excerpt(turn.get("status"))
        if method is None and "result" in message:
            return self._trim_excerpt("response")
        if method is None and "error" in message:
            return self._trim_excerpt(json.dumps(message["error"]))
        return self._trim_excerpt(method)

    def _activity_excerpt(self, message: dict[str, Any]) -> str | None:
        method = message.get("method")
        if method == "item/agentMessage/delta":
            return self._aggregated_agent_message_excerpt(message)
        return self._message_excerpt(message)

    def _aggregated_agent_message_excerpt(self, message: dict[str, Any]) -> str | None:
        params = message.get("params", {})
        item_id = params.get("itemId")
        delta = params.get("delta")
        if item_id is None:
            return self._trim_excerpt(delta)
        previous = self._agent_message_fragments.get(item_id, "")
        self._agent_message_fragments[item_id] = previous + str(delta or "")
        return self._trim_excerpt(self._agent_message_fragments[item_id])

    def _trim_excerpt(self, value: Any, *, limit: int = 200) -> str | None:
        if value is None:
            return None
        text = str(value).strip().replace("\n", "\\n")
        if not text:
            return None
        if len(text) <= limit:
            return text
        return text[: limit - 3] + "..."

    def _now_iso(self) -> str:
        return datetime.now(UTC).isoformat()

    def _drain_stderr(self) -> str:
        if self.process is None or self.process.stderr is None:
            if self._stderr_file is None:
                return ""
        try:
            self._stderr_file.seek(0)
            return self._stderr_file.read()
        except Exception:
            return ""
