"""BuilderAdapter for OpenCode CLI (opencode run --format json).

OpenCode emits JSONL events: step_start, tool_use, text, step_finish.
Supports 75+ model providers via ``-m provider/model``.
"""

from __future__ import annotations

import json
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from spec_orch.domain.compliance import default_turn_contract_compliance
from spec_orch.domain.models import BuilderEvent, BuilderResult, Issue

PREAMBLE = (
    "You are the SpecOrch builder for this issue workspace. "
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

            if etype == "step_start":
                result.append(BuilderEvent(timestamp=ts, kind="message", text="Step started"))
            elif etype == "tool_use":
                tool = raw.get("tool", "")
                status = raw.get("status", "")
                if tool == "bash" and status == "completed":
                    result.append(
                        BuilderEvent(
                            timestamp=ts,
                            kind="command_end",
                            text=raw.get("input", {}).get("command", ""),
                            exit_code=raw.get("metadata", {}).get("exit_code"),
                        )
                    )
                elif tool in ("write", "edit") and status == "completed":
                    file_path = raw.get("input", {}).get("file_path") or raw.get("input", {}).get(
                        "path", ""
                    )
                    result.append(
                        BuilderEvent(timestamp=ts, kind="file_change", file_path=file_path)
                    )
                else:
                    result.append(
                        BuilderEvent(
                            timestamp=ts,
                            kind="command_end",
                            text=f"{tool}: {raw.get('output', '')[:200]}",
                        )
                    )
            elif etype == "text":
                result.append(BuilderEvent(timestamp=ts, kind="message", text=raw.get("text", "")))
            elif etype == "step_finish":
                result.append(
                    BuilderEvent(
                        timestamp=ts,
                        kind="turn_end",
                        metadata={
                            "cost_usd": raw.get("cost_usd", 0),
                            "input_tokens": raw.get("input_tokens", 0),
                            "output_tokens": raw.get("output_tokens", 0),
                            "reason": raw.get("reason", ""),
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

        process = subprocess.Popen(
            command,
            cwd=workspace,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
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
                    if etype == "text":
                        state["final_message"] = event.get("text", "")
                    elif etype == "tool_use":
                        tool = event.get("tool", "")
                        if tool in ("write", "edit"):
                            state.setdefault("files_changed", [])
                            fp = event.get("input", {}).get("file_path") or event.get(
                                "input", {}
                            ).get("path", "")
                            if fp:
                                state["files_changed"].append(fp)
                        elif tool == "bash":
                            state.setdefault("commands_completed", 0)
                            state["commands_completed"] += 1
                    elif etype == "step_finish":
                        reason = event.get("reason", "")
                        state["total_cost_usd"] += event.get("cost_usd", 0)
                        state["total_input_tokens"] += event.get("input_tokens", 0)
                        state["total_output_tokens"] += event.get("output_tokens", 0)
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
    if etype == "step_start":
        return "step_start"
    if etype == "tool_use":
        tool = event.get("tool", "")
        status = event.get("status", "")
        return f"tool_use: {tool} ({status})"
    if etype == "text":
        text = event.get("text", "")[:80]
        return f"text: {text}..."
    if etype == "step_finish":
        reason = event.get("reason", "")
        cost = event.get("cost_usd", 0)
        return f"step_finish ({reason}, ${cost:.4f})"
    return etype or "event"


def _write_report(result: BuilderResult) -> None:
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
        + "\n",
        encoding="utf-8",
    )
