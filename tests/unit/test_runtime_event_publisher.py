from __future__ import annotations

from pathlib import Path

from spec_orch.services.run_event_logger import RunEventLogger
from spec_orch.services.telemetry_service import TelemetryService


class _FakeTelemetryService(TelemetryService):
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def log_event(self, **kwargs: object) -> Path:  # type: ignore[override]
        self.calls.append(kwargs)
        return Path("events.jsonl")


class _FakeActivityLogger:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def log(self, event: dict[str, object]) -> None:
        self.events.append(event)


class _FakePublisher:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def publish(self, **kwargs: object) -> None:
        self.calls.append(kwargs)


def test_run_event_logger_log_and_emit_delegates_to_runtime_event_publisher(tmp_path: Path) -> None:
    logger = RunEventLogger(telemetry_service=_FakeTelemetryService())
    fake_publisher = _FakePublisher()
    logger._event_publisher = fake_publisher  # type: ignore[attr-defined]

    logger.log_and_emit(
        workspace=tmp_path / "workspace",
        run_id="run-1",
        issue_id="SPC-1",
        component="verification",
        event_type="verification_completed",
        severity="warning",
        message="Completed verification steps.",
        data={"artifact": "report.json"},
    )

    assert fake_publisher.calls == [
        {
            "activity_logger": None,
            "workspace": tmp_path / "workspace",
            "run_id": "run-1",
            "issue_id": "SPC-1",
            "component": "verification",
            "event_type": "verification_completed",
            "severity": "warning",
            "message": "Completed verification steps.",
            "adapter": None,
            "agent": None,
            "data": {"artifact": "report.json"},
        }
    ]


def test_run_event_logger_event_callback_logs_to_telemetry_and_activity(tmp_path: Path) -> None:
    telemetry = _FakeTelemetryService()
    activity_logger = _FakeActivityLogger()
    logger = RunEventLogger(telemetry_service=telemetry)

    callback = logger.make_event_logger(
        workspace=tmp_path / "workspace",
        run_id="run-1",
        issue_id="SPC-1",
        activity_logger=activity_logger,  # type: ignore[arg-type]
    )

    callback(
        {
            "component": "builder",
            "event_type": "step_completed",
            "message": "Built packet",
            "adapter": "test-adapter",
            "agent": "builder-agent",
            "data": {"artifact": "task.spec.md"},
        }
    )

    assert telemetry.calls == [
        {
            "workspace": tmp_path / "workspace",
            "run_id": "run-1",
            "issue_id": "SPC-1",
            "component": "builder",
            "event_type": "step_completed",
            "severity": "info",
            "message": "Built packet",
            "adapter": "test-adapter",
            "agent": "builder-agent",
            "data": {"artifact": "task.spec.md"},
        }
    ]
    assert activity_logger.events == [{"artifact": "task.spec.md"}]


def test_run_event_logger_event_callback_preserves_top_level_payload_fields(tmp_path: Path) -> None:
    telemetry = _FakeTelemetryService()
    activity_logger = _FakeActivityLogger()
    logger = RunEventLogger(telemetry_service=telemetry)

    callback = logger.make_event_logger(
        workspace=tmp_path / "workspace",
        run_id="run-2",
        issue_id="SPC-2",
        activity_logger=activity_logger,  # type: ignore[arg-type]
    )

    callback(
        {
            "component": "builder",
            "method": "tool_call",
            "params": {"tool": "write"},
            "message": "Tool invoked",
            "data": {"artifact": "task.spec.md"},
        }
    )

    assert telemetry.calls[0]["data"] == {
        "artifact": "task.spec.md",
        "params": {"tool": "write"},
    }
    assert activity_logger.events == [
        {
            "artifact": "task.spec.md",
            "params": {"tool": "write"},
        }
    ]
