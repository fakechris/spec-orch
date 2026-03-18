"""BuilderAdapter for ACPX — Agent Client Protocol headless CLI.

ACPX provides a unified interface to 15+ coding agents (OpenCode, Codex,
Claude, Gemini, Droid, etc.) via the ACP protocol.  This adapter replaces
per-agent CLI wrappers with a single, session-aware implementation.

Usage via spec-orch.toml::

    [builder]
    adapter = "acpx"
    agent = "opencode"                 # or codex, claude, gemini, droid, ...
    model = "minimax/MiniMax-M2.5"     # passed through to the agent
    timeout_seconds = 1800
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spec_orch.domain.compliance import default_turn_contract_compliance
from spec_orch.domain.models import BuilderEvent, BuilderResult, Issue

logger = logging.getLogger(__name__)

PREAMBLE = (
    "You are the SpecOrch builder for this issue workspace. "
    "Your current working directory IS the project root — "
    "all file paths must be relative to it. "
    "Move directly into implementation and verification. "
    "Minimize workflow narration and process summaries."
)


class AcpxBuilderAdapter:
    """Unified builder adapter using ACPX (Agent Client Protocol)."""

    ADAPTER_NAME = "acpx"
    AGENT_NAME: str

    def __init__(
        self,
        *,
        agent: str = "opencode",
        model: str | None = None,
        session_name: str | None = None,
        permissions: str = "full-auto",
        executable: str = "npx",
        acpx_package: str = "acpx",
        absolute_timeout_seconds: float = 1800.0,
    ) -> None:
        self.agent = agent
        self.AGENT_NAME = agent
        self.model = model
        self.session_name = session_name
        self.permissions = permissions
        self.executable = executable
        self.acpx_package = acpx_package
        self.absolute_timeout_seconds = absolute_timeout_seconds

    def can_handle(self, issue: Issue) -> bool:
        return True

    def prepare(self, *, issue: Issue, workspace: Path) -> None:
        if self.session_name:
            self._ensure_session(workspace)

    def collect_artifacts(self, workspace: Path) -> list[Path]:
        artifacts: list[Path] = []
        for name in ("builder_report.json", "telemetry/incoming_events.jsonl"):
            p = workspace / name
            if p.exists():
                artifacts.append(p)
        return artifacts

    def run(
        self,
        *,
        issue: Issue,
        workspace: Path,
        run_id: str | None = None,
        event_logger: Callable[[dict[str, Any]], None] | None = None,
    ) -> BuilderResult:
        prompt = issue.builder_prompt or issue.summary
        full_prompt = f"{PREAMBLE}\n\n{prompt}"

        cmd = self._build_command(full_prompt)
        raw_events: list[dict[str, Any]] = []
        stdout_lines: list[str] = []

        env = self._build_env()

        try:
            process = subprocess.Popen(
                cmd,
                cwd=workspace,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
        except FileNotFoundError:
            return BuilderResult(
                succeeded=False,
                command=cmd,
                stdout="",
                stderr=f"ACPX executable not found: {self.executable}",
                report_path=workspace / "builder_report.json",
                adapter=self.ADAPTER_NAME,
                agent=self.AGENT_NAME,
            )

        stderr_lines: list[str] = []

        def _read_stdout() -> None:
            assert process.stdout is not None
            for line in process.stdout:
                stdout_lines.append(line)
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    event = json.loads(stripped)
                    raw_events.append(event)
                    if event_logger:
                        event_logger(event)
                except json.JSONDecodeError:
                    pass

        stdout_thread = threading.Thread(target=_read_stdout, daemon=True)
        stderr_thread = threading.Thread(
            target=self._drain_stderr,
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
                command=cmd,
                stdout="".join(stdout_lines),
                stderr=f"Timeout after {self.absolute_timeout_seconds}s",
                report_path=workspace / "builder_report.json",
                adapter=self.ADAPTER_NAME,
                agent=self.AGENT_NAME,
            )

        stderr_text = "".join(stderr_lines)

        compliance = default_turn_contract_compliance()
        succeeded = process.returncode == 0

        report_path = workspace / "builder_report.json"
        report_data = {
            "adapter": self.ADAPTER_NAME,
            "agent": self.AGENT_NAME,
            "acpx_agent": self.agent,
            "model": self.model,
            "succeeded": succeeded,
            "exit_code": process.returncode,
            "event_count": len(raw_events),
            "session_name": self.session_name,
        }
        report_path.write_text(json.dumps(report_data, indent=2))

        return BuilderResult(
            succeeded=succeeded,
            command=cmd,
            stdout="".join(stdout_lines),
            stderr=stderr_text,
            report_path=report_path,
            adapter=self.ADAPTER_NAME,
            agent=self.AGENT_NAME,
            metadata={"turn_contract_compliance": compliance},
        )

    def map_events(self, raw_events: list[dict[str, Any]]) -> list[BuilderEvent]:
        """Map ACP protocol events to vendor-neutral BuilderEvent.

        Handles three event lineages:
        1. ACP generic (type=text/tool_call/result/error)
        2. Codex-style (type=item.started/item.completed/turn.plan.updated)
        3. OpenCode-style (type=step_start/tool_use/step_finish/text)
        """
        result: list[BuilderEvent] = []
        for raw in raw_events:
            ts = str(
                raw.get(
                    "timestamp",
                    datetime.now(UTC).isoformat(),
                )
            )
            ev_type = raw.get("type", "")
            method = raw.get("method", "")
            params = raw.get("params", {})

            mapped = self._map_acp_event(ts, ev_type, method, params, raw)
            if mapped:
                result.append(mapped)
                continue

            mapped = self._map_codex_event(ts, ev_type, raw)
            if mapped:
                result.append(mapped)
                continue

            mapped = self._map_opencode_event(ts, ev_type, raw)
            if mapped:
                result.append(mapped)

        return result

    def _map_acp_event(
        self,
        ts: str,
        ev_type: str,
        method: str,
        params: dict[str, Any],
        raw: dict[str, Any],
    ) -> BuilderEvent | None:
        """Map standard ACP protocol events."""
        if ev_type == "text" or method == "text":
            text = params.get("text", raw.get("text", "")) if params else raw.get("text", "")
            if text:
                return BuilderEvent(timestamp=ts, kind="message", text=str(text))
            return None

        if ev_type == "tool_call" or method == "tools/call":
            return self._map_tool_call(ts, params)

        if ev_type == "result" or method == "session/result":
            text = params.get("text", raw.get("text", "")) if params else raw.get("text", "")
            return BuilderEvent(timestamp=ts, kind="turn_end", text=str(text))

        if ev_type == "error":
            error_text = (
                params.get("message", str(raw.get("error", "")))
                if params
                else str(raw.get("error", ""))
            )
            return BuilderEvent(timestamp=ts, kind="error", text=error_text)

        return None

    @staticmethod
    def _map_codex_event(ts: str, ev_type: str, raw: dict[str, Any]) -> BuilderEvent | None:
        """Map Codex-style events (item.started/completed, turn.plan.updated)."""
        item = raw.get("item", {})
        itype = item.get("type", "")

        if ev_type == "item.started" and itype == "command_execution":
            return BuilderEvent(
                timestamp=ts,
                kind="command_start",
                text=item.get("command", ""),
            )
        if ev_type == "item.completed":
            if itype == "command_execution":
                return BuilderEvent(
                    timestamp=ts,
                    kind="command_end",
                    text=item.get("command", ""),
                    exit_code=item.get("exit_code"),
                )
            if itype == "agent_message":
                return BuilderEvent(
                    timestamp=ts,
                    kind="message",
                    text=item.get("text", ""),
                )
            if itype == "file_change":
                return BuilderEvent(
                    timestamp=ts,
                    kind="file_change",
                    file_path=item.get("file"),
                )
            if itype == "reasoning":
                return BuilderEvent(
                    timestamp=ts,
                    kind="reasoning",
                    text=item.get("text", ""),
                )
        if ev_type == "turn.plan.updated":
            return BuilderEvent(
                timestamp=ts,
                kind="plan",
                metadata={"items": raw.get("items", [])},
            )

        return None

    @staticmethod
    def _map_opencode_event(ts: str, ev_type: str, raw: dict[str, Any]) -> BuilderEvent | None:
        """Map OpenCode-style events (step_start/tool_use/step_finish)."""
        part = raw.get("part", {})

        if ev_type == "step_start":
            return BuilderEvent(timestamp=ts, kind="message", text="Step started")

        if ev_type == "tool_use":
            tool = part.get("tool", "")
            state = part.get("state", {})
            if state.get("status") != "completed":
                return None
            inp = state.get("input", {})
            lower_tool = tool.lower()
            if lower_tool == "bash":
                return BuilderEvent(
                    timestamp=ts,
                    kind="command_end",
                    text=inp.get("command", ""),
                    metadata={"tool": tool},
                )
            if lower_tool in ("write", "edit"):
                fp = inp.get("filePath") or inp.get("file_path") or inp.get("path", "")
                return BuilderEvent(
                    timestamp=ts,
                    kind="file_change",
                    file_path=fp,
                    metadata={"tool": tool},
                )
            return BuilderEvent(
                timestamp=ts,
                kind="message",
                text=f"Tool: {tool}",
                metadata={"tool": tool},
            )

        if ev_type == "step_finish":
            return BuilderEvent(
                timestamp=ts,
                kind="turn_end",
                text=part.get("reason", ""),
            )

        return None

    def _map_tool_call(self, ts: str, params: dict[str, Any]) -> BuilderEvent:
        """Map a generic ACP tool_call event."""
        tool_name = params.get("name", "") if params else ""
        tool_input = params.get("input", {}) if params else {}
        lower_name = tool_name.lower()

        if lower_name in ("bash", "shell", "terminal", "execute"):
            cmd_text = (
                tool_input.get("command", "") if isinstance(tool_input, dict) else str(tool_input)
            )
            return BuilderEvent(
                timestamp=ts,
                kind="command_end",
                text=cmd_text,
                metadata={"tool": tool_name},
            )

        if lower_name in (
            "write",
            "edit",
            "write_file",
            "edit_file",
            "create_file",
        ):
            fp = tool_input.get("path", "") if isinstance(tool_input, dict) else ""
            return BuilderEvent(
                timestamp=ts,
                kind="file_change",
                text=tool_name,
                file_path=fp,
                metadata={"tool": tool_name},
            )

        return BuilderEvent(
            timestamp=ts,
            kind="message",
            text=f"Tool: {tool_name}",
            metadata={"tool": tool_name, "input": tool_input},
        )

    def _build_command(self, prompt: str) -> list[str]:
        cmd = [self.executable, "-y", self.acpx_package, self.agent]

        if self.session_name:
            cmd.extend(["-s", self.session_name])

        cmd.extend(["--format", "json"])

        if self.permissions:
            cmd.extend(["--permissions", self.permissions])

        cmd.append(prompt)
        return cmd

    def _build_env(self) -> dict[str, str]:
        env = dict(os.environ)
        if self.model:
            env.setdefault("ACPX_MODEL", self.model)
        return env

    def _ensure_session(self, workspace: Path) -> None:
        """Ensure a named session exists (create if needed)."""
        cmd = [
            self.executable,
            "-y",
            self.acpx_package,
            self.agent,
            "sessions",
            "ensure",
            "-s",
            self.session_name or "default",
        ]
        result = subprocess.run(
            cmd,
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            logger.warning(
                "Session ensure failed (rc=%d): %s",
                result.returncode,
                result.stderr.strip(),
            )

    def cancel_session(self, workspace: Path) -> None:
        """Cancel the current prompt in the named session."""
        if not self.session_name:
            return
        cmd = [
            self.executable,
            "-y",
            self.acpx_package,
            self.agent,
            "sessions",
            "cancel",
            "-s",
            self.session_name,
        ]
        subprocess.run(
            cmd,
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )

    @staticmethod
    def _drain_stderr(
        process: subprocess.Popen[str],
        container: list[str],
    ) -> None:
        assert process.stderr is not None
        for line in process.stderr:
            container.append(line)
