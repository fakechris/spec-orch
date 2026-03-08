from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Sequence

from spec_orch.domain.models import BuilderResult, Issue


class CodexHarnessTransportError(RuntimeError):
    """Raised when the Codex app-server transport cannot be used."""


class CodexHarnessBuilderAdapter:
    ADAPTER_NAME = "codex_harness"
    AGENT_NAME = "codex"

    def __init__(
        self,
        *,
        executable: str = "codex",
        command: Sequence[str] | None = None,
        timeout_seconds: float = 120.0,
    ) -> None:
        self.executable = executable
        self.command = list(command) if command is not None else [
            executable,
            "app-server",
            "--listen",
            "stdio://",
        ]
        self.timeout_seconds = timeout_seconds

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
                metadata={"transport": "app_server_stdio"},
            )
            self._write_report(result)
            return result

        try:
            with _CodexHarnessSession(
                command=self.command,
                cwd=workspace,
                env=self._build_env(issue),
                timeout_seconds=self.timeout_seconds,
                raw_in_path=telemetry_dir / "raw_harness_in.jsonl",
                raw_out_path=telemetry_dir / "raw_harness_out.jsonl",
                raw_err_path=telemetry_dir / "raw_harness_err.log",
                run_id=run_id,
                event_logger=event_logger,
            ) as session:
                session.initialize()
                thread_id = session.start_thread(cwd=workspace)
                turn_id = session.start_turn(
                    thread_id=thread_id,
                    prompt=issue.builder_prompt,
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


class _CodexHarnessSession:
    def __init__(
        self,
        *,
        command: list[str],
        cwd: Path,
        env: dict[str, str],
        timeout_seconds: float,
        raw_in_path: Path | None = None,
        raw_out_path: Path | None = None,
        raw_err_path: Path | None = None,
        run_id: str | None = None,
        event_logger: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.command = command
        self.cwd = cwd
        self.env = env
        self.timeout_seconds = timeout_seconds
        self.raw_in_path = raw_in_path
        self.raw_out_path = raw_out_path
        self.raw_err_path = raw_err_path
        self.run_id = run_id
        self.event_logger = event_logger
        self._next_id = 1
        self.process: subprocess.Popen[str] | None = None
        self._stderr_file: tempfile.TemporaryFile[str] | None = None

    def __enter__(self) -> "_CodexHarnessSession":
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
            text=True,
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
        self._emit_event(
            event_type="thread_started",
            message="Started Codex thread.",
            data={"thread_id": thread_id},
        )
        return thread_id

    def start_turn(self, *, thread_id: str, prompt: str) -> str:
        response = self._request(
            "turn/start",
            {
                "threadId": thread_id,
                "input": [{"type": "text", "text": prompt}],
            },
        )
        turn_id = response["turn"]["id"]
        self._emit_event(
            event_type="turn_started",
            message="Started Codex turn.",
            data={"thread_id": thread_id, "turn_id": turn_id},
        )
        return turn_id

    def wait_for_turn_completion(self, *, thread_id: str, turn_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.timeout_seconds
        final_message_parts: list[str] = []
        plan_items: list[str] = []
        event_count = 0

        while time.monotonic() < deadline:
            message = self._read_message(deadline)
            if "method" in message and "id" in message:
                self._handle_server_request(message)
                continue
            if "method" not in message:
                continue
            event_count += 1
            if message["method"] == "item/agentMessage/delta":
                params = message["params"]
                if params["threadId"] == thread_id and params["turnId"] == turn_id:
                    final_message_parts.append(params["delta"])
            elif message["method"] == "turn/plan/updated":
                params = message["params"]
                if params["threadId"] == thread_id and params["turnId"] == turn_id:
                    plan_items = [
                        item.get("text", "")
                        for item in params.get("items", [])
                        if item.get("text")
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
                    return {
                        "status": params["turn"]["status"],
                        "final_message": "".join(final_message_parts),
                        "plan": plan_items,
                        "event_count": event_count,
                        "stderr": self._drain_stderr(),
                    }

        raise TimeoutError(f"timed out waiting for Codex turn {turn_id}")

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

        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            message = self._read_message(deadline)
            if "method" in message and "id" in message:
                self._handle_server_request(message)
                continue
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise CodexHarnessTransportError(json.dumps(message["error"]))
            return message["result"]

        raise TimeoutError(f"timed out waiting for response to {method}")

    def _write_message(self, payload: dict[str, Any]) -> None:
        if self.process is None or self.process.stdin is None:
            raise CodexHarnessTransportError("Codex app-server stdin is not available")
        serialized = json.dumps(payload)
        if self.raw_in_path is not None:
            with self.raw_in_path.open("a", encoding="utf-8") as handle:
                handle.write(serialized + "\n")
        self.process.stdin.write(serialized + "\n")
        self.process.stdin.flush()

    def _read_message(self, deadline: float) -> dict[str, Any]:
        if self.process is None or self.process.stdout is None:
            raise CodexHarnessTransportError("Codex app-server stdout is not available")
        if time.monotonic() >= deadline:
            raise TimeoutError("timed out waiting for Codex app-server output")

        line = self.process.stdout.readline()
        if line == "":
            stderr = self._drain_stderr()
            raise CodexHarnessTransportError(
                f"Codex app-server closed the stdio stream unexpectedly. stderr={stderr}"
            )
        if self.raw_out_path is not None:
            with self.raw_out_path.open("a", encoding="utf-8") as handle:
                handle.write(line)
        return json.loads(line)

    def _handle_server_request(self, message: dict[str, Any]) -> None:
        method = message["method"]
        request_id = message["id"]
        params = message.get("params", {})

        if method == "item/commandExecution/requestApproval":
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
            return

        if method == "item/fileChange/requestApproval":
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

    def _drain_stderr(self) -> str:
        if self.process is None or self.process.stderr is None:
            if self._stderr_file is None:
                return ""
        try:
            self._stderr_file.seek(0)
            return self._stderr_file.read()
        except Exception:
            return ""
