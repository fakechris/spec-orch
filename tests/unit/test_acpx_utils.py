from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from spec_orch.services.workers._acpx_utils import cancel_acpx_session, ensure_acpx_session


@patch("spec_orch.services.workers._acpx_utils.subprocess.run")
def test_ensure_acpx_session_uses_tool_runtime_and_writes_telemetry(
    mock_run: MagicMock,
    tmp_path: Path,
) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=["npx", "-y", "acpx"],
        returncode=0,
        stdout="ok",
        stderr="",
    )

    ensure_acpx_session(
        workspace=tmp_path,
        executable="npx",
        acpx_package="acpx",
        agent="opencode",
        session_name="session-1",
    )

    telemetry = tmp_path / "telemetry" / "tool_runtime" / "tool_lifecycle.jsonl"
    lines = telemetry.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["tool_name"] == "acpx.session.ensure"
    assert json.loads(lines[1])["phase"] == "completed"


@patch("spec_orch.services.workers._acpx_utils.subprocess.run")
def test_cancel_acpx_session_raises_runtime_error_on_failure(
    mock_run: MagicMock,
    tmp_path: Path,
) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=["npx", "-y", "acpx"],
        returncode=1,
        stdout="",
        stderr="failed",
    )

    try:
        cancel_acpx_session(
            workspace=tmp_path,
            executable="npx",
            acpx_package="acpx",
            agent="opencode",
            session_name="session-1",
        )
    except RuntimeError as exc:
        assert "session cancel failed" in str(exc).lower()
    else:
        raise AssertionError("expected RuntimeError")
