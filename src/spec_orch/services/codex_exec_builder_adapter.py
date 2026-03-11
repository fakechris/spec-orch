from __future__ import annotations

import json
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from spec_orch.domain.compliance import (
    default_turn_contract_compliance,
    evaluate_pre_action_narration_compliance,
)
from spec_orch.domain.models import BuilderEvent, BuilderResult, Issue

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


class CodexExecBuilderAdapter:
    ADAPTER_NAME = "codex_exec"
    AGENT_NAME = "codex"

    def __init__(
        self,
        *,
        executable: str = "codex",
        absolute_timeout_seconds: float = 1800.0,
    ) -> None:
        self.executable = executable
        self.absolute_timeout_seconds = absolute_timeout_seconds
        self._command_base = [
            executable,
            "exec",
            "--json",
            "--sandbox",
            "workspace-write",
            "--skip-git-repo-check",
        ]

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

    def map_events(
        self, raw_events: list[dict[str, Any]],
    ) -> list[BuilderEvent]:
        """Convert Codex JSONL events to vendor-neutral BuilderEvent."""
        from datetime import UTC, datetime

        result: list[BuilderEvent] = []
        for raw in raw_events:
            etype = raw.get("type", "")
            item = raw.get("item", {})
            itype = item.get("type", "")
            ts = raw.get("timestamp", datetime.now(UTC).isoformat())
            if etype == "item.started" and itype == "command_execution":
                result.append(BuilderEvent(
                    timestamp=ts, kind="command_start",
                    text=item.get("command", ""),
                ))
            elif etype == "item.completed" and itype == "command_execution":
                result.append(BuilderEvent(
                    timestamp=ts, kind="command_end",
                    text=item.get("command", ""),
                    exit_code=item.get("exit_code"),
                ))
            elif etype == "item.completed" and itype == "agent_message":
                result.append(BuilderEvent(
                    timestamp=ts, kind="message",
                    text=item.get("text", ""),
                ))
            elif etype == "item.completed" and itype == "file_change":
                result.append(BuilderEvent(
                    timestamp=ts, kind="file_change",
                    file_path=item.get("file"),
                ))
            elif etype == "item.completed" and itype == "reasoning":
                result.append(BuilderEvent(
                    timestamp=ts, kind="reasoning",
                    text=item.get("text", ""),
                ))
            elif etype == "turn.plan.updated":
                result.append(BuilderEvent(
                    timestamp=ts, kind="plan",
                    metadata={"items": raw.get("items", [])},
                ))
            elif etype == "turn.completed":
                result.append(BuilderEvent(
                    timestamp=ts, kind="turn_end",
                    metadata=raw.get("usage", {}),
                ))
            elif etype == "turn.failed":
                result.append(BuilderEvent(
                    timestamp=ts, kind="error",
                    text="Turn failed",
                ))
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
                command=self._command_base,
                stdout="",
                stderr="",
                report_path=report_path,
                skipped=True,
                adapter=self.ADAPTER_NAME,
                agent=self.AGENT_NAME,
                metadata={
                    "turn_contract_compliance": default_turn_contract_compliance(),
                },
            )
            _write_report(result)
            return result

        prompt = (
            f"{PREAMBLE}\n\n"
            "--- BEGIN USER ISSUE PROMPT (untrusted) ---\n"
            f"{issue.builder_prompt}\n"
            "--- END USER ISSUE PROMPT ---"
        )
        command = self._command_base + [prompt]
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
            "plan": [],
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
                    item = event.get("item", {})
                    itype = item.get("type", "")
                    match etype:
                        case "item.started":
                            if itype == "command_execution":
                                state.setdefault("commands_started", 0)
                                state["commands_started"] += 1
                        case "item.completed":
                            if itype == "agent_message":
                                state["final_message"] = item.get("text", "")
                            elif itype == "command_execution":
                                state.setdefault("commands_completed", 0)
                                state["commands_completed"] += 1
                            elif itype == "file_change":
                                state.setdefault("files_changed", [])
                                state["files_changed"].append(
                                    item.get("file", "")
                                )
                        case "turn.plan.updated":
                            state["plan"] = event.get("items", [])
                        case "turn.completed":
                            state["turn_status"] = "success"
                            state["usage"] = event.get("usage", {})
                        case "turn.failed":
                            state["turn_status"] = "failure"

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
        final_message = state["final_message"]
        plan = state["plan"]
        turn_status = state["turn_status"]
        if turn_status == "unknown":
            turn_status = "success" if process.returncode == 0 else "failure"
        succeeded = turn_status == "success"

        compliance = evaluate_pre_action_narration_compliance(incoming_path)
        result = BuilderResult(
            succeeded=succeeded,
            command=command,
            stdout=final_message,
            stderr=stderr,
            report_path=report_path,
            adapter=self.ADAPTER_NAME,
            agent=self.AGENT_NAME,
            metadata={
                "run_id": run_id,
                "plan": plan,
                "turn_status": turn_status,
                "turn_contract_compliance": compliance,
                "usage": state.get("usage", {}),
                "commands_started": state.get("commands_started", 0),
                "commands_completed": state.get("commands_completed", 0),
                "files_changed": state.get("files_changed", []),
            },
        )
        _write_report(result)
        return result


def _short_description(event: dict[str, Any]) -> str:
    t: str = event.get("type", "")
    item = event.get("item", {})
    itype = item.get("type", "")
    match t:
        case "item.started":
            if itype == "command_execution":
                return f"command_started: {item.get('command', '')}"
            return f"item.started ({itype})"
        case "item.completed":
            if itype == "agent_message":
                text = item.get("text", "")[:80]
                return f"agent_message: {text}..."
            if itype == "command_execution":
                exit_code = item.get("exit_code", "?")
                cmd = item.get("command", "")
                return f"command_completed: {cmd} (exit {exit_code})"
            if itype == "file_change":
                return f"file_change: {item.get('file', '')}"
            if itype == "reasoning":
                text = item.get("text", "")[:60]
                return f"reasoning: {text}..."
            return f"item.completed ({itype})"
        case "turn.completed":
            usage = event.get("usage", {})
            if usage:
                return (
                    f"turn.completed "
                    f"({usage.get('input_tokens', 0)} in"
                    f" / {usage.get('output_tokens', 0)} out)"
                )
            return "turn.completed"
        case "turn.failed":
            return "turn.failed"
        case "turn.plan.updated":
            items = event.get("items", [])
            return f"plan.updated ({len(items)} items)"
    return t or "event"


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
