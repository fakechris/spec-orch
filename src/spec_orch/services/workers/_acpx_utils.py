from __future__ import annotations

import json
import logging
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


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
    cmd = [
        executable,
        "-y",
        acpx_package,
        agent,
        "sessions",
        "ensure",
        "--name",
        session_name,
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


def cancel_acpx_session(
    *,
    workspace: Path,
    executable: str,
    acpx_package: str,
    agent: str,
    session_name: str,
) -> None:
    cmd = [executable, "-y", acpx_package, agent, "cancel", "-s", session_name]
    subprocess.run(
        cmd,
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
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
