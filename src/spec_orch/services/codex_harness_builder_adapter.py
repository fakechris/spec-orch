from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
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

    def run(self, *, issue: Issue, workspace: Path) -> BuilderResult:
        report_path = workspace / "builder_report.json"
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
    ) -> None:
        self.command = command
        self.cwd = cwd
        self.env = env
        self.timeout_seconds = timeout_seconds
        self._next_id = 1
        self.process: subprocess.Popen[str] | None = None
        self._stderr_file: tempfile.TemporaryFile[str] | None = None

    def __enter__(self) -> "_CodexHarnessSession":
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
                "approvalPolicy": "never",
                "sandbox": "workspace-write",
                "model": "codex",
                "personality": "pragmatic",
                "serviceName": "spec-orch-builder",
            },
        )
        return response["thread"]["id"]

    def start_turn(self, *, thread_id: str, prompt: str) -> str:
        response = self._request(
            "turn/start",
            {
                "threadId": thread_id,
                "input": [{"type": "text", "text": prompt}],
            },
        )
        return response["turn"]["id"]

    def wait_for_turn_completion(self, *, thread_id: str, turn_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.timeout_seconds
        final_message_parts: list[str] = []
        plan_items: list[str] = []
        event_count = 0

        while time.monotonic() < deadline:
            message = self._read_message(deadline)
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
                raise CodexHarnessTransportError(
                    f"unexpected server request during {method}: {message['method']}"
                )
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise CodexHarnessTransportError(json.dumps(message["error"]))
            return message["result"]

        raise TimeoutError(f"timed out waiting for response to {method}")

    def _write_message(self, payload: dict[str, Any]) -> None:
        if self.process is None or self.process.stdin is None:
            raise CodexHarnessTransportError("Codex app-server stdin is not available")
        self.process.stdin.write(json.dumps(payload) + "\n")
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
        return json.loads(line)

    def _drain_stderr(self) -> str:
        if self.process is None or self.process.stderr is None:
            if self._stderr_file is None:
                return ""
        try:
            self._stderr_file.seek(0)
            return self._stderr_file.read()
        except Exception:
            return ""
