from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from spec_orch.runtime_chain.store import read_chain_events
from spec_orch.services.workers.acpx_worker_handle import AcpxWorkerHandle
from spec_orch.services.workers.acpx_worker_handle_factory import AcpxWorkerHandleFactory


class FakeProcess:
    def __init__(
        self,
        *,
        stdout_lines: list[str] | None = None,
        stderr_lines: list[str] | None = None,
        poll_values: list[int | None] | None = None,
        final_returncode: int = 0,
    ) -> None:
        self.stdout = iter(stdout_lines or [])
        self.stderr = iter(stderr_lines or [])
        self._poll_values = list(poll_values or [])
        self.returncode: int | None = None
        self._final_returncode = final_returncode
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        if self.returncode is not None:
            return self.returncode
        if self._poll_values:
            value = self._poll_values.pop(0)
            if value is not None:
                self.returncode = value
            return value
        return None

    def wait(self, timeout: float | None = None) -> int:
        if self.returncode is None:
            if timeout is not None:
                raise subprocess.TimeoutExpired("fake", timeout)
            self.returncode = self._final_returncode
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        if self.returncode is None:
            self.returncode = -15

    def kill(self) -> None:
        self.killed = True
        if self.returncode is None:
            self.returncode = -9


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
    mock_process.poll.return_value = 0
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
    assert report["terminal_reason"] == "process_exit_success"
    assert report["retry_count"] == 0
    assert report["session_reused"] is False
    incoming_path = tmp_path / "telemetry" / "incoming_events.jsonl"
    assert incoming_path.exists()
    assert (tmp_path / "telemetry" / "worker_turn.json").exists()
    assert (tmp_path / "telemetry" / "worker_health.json").exists()
    raw_lines = incoming_path.read_text(encoding="utf-8").splitlines()
    assert len(raw_lines) == 2
    assert json.loads(raw_lines[0])["type"] == "text"
    assert json.loads(raw_lines[1])["type"] == "result"


@patch("spec_orch.services.workers.acpx_worker_handle.ensure_acpx_session")
@patch("spec_orch.services.workers.acpx_worker_handle.subprocess.Popen")
def test_acpx_worker_handle_links_worker_turn_to_runtime_chain(
    mock_popen: MagicMock,
    mock_ensure_session: MagicMock,
    tmp_path: Path,
) -> None:
    mock_process = MagicMock()
    mock_process.stdout = iter(['{"type": "result", "params": {"text": "done"}}\n'])
    mock_process.stderr = iter([])
    mock_process.returncode = 0
    mock_process.wait.return_value = 0
    mock_process.poll.return_value = 0
    mock_popen.return_value = mock_process

    handle = AcpxWorkerHandle(
        session_id="mission-m1-pkt1",
        agent="codex",
        executable="npx",
        acpx_package="acpx",
    )

    chain_root = tmp_path / "operator" / "runtime_chain"
    result = handle.send(
        prompt="Continue fixing the migration issue.",
        workspace=tmp_path,
        chain_root=chain_root,
        chain_id="chain-mission-1",
        span_id="span-pkt-1-worker",
        parent_span_id="span-pkt-1",
    )

    assert result.succeeded is True
    report = json.loads((tmp_path / "builder_report.json").read_text(encoding="utf-8"))
    assert report["chain_id"] == "chain-mission-1"
    assert report["span_id"] == "span-pkt-1-worker"
    assert report["parent_span_id"] == "span-pkt-1"
    worker_turn = json.loads(
        (tmp_path / "telemetry" / "worker_turn.json").read_text(encoding="utf-8")
    )
    assert worker_turn["chain_id"] == "chain-mission-1"
    assert worker_turn["span_id"] == "span-pkt-1-worker"
    assert worker_turn["parent_span_id"] == "span-pkt-1"
    chain_events = read_chain_events(chain_root)
    assert [event.phase.value for event in chain_events] == ["started", "completed"]
    assert all(event.subject_kind.value == "packet" for event in chain_events)
    assert all(event.subject_id == "mission-m1-pkt1" for event in chain_events)
    mock_ensure_session.assert_called_once()


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
    mock_process.poll.return_value = 0
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
    mock_process.poll.return_value = 0
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
    factory = AcpxWorkerHandleFactory(
        agent="codex",
        model="gpt-5",
        startup_timeout_seconds=12.0,
        idle_progress_timeout_seconds=34.0,
        completion_quiet_period_seconds=5.0,
        max_retries=2,
    )

    handle1 = factory.create(session_id="mission-m1-pkt1", workspace=tmp_path)
    handle2 = factory.create(session_id="mission-m1-pkt1", workspace=tmp_path)

    assert handle1 is handle2
    assert factory.get("mission-m1-pkt1") is handle1
    assert handle1.startup_timeout_seconds == 12.0
    assert handle1.idle_progress_timeout_seconds == 34.0
    assert handle1.completion_quiet_period_seconds == 5.0
    assert handle1.max_retries == 2


@patch("spec_orch.services.workers.acpx_worker_handle.ensure_acpx_session")
@patch("spec_orch.services.workers.acpx_worker_handle.subprocess.Popen")
def test_acpx_worker_handle_send_delegates_builder_report_write(
    mock_popen: MagicMock,
    mock_ensure_session: MagicMock,
    tmp_path: Path,
) -> None:
    mock_process = MagicMock()
    mock_process.stdout = iter(['{"type": "result", "params": {"text": "done"}}\n'])
    mock_process.stderr = iter([])
    mock_process.returncode = 0
    mock_process.wait.return_value = 0
    mock_process.poll.return_value = 0
    mock_popen.return_value = mock_process

    delegated: dict[str, object] = {}

    def fake_write_worker_execution_payloads(
        worker_dir: Path,
        *,
        builder_report: dict,
    ) -> dict[str, Path]:
        delegated["worker_dir"] = worker_dir
        delegated["builder_report"] = builder_report
        target = worker_dir / "builder_report.json"
        target.write_text(json.dumps(builder_report), encoding="utf-8")
        return {"builder_report": target}

    handle = AcpxWorkerHandle(
        session_id="mission-m1-pkt1",
        agent="codex",
        executable="npx",
        acpx_package="acpx",
    )

    with patch(
        "spec_orch.services.workers.acpx_worker_handle.write_worker_execution_payloads",
        fake_write_worker_execution_payloads,
    ):
        result = handle.send(prompt="Continue.", workspace=tmp_path)

    assert result.succeeded is True
    mock_ensure_session.assert_called_once()
    assert delegated["worker_dir"] == tmp_path
    assert isinstance(delegated["builder_report"], dict)
    assert (
        json.loads((tmp_path / "builder_report.json").read_text(encoding="utf-8"))["session_name"]
        == "mission-m1-pkt1"
    )


@patch("spec_orch.services.workers.acpx_worker_handle.cancel_acpx_session")
@patch("spec_orch.services.workers.acpx_worker_handle.ensure_acpx_session")
@patch("spec_orch.services.workers.acpx_worker_handle.subprocess.Popen")
def test_acpx_worker_handle_retries_once_after_startup_reconnect_stall(
    mock_popen: MagicMock,
    mock_ensure_session: MagicMock,
    mock_cancel_session: MagicMock,
    tmp_path: Path,
) -> None:
    stalled = FakeProcess(
        stdout_lines=[],
        stderr_lines=["[acpx] agent needs reconnect\n"],
        poll_values=[None, None, None, None, None],
    )
    recovered = FakeProcess(
        stdout_lines=['{"type": "result", "params": {"text": "done"}}\n'],
        stderr_lines=[],
        poll_values=[0],
        final_returncode=0,
    )
    mock_popen.side_effect = [stalled, recovered]

    handle = AcpxWorkerHandle(
        session_id="mission-m1-pkt1",
        agent="codex",
        executable="npx",
        acpx_package="acpx",
        startup_timeout_seconds=0.01,
        idle_progress_timeout_seconds=1.0,
        completion_quiet_period_seconds=0.0,
        absolute_timeout_seconds=5.0,
        max_retries=1,
    )

    result = handle.send(prompt="Continue.", workspace=tmp_path)

    assert result.succeeded is True
    assert mock_popen.call_count == 2
    assert mock_ensure_session.call_count == 2
    mock_cancel_session.assert_called_once()
    report = json.loads((tmp_path / "builder_report.json").read_text(encoding="utf-8"))
    assert report["retry_count"] == 1
    assert report["session_recycled"] is True
    assert report["terminal_reason"] == "process_exit_success"
    assert report["session_name"].endswith("-retry-1")


@patch("spec_orch.services.workers.acpx_worker_handle.cancel_acpx_session")
@patch("spec_orch.services.workers.acpx_worker_handle.ensure_acpx_session")
@patch("spec_orch.services.workers.acpx_worker_handle.subprocess.Popen")
def test_acpx_worker_handle_does_not_retry_after_progress_then_idle_timeout(
    mock_popen: MagicMock,
    mock_ensure_session: MagicMock,
    mock_cancel_session: MagicMock,
    tmp_path: Path,
) -> None:
    stuck = FakeProcess(
        stdout_lines=[
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "method": "session/update",
                    "params": {
                        "update": {
                            "sessionUpdate": "tool_call_update",
                            "title": "write",
                            "status": "completed",
                            "rawInput": {"filePath": "src/contracts/mission_types.ts"},
                        }
                    },
                }
            )
            + "\n"
        ],
        stderr_lines=[],
        poll_values=[None, None, None, None, None],
    )
    mock_popen.return_value = stuck

    handle = AcpxWorkerHandle(
        session_id="mission-m1-pkt1",
        agent="codex",
        executable="npx",
        acpx_package="acpx",
        startup_timeout_seconds=0.01,
        idle_progress_timeout_seconds=0.01,
        completion_quiet_period_seconds=10.0,
        absolute_timeout_seconds=5.0,
        max_retries=1,
    )

    result = handle.send(prompt="Continue.", workspace=tmp_path)

    assert result.succeeded is False
    assert mock_popen.call_count == 1
    mock_cancel_session.assert_called_once()
    report = json.loads((tmp_path / "builder_report.json").read_text(encoding="utf-8"))
    assert report["retry_count"] == 0
    assert report["session_recycled"] is False
    assert report["terminal_reason"] == "idle_timeout"
    assert report["files_changed"] == ["src/contracts/mission_types.ts"]


@patch("spec_orch.services.workers.acpx_worker_handle.ensure_acpx_session")
@patch("spec_orch.services.workers.acpx_worker_handle.subprocess.Popen")
def test_acpx_worker_handle_completes_on_explicit_result_event_without_process_exit(
    mock_popen: MagicMock,
    mock_ensure_session: MagicMock,
    tmp_path: Path,
) -> None:
    process = FakeProcess(
        stdout_lines=['{"type": "result", "params": {"text": "done"}}\n'],
        stderr_lines=[],
        poll_values=[None, None, None, None, None],
    )
    mock_popen.return_value = process

    handle = AcpxWorkerHandle(
        session_id="mission-m1-pkt1",
        agent="codex",
        executable="npx",
        acpx_package="acpx",
        startup_timeout_seconds=0.01,
        idle_progress_timeout_seconds=1.0,
        completion_quiet_period_seconds=0.0,
        absolute_timeout_seconds=5.0,
        max_retries=0,
    )

    result = handle.send(prompt="Continue.", workspace=tmp_path)

    assert result.succeeded is True
    assert process.terminated is True
    report = json.loads((tmp_path / "builder_report.json").read_text(encoding="utf-8"))
    assert report["terminal_reason"] == "event_completed"
