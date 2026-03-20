"""BuilderAdapter for Droid CLI (droid exec --output-format stream-json).

Factory's Droid supports structured streaming and multiple models.
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


class DroidBuilderAdapter:
    ADAPTER_NAME = "droid"
    AGENT_NAME = "droid"

    def __init__(
        self,
        *,
        executable: str = "droid",
        model: str | None = None,
        absolute_timeout_seconds: float = 1800.0,
        autonomy: str = "high",
    ) -> None:
        self.executable = executable
        self.model = model
        self.absolute_timeout_seconds = absolute_timeout_seconds
        self.autonomy = autonomy

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

            if etype == "message":
                result.append(
                    BuilderEvent(timestamp=ts, kind="message", text=raw.get("content", ""))
                )
            elif etype == "tool_call":
                tool = raw.get("name", "")
                if tool in ("bash", "shell", "terminal"):
                    result.append(
                        BuilderEvent(
                            timestamp=ts,
                            kind="command_end",
                            text=raw.get("input", ""),
                            exit_code=raw.get("exit_code"),
                        )
                    )
                elif tool in ("write_file", "edit_file", "create_file"):
                    result.append(
                        BuilderEvent(
                            timestamp=ts,
                            kind="file_change",
                            file_path=raw.get("path", ""),
                        )
                    )
                else:
                    result.append(BuilderEvent(timestamp=ts, kind="command_end", text=f"{tool}"))
            elif etype == "result":
                result.append(
                    BuilderEvent(
                        timestamp=ts,
                        kind="turn_end",
                        metadata={
                            "cost_usd": raw.get("total_cost_usd", 0),
                            "subtype": raw.get("subtype", ""),
                        },
                    )
                )
            elif etype == "error":
                result.append(BuilderEvent(timestamp=ts, kind="error", text=raw.get("message", "")))
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
                command=[self.executable, "exec"],
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

        command = [
            self.executable,
            "exec",
            "--output-format",
            "stream-json",
            "--auto",
            self.autonomy,
        ]
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
                    if etype == "message":
                        state["final_message"] = event.get("content", "")
                    elif etype == "tool_call":
                        tool = event.get("name", "")
                        if tool in ("write_file", "edit_file", "create_file"):
                            state.setdefault("files_changed", [])
                            fp = event.get("path", "")
                            if fp:
                                state["files_changed"].append(fp)
                        elif tool in ("bash", "shell", "terminal"):
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
                "usage": {"cost_usd": state.get("cost_usd", 0)},
                "commands_completed": state.get("commands_completed", 0),
                "files_changed": state.get("files_changed", []),
            },
        )
        _write_report(result)
        return result


def _short_description(event: dict[str, Any]) -> str:
    etype = event.get("type", "")
    if etype == "message":
        text = event.get("content", "")[:80]
        return f"message: {text}..."
    if etype == "tool_call":
        return f"tool_call: {event.get('name', '')}"
    if etype == "result":
        return f"result: {event.get('subtype', '')}"
    if etype == "error":
        return f"error: {event.get('message', '')[:80]}"
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
