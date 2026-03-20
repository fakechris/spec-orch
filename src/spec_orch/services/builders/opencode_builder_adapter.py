"""BuilderAdapter for OpenCode CLI (opencode run --format json).

OpenCode emits JSONL events: step_start, tool_use, text, step_finish.
Supports 75+ model providers via ``-m provider/model``.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from spec_orch.domain.compliance import default_turn_contract_compliance
from spec_orch.domain.models import BuilderEvent, BuilderResult, Issue
from spec_orch.services.io import atomic_write_json

PREAMBLE = (
    "You are the SpecOrch builder for this issue workspace. "
    "Your current working directory IS the project root — "
    "all file paths must be relative to it (e.g. 'docs/foo.md', not '../docs/foo.md'). "
    "NEVER resolve the git repository root to a different directory; "
    "treat cwd as the authoritative project root. "
    "Move directly into implementation and verification. "
    "Minimize workflow narration, tool-loading commentary, and process summaries. "
    "Only stop to explain when blocked, when requesting approval, "
    "or when reporting the final outcome."
)


class OpenCodeBuilderAdapter:
    ADAPTER_NAME = "opencode"
    AGENT_NAME = "opencode"

    def __init__(
        self,
        *,
        executable: str = "opencode",
        model: str | None = None,
        absolute_timeout_seconds: float = 1800.0,
    ) -> None:
        self.executable = executable
        self.model = model
        self.absolute_timeout_seconds = absolute_timeout_seconds

    def can_handle(self, issue: Issue) -> bool:
        return True

    def prepare(self, *, issue: Issue, workspace: Path) -> None:
        pass

    def collect_artifacts(self, workspace: Path) -> list[Path]:
        artifacts: list[Path] = []
        for name in ("builder_report.json", "telemetry/incoming_events.jsonl"):
            p = workspace / name
            if p.exists():
                artifacts.append(p)
        return artifacts

    def map_events(self, raw_events: list[dict[str, Any]]) -> list[BuilderEvent]:
        from datetime import UTC, datetime

        result: list[BuilderEvent] = []
        for raw in raw_events:
            etype = raw.get("type", "")
            ts = str(raw.get("timestamp", datetime.now(UTC).isoformat()))
            part = raw.get("part", {})

            if etype == "step_start":
                result.append(BuilderEvent(timestamp=ts, kind="message", text="Step started"))

            elif etype == "tool_use":
                tool = part.get("tool", "")
                state = part.get("state", {})
                status = state.get("status", "")
                inp = state.get("input", {})
                output = state.get("output", "")

                if status != "completed":
                    continue

                if tool == "bash":
                    result.append(
                        BuilderEvent(
                            timestamp=ts,
                            kind="command_end",
                            text=inp.get("command", ""),
                            exit_code=state.get("metadata", {}).get("exit_code"),
                        )
                    )
                elif tool in ("write", "edit"):
                    file_path = inp.get("filePath") or inp.get("file_path") or inp.get("path", "")
                    result.append(
                        BuilderEvent(timestamp=ts, kind="file_change", file_path=file_path)
                    )
                else:
                    result.append(
                        BuilderEvent(
                            timestamp=ts,
                            kind="command_end",
                            text=f"{tool}: {str(output)[:200]}",
                        )
                    )

            elif etype == "text":
                result.append(BuilderEvent(timestamp=ts, kind="message", text=part.get("text", "")))

            elif etype == "step_finish":
                tokens = part.get("tokens", {})
                result.append(
                    BuilderEvent(
                        timestamp=ts,
                        kind="turn_end",
                        metadata={
                            "cost_usd": part.get("cost", 0),
                            "input_tokens": tokens.get("input", 0),
                            "output_tokens": tokens.get("output", 0),
                            "reason": part.get("reason", ""),
                        },
                    )
                )
        return result

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
        incoming_path = telemetry_dir / "incoming_events.jsonl"

        if issue.builder_prompt is None:
            result = BuilderResult(
                succeeded=True,
                command=[self.executable, "run"],
                stdout="",
                stderr="",
                report_path=report_path,
                skipped=True,
                adapter=self.ADAPTER_NAME,
                agent=self.AGENT_NAME,
                metadata={"turn_contract_compliance": default_turn_contract_compliance()},
            )
            _write_report(result)
            return result

        prompt = f"{PREAMBLE}\n\n{issue.builder_prompt}"

        command = [self.executable, "run", "--format", "json"]
        if self.model:
            command.extend(["-m", self.model])
        command.append(prompt)

        # OpenCode's MiniMax provider uses @ai-sdk/anthropic which reads
        # ANTHROPIC_API_KEY. Inject it from spec-orch's own key env vars
        # so users don't need to set a separate variable.
        env = os.environ.copy()
        if not env.get("ANTHROPIC_API_KEY"):
            for key_env in ("SPEC_ORCH_LLM_API_KEY", "MINIMAX_API_KEY"):
                if val := env.get(key_env):
                    env["ANTHROPIC_API_KEY"] = val
                    break

        process = subprocess.Popen(
            command,
            cwd=workspace,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )

        state: dict[str, Any] = {
            "final_message": "",
            "turn_status": "unknown",
            "total_cost_usd": 0.0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
        }

        def read_stdout() -> None:
            if process.stdout is None:
                return
            with incoming_path.open("w", encoding="utf-8") as out_file:
                for line in process.stdout:
                    if not line.strip():
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    out_file.write(line)
                    out_file.flush()

                    if event_logger:
                        event_logger(
                            {
                                "event_type": event.get("type", "unknown"),
                                "message": _short_description(event),
                                "data": event,
                            }
                        )

                    etype = event.get("type", "")
                    part = event.get("part", {})
                    if etype == "text":
                        state["final_message"] = part.get("text", "")
                    elif etype == "tool_use":
                        tool = part.get("tool", "")
                        evt_state = part.get("state", {})
                        if evt_state.get("status") != "completed":
                            continue
                        inp = evt_state.get("input", {})
                        if tool in ("write", "edit"):
                            state.setdefault("files_changed", [])
                            fp = inp.get("filePath") or inp.get("file_path") or inp.get("path", "")
                            if fp:
                                state["files_changed"].append(fp)
                        elif tool == "bash":
                            state.setdefault("commands_completed", 0)
                            state["commands_completed"] += 1
                    elif etype == "step_finish":
                        reason = part.get("reason", "")
                        tokens = part.get("tokens", {})
                        state["total_cost_usd"] += part.get("cost", 0)
                        state["total_input_tokens"] += tokens.get("input", 0)
                        state["total_output_tokens"] += tokens.get("output", 0)
                        if reason == "stop":
                            state["turn_status"] = "success"

        reader = threading.Thread(target=read_stdout, daemon=True)
        reader.start()

        try:
            process.wait(timeout=self.absolute_timeout_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            state["turn_status"] = "timeout"
        reader.join(timeout=5.0)

        stderr = process.stderr.read() if process.stderr else ""
        turn_status = state["turn_status"]
        if turn_status == "unknown":
            turn_status = "success" if process.returncode == 0 else "failure"
        succeeded = turn_status == "success"

        result = BuilderResult(
            succeeded=succeeded,
            command=command,
            stdout=state["final_message"],
            stderr=stderr,
            report_path=report_path,
            adapter=self.ADAPTER_NAME,
            agent=self.AGENT_NAME,
            metadata={
                "run_id": run_id,
                "turn_status": turn_status,
                "turn_contract_compliance": default_turn_contract_compliance(),
                "usage": {
                    "cost_usd": state["total_cost_usd"],
                    "input_tokens": state["total_input_tokens"],
                    "output_tokens": state["total_output_tokens"],
                },
                "commands_completed": state.get("commands_completed", 0),
                "files_changed": state.get("files_changed", []),
            },
        )
        _write_report(result)
        return result


def _short_description(event: dict[str, Any]) -> str:
    etype = event.get("type", "")
    part = event.get("part", {})
    if etype == "step_start":
        return "step_start"
    if etype == "tool_use":
        tool = part.get("tool", "")
        status = part.get("state", {}).get("status", "")
        return f"tool_use: {tool} ({status})"
    if etype == "text":
        text = part.get("text", "")[:80]
        return f"text: {text}..."
    if etype == "step_finish":
        reason = part.get("reason", "")
        cost = part.get("cost", 0)
        return f"step_finish ({reason}, ${cost:.4f})"
    return etype or "event"


def _write_report(result: BuilderResult) -> None:
    atomic_write_json(
        result.report_path,
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
    )
