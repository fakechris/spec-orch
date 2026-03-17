"""BuilderAdapter for Claude Code CLI (claude -p --output-format stream-json).

Claude Code supports ``-p`` (print/non-interactive) mode with structured JSON output.
Model selection is limited to Anthropic models.
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


class ClaudeCodeBuilderAdapter:
    ADAPTER_NAME = "claude_code"
    AGENT_NAME = "claude"

    def __init__(
        self,
        *,
        executable: str = "claude",
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

            if etype == "assistant":
                for block in raw.get("message", {}).get("content", []):
                    btype = block.get("type", "")
                    if btype == "text":
                        result.append(
                            BuilderEvent(timestamp=ts, kind="message", text=block.get("text", ""))
                        )
                    elif btype == "tool_use":
                        tool_name = block.get("name", "")
                        if tool_name in ("Bash", "bash"):
                            result.append(
                                BuilderEvent(
                                    timestamp=ts,
                                    kind="command_end",
                                    text=block.get("input", {}).get("command", ""),
                                )
                            )
                        elif tool_name in ("Write", "Edit", "write", "edit"):
                            result.append(
                                BuilderEvent(
                                    timestamp=ts,
                                    kind="file_change",
                                    file_path=block.get("input", {}).get("file_path", ""),
                                )
                            )
            elif etype == "result":
                result.append(
                    BuilderEvent(
                        timestamp=ts,
                        kind="turn_end",
                        metadata={
                            "subtype": raw.get("subtype", ""),
                            "cost_usd": raw.get("total_cost_usd", 0),
                            "session_id": raw.get("session_id", ""),
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
                command=[self.executable, "-p"],
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

        command = [self.executable, "-p", "--output-format", "stream-json"]
        if self.model:
            command.extend(["--model", self.model])
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
        }

        def read_stdout() -> None:
            assert process.stdout is not None
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
                    if etype == "assistant":
                        for block in event.get("message", {}).get("content", []):
                            if block.get("type") == "text":
                                state["final_message"] = block.get("text", "")
                            elif block.get("type") == "tool_use":
                                name = block.get("name", "")
                                if name in ("Write", "Edit", "write", "edit"):
                                    state.setdefault("files_changed", [])
                                    fp = block.get("input", {}).get("file_path", "")
                                    if fp:
                                        state["files_changed"].append(fp)
                                elif name in ("Bash", "bash"):
                                    state.setdefault("commands_completed", 0)
                                    state["commands_completed"] += 1
                    elif etype == "result":
                        subtype = event.get("subtype", "")
                        if subtype == "success":
                            state["turn_status"] = "success"
                            state["final_message"] = event.get("result", state["final_message"])
                        elif subtype == "error":
                            state["turn_status"] = "failure"
                        state["cost_usd"] = event.get("total_cost_usd", 0)
                        state["session_id"] = event.get("session_id", "")
                        state["usage"] = event.get("usage", {})

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
                "usage": state.get("usage", {}),
                "cost_usd": state.get("cost_usd", 0),
                "session_id": state.get("session_id", ""),
                "commands_completed": state.get("commands_completed", 0),
                "files_changed": state.get("files_changed", []),
            },
        )
        _write_report(result)
        return result


def _short_description(event: dict[str, Any]) -> str:
    etype = event.get("type", "")
    if etype == "assistant":
        blocks = event.get("message", {}).get("content", [])
        if blocks:
            first = blocks[0]
            if first.get("type") == "text":
                return f"assistant: {first.get('text', '')[:80]}..."
            if first.get("type") == "tool_use":
                return f"tool: {first.get('name', '')}"
        return "assistant"
    if etype == "result":
        return f"result: {event.get('subtype', '')}"
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
