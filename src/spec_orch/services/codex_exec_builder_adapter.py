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
from spec_orch.domain.models import BuilderResult, Issue

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

                    match event.get("type"):
                        case "item.completed":
                            item = event.get("item", {})
                            if item.get("type") == "agent_message":
                                state["final_message"] = item.get("text", "")
                        case "turn.plan.updated":
                            state["plan"] = event.get("items", [])
                        case "turn.completed":
                            state["turn_status"] = "success"
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
            },
        )
        _write_report(result)
        return result


def _short_description(event: dict[str, Any]) -> str:
    t: str = event.get("type", "")
    if t == "item.completed":
        item = event.get("item", {})
        itype = item.get("type", "")
        if itype == "agent_message":
            text = item.get("text", "")[:80]
            return f"agent_message: {text}..."
        return f"item.completed ({itype})"
    if t in ("turn.completed", "turn.failed"):
        return t
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
