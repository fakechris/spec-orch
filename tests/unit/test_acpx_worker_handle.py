from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from spec_orch.services.workers.acpx_worker_handle import AcpxWorkerHandle
from spec_orch.services.workers.acpx_worker_handle_factory import AcpxWorkerHandleFactory


@patch("spec_orch.services.workers.acpx_worker_handle.subprocess.run")
@patch("spec_orch.services.workers.acpx_worker_handle.subprocess.Popen")
def test_acpx_worker_handle_send_uses_session_and_writes_report(
    mock_popen: MagicMock,
    mock_run: MagicMock,
    tmp_path: Path,
) -> None:
    mock_process = MagicMock()
    mock_process.stdout = iter(
        [
            '{"type": "text", "params": {"text": "working"}}\n',
            '{"type": "result", "params": {"text": "done"}}\n',
        ]
    )
    mock_process.stderr = iter([])
    mock_process.returncode = 0
    mock_process.wait.return_value = 0
    mock_popen.return_value = mock_process

    handle = AcpxWorkerHandle(
        session_id="mission-m1-pkt1",
        agent="codex",
        executable="npx",
        acpx_package="acpx",
    )

    result = handle.send(prompt="Continue fixing the migration issue.", workspace=tmp_path)

    assert result.succeeded is True
    ensure_cmd = mock_run.call_args[0][0]
    assert "sessions" in ensure_cmd
    assert "ensure" in ensure_cmd
    send_cmd = mock_popen.call_args[0][0]
    assert "-s" in send_cmd
    assert "mission-m1-pkt1" in send_cmd
    assert "exec" not in send_cmd
    report = json.loads((tmp_path / "builder_report.json").read_text(encoding="utf-8"))
    assert report["session_name"] == "mission-m1-pkt1"


@patch("spec_orch.services.workers.acpx_worker_handle.subprocess.run")
def test_acpx_worker_handle_cancel_calls_acpx_cancel(mock_run: MagicMock, tmp_path: Path) -> None:
    handle = AcpxWorkerHandle(session_id="mission-m1-pkt1", agent="codex")

    handle.cancel(tmp_path)

    cmd = mock_run.call_args[0][0]
    assert "cancel" in cmd
    assert "-s" in cmd
    assert "mission-m1-pkt1" in cmd


def test_acpx_worker_handle_factory_reuses_existing_handles(tmp_path: Path) -> None:
    factory = AcpxWorkerHandleFactory(agent="codex", model="gpt-5")

    handle1 = factory.create(session_id="mission-m1-pkt1", workspace=tmp_path)
    handle2 = factory.create(session_id="mission-m1-pkt1", workspace=tmp_path)

    assert handle1 is handle2
    assert factory.get("mission-m1-pkt1") is handle1
