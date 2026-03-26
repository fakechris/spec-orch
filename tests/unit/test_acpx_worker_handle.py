from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from spec_orch.services.workers.acpx_worker_handle import AcpxWorkerHandle
from spec_orch.services.workers.acpx_worker_handle_factory import AcpxWorkerHandleFactory


@patch("spec_orch.services.workers.acpx_worker_handle.ensure_acpx_session")
@patch("spec_orch.services.workers.acpx_worker_handle.subprocess.Popen")
def test_acpx_worker_handle_send_uses_session_and_writes_report(
    mock_popen: MagicMock,
    mock_ensure_session: MagicMock,
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
    mock_ensure_session.assert_called_once()
    send_cmd = mock_popen.call_args[0][0]
    assert "-s" in send_cmd
    assert "mission-m1-pkt1" in send_cmd
    assert "exec" not in send_cmd
    report = json.loads((tmp_path / "builder_report.json").read_text(encoding="utf-8"))
    assert report["session_name"] == "mission-m1-pkt1"
    incoming_path = tmp_path / "telemetry" / "incoming_events.jsonl"
    assert incoming_path.exists()
    raw_lines = incoming_path.read_text(encoding="utf-8").splitlines()
    assert len(raw_lines) == 2
    assert json.loads(raw_lines[0])["type"] == "text"
    assert json.loads(raw_lines[1])["type"] == "result"


@patch("spec_orch.services.workers.acpx_worker_handle.ensure_acpx_session")
@patch("spec_orch.services.workers.acpx_worker_handle.subprocess.Popen")
def test_acpx_worker_handle_appends_incoming_events_across_sends(
    mock_popen: MagicMock,
    mock_ensure_session: MagicMock,
    tmp_path: Path,
) -> None:
    mock_process = MagicMock()
    mock_process.stdout = iter(['{"type": "result", "params": {"text": "done"}}\n'])
    mock_process.stderr = iter([])
    mock_process.returncode = 0
    mock_process.wait.return_value = 0
    mock_popen.return_value = mock_process

    telemetry_dir = tmp_path / "telemetry"
    telemetry_dir.mkdir(parents=True)
    incoming_path = telemetry_dir / "incoming_events.jsonl"
    incoming_path.write_text('{"type":"existing"}\n', encoding="utf-8")

    handle = AcpxWorkerHandle(
        session_id="mission-m1-pkt1",
        agent="codex",
        executable="npx",
        acpx_package="acpx",
    )

    result = handle.send(prompt="Continue.", workspace=tmp_path)

    assert result.succeeded is True
    mock_ensure_session.assert_called_once()
    raw_lines = incoming_path.read_text(encoding="utf-8").splitlines()
    assert len(raw_lines) == 2
    assert json.loads(raw_lines[0])["type"] == "existing"
    assert json.loads(raw_lines[1])["type"] == "result"


@patch("spec_orch.services.workers.acpx_worker_handle.ensure_acpx_session")
@patch("spec_orch.services.workers.acpx_worker_handle.subprocess.Popen")
def test_acpx_worker_handle_continues_when_incoming_events_file_cannot_open(
    mock_popen: MagicMock,
    mock_ensure_session: MagicMock,
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

    incoming_path = tmp_path / "telemetry" / "incoming_events.jsonl"
    event_types: list[str] = []
    original_open = Path.open

    def fake_open(self: Path, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self == incoming_path and args and args[0] == "a":
            raise OSError("disk full")
        return original_open(self, *args, **kwargs)

    with patch.object(Path, "open", fake_open):
        result = handle.send(
            prompt="Continue.",
            workspace=tmp_path,
            event_logger=lambda event: event_types.append(str(event.get("type"))),
        )

    assert result.succeeded is True
    mock_ensure_session.assert_called_once()
    assert event_types == ["text", "result"]
    assert (
        json.loads((tmp_path / "builder_report.json").read_text(encoding="utf-8"))["event_count"]
        == 2
    )


@patch("spec_orch.services.workers.acpx_worker_handle.cancel_acpx_session")
def test_acpx_worker_handle_cancel_calls_acpx_cancel(
    mock_cancel_session: MagicMock,
    tmp_path: Path,
) -> None:
    handle = AcpxWorkerHandle(session_id="mission-m1-pkt1", agent="codex")
    handle._session_ready = True

    handle.cancel(tmp_path)

    mock_cancel_session.assert_called_once()
    assert handle._session_ready is False


def test_acpx_worker_handle_factory_reuses_existing_handles(tmp_path: Path) -> None:
    factory = AcpxWorkerHandleFactory(agent="codex", model="gpt-5")

    handle1 = factory.create(session_id="mission-m1-pkt1", workspace=tmp_path)
    handle2 = factory.create(session_id="mission-m1-pkt1", workspace=tmp_path)

    assert handle1 is handle2
    assert factory.get("mission-m1-pkt1") is handle1
