import io

from spec_orch.services.activity_logger import ActivityLogger


def test_activity_logger_writes_to_file(tmp_path) -> None:
    log_path = tmp_path / "telemetry" / "activity.log"
    logger = ActivityLogger(log_path)

    logger.log(
        {
            "event_type": "builder_started",
            "component": "builder",
            "message": "Started builder adapter.",
            "data": {},
            "timestamp": "2026-03-10T14:32:01+00:00",
        }
    )
    logger.close()

    content = log_path.read_text()
    assert "BUILDER" in content
    assert "Started" in content


def test_activity_logger_writes_to_live_stream(tmp_path) -> None:
    log_path = tmp_path / "telemetry" / "activity.log"
    stream = io.StringIO()
    logger = ActivityLogger(log_path, live_stream=stream)

    logger.log(
        {
            "event_type": "gate_evaluated",
            "component": "gate",
            "message": "Evaluated gate verdict.",
            "data": {"mergeable": True, "failed_conditions": []},
            "timestamp": "2026-03-10T14:32:36+00:00",
        }
    )
    logger.close()

    file_content = log_path.read_text()
    stream_content = stream.getvalue()
    assert "GATE" in file_content
    assert "MERGEABLE" in file_content
    assert "GATE" in stream_content
    assert "MERGEABLE" in stream_content


def test_activity_logger_skips_unformattable_events(tmp_path) -> None:
    log_path = tmp_path / "telemetry" / "activity.log"
    logger = ActivityLogger(log_path)

    logger.log({"type": "item.started", "item": {"type": "web_search"}})
    logger.close()

    content = log_path.read_text() if log_path.exists() else ""
    assert content.strip() == ""


def test_activity_logger_context_manager(tmp_path) -> None:
    log_path = tmp_path / "telemetry" / "activity.log"
    with ActivityLogger(log_path) as logger:
        logger.log(
            {
                "event_type": "run_started",
                "component": "run_controller",
                "message": "Started issue run.",
                "data": {},
                "timestamp": "2026-03-10T14:32:00+00:00",
            }
        )

    content = log_path.read_text()
    assert "RUN" in content
    assert "Started" in content


def test_activity_log_path_static_method(tmp_path) -> None:
    result = ActivityLogger.activity_log_path(tmp_path)
    assert result == tmp_path / "telemetry" / "activity.log"


def test_multiple_events_appended(tmp_path) -> None:
    log_path = tmp_path / "telemetry" / "activity.log"
    logger = ActivityLogger(log_path)

    logger.log(
        {
            "event_type": "builder_started",
            "component": "builder",
            "message": "Started builder adapter.",
            "data": {},
            "timestamp": "2026-03-10T14:32:01+00:00",
        }
    )
    logger.log(
        {
            "event_type": "verification_step_completed",
            "component": "verification",
            "message": "lint",
            "data": {"step": "lint", "exit_code": 0},
            "timestamp": "2026-03-10T14:32:25+00:00",
        }
    )
    logger.close()

    lines = [ln for ln in log_path.read_text().splitlines() if ln.strip()]
    assert len(lines) == 2
    assert "BUILDER" in lines[0]
    assert "VERIFY" in lines[1]
