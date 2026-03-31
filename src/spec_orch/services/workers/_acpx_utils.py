from __future__ import annotations

import json
import logging
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from spec_orch.runtime_core.tool_runtime.executor import execute_tool_request
from spec_orch.runtime_core.tool_runtime.models import (
    ToolConcurrencyClass,
    ToolDefinition,
    ToolExecutionRequest,
    ToolPermissionClass,
)
from spec_orch.runtime_core.tool_runtime.registry import ToolRegistry

logger = logging.getLogger(__name__)

_TOOL_REGISTRY = ToolRegistry()


def _session_ensure_adapter(arguments: dict[str, Any]) -> dict[str, Any]:
    workspace = Path(str(arguments["workspace"]))
    cmd = [
        str(arguments["executable"]),
        "-y",
        str(arguments["acpx_package"]),
        str(arguments["agent"]),
        "sessions",
        "ensure",
        "--name",
        str(arguments["session_name"]),
    ]
    result = subprocess.run(
        cmd,
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "command": cmd,
    }


def _session_cancel_adapter(arguments: dict[str, Any]) -> dict[str, Any]:
    workspace = Path(str(arguments["workspace"]))
    cmd = [
        str(arguments["executable"]),
        "-y",
        str(arguments["acpx_package"]),
        str(arguments["agent"]),
        "cancel",
        "-s",
        str(arguments["session_name"]),
    ]
    result = subprocess.run(
        cmd,
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "command": cmd,
    }


_TOOL_REGISTRY.register(
    ToolDefinition(
        name="acpx.session.ensure",
        aliases=("acpx.ensure_session",),
        adapter=_session_ensure_adapter,
        required_fields=("workspace", "executable", "acpx_package", "agent", "session_name"),
        permission_class=ToolPermissionClass.SESSION_ADMIN,
        concurrency_class=ToolConcurrencyClass.SERIAL,
        telemetry_label="acpx-session-ensure",
    )
)
_TOOL_REGISTRY.register(
    ToolDefinition(
        name="acpx.session.cancel",
        aliases=("acpx.cancel_session",),
        adapter=_session_cancel_adapter,
        required_fields=("workspace", "executable", "acpx_package", "agent", "session_name"),
        permission_class=ToolPermissionClass.SESSION_ADMIN,
        concurrency_class=ToolConcurrencyClass.SERIAL,
        telemetry_label="acpx-session-cancel",
    )
)


def _tool_runtime_root(workspace: Path) -> Path:
    return workspace / "telemetry" / "tool_runtime"


def build_acpx_command(
    *,
    executable: str,
    acpx_package: str,
    agent: str,
    prompt: str,
    model: str | None = None,
    session_name: str | None = None,
    permissions: str = "full-auto",
) -> list[str]:
    cmd = [executable, "-y", acpx_package, "--format", "json"]
    if permissions == "full-auto":
        cmd.append("--approve-all")
    if model:
        cmd.extend(["--model", model])
    cmd.append(agent)
    if session_name:
        cmd.extend(["-s", session_name])
    else:
        cmd.append("exec")
    cmd.append(prompt)
    return cmd


def build_acpx_env() -> dict[str, str]:
    return dict(os.environ)


def ensure_acpx_session(
    *,
    workspace: Path,
    executable: str,
    acpx_package: str,
    agent: str,
    session_name: str,
) -> None:
    result = execute_tool_request(
        ToolExecutionRequest(
            tool_name="acpx.session.ensure",
            arguments={
                "workspace": str(workspace),
                "executable": executable,
                "acpx_package": acpx_package,
                "agent": agent,
                "session_name": session_name,
            },
            allowed_permissions={ToolPermissionClass.SESSION_ADMIN},
            telemetry_root=_tool_runtime_root(workspace),
        ),
        registry=_TOOL_REGISTRY,
    )
    output = result.output if isinstance(result.output, dict) else {}
    if (not result.success) or int(output.get("returncode", 1)) != 0:
        stderr = str(output.get("stderr", result.error)).strip()
        raise RuntimeError(
            "ACPX session ensure failed "
            f"(rc={output.get('returncode', 'unknown')}, "
            f"agent={agent}, session={session_name}): {stderr}"
        )


def cancel_acpx_session(
    *,
    workspace: Path,
    executable: str,
    acpx_package: str,
    agent: str,
    session_name: str,
) -> None:
    result = execute_tool_request(
        ToolExecutionRequest(
            tool_name="acpx.session.cancel",
            arguments={
                "workspace": str(workspace),
                "executable": executable,
                "acpx_package": acpx_package,
                "agent": agent,
                "session_name": session_name,
            },
            allowed_permissions={ToolPermissionClass.SESSION_ADMIN},
            telemetry_root=_tool_runtime_root(workspace),
        ),
        registry=_TOOL_REGISTRY,
    )
    output = result.output if isinstance(result.output, dict) else {}
    if (not result.success) or int(output.get("returncode", 1)) != 0:
        stderr = str(output.get("stderr", result.error)).strip()
        raise RuntimeError(
            "ACPX session cancel failed "
            f"(rc={output.get('returncode', 'unknown')}, "
            f"agent={agent}, session={session_name}): {stderr}"
        )


def drain_stderr(process: subprocess.Popen[str], container: list[str]) -> None:
    assert process.stderr is not None
    for line in process.stderr:
        container.append(line)


def collect_stdout_events(
    process: subprocess.Popen[str],
    *,
    stdout_lines: list[str],
    raw_events: list[dict[str, Any]],
    event_logger: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    assert process.stdout is not None
    for line in process.stdout:
        stdout_lines.append(line)
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        raw_events.append(event)
        if event_logger is not None:
            event_logger(event)
