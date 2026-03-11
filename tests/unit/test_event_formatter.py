from spec_orch.services.event_formatter import EventFormatter


def test_format_command_started() -> None:
    fmt = EventFormatter(color=False)
    event: dict = {
        "type": "item.started",
        "item": {"type": "command_execution", "command": "bash -lc 'ls'"},
        "timestamp": "2026-03-10T14:32:08+00:00",
    }
    line = fmt.format_plain(event)
    assert line is not None
    assert "COMMAND" in line
    assert "bash -lc 'ls'" in line


def test_format_command_completed_exit_zero() -> None:
    fmt = EventFormatter(color=False)
    event: dict = {
        "type": "item.completed",
        "item": {
            "type": "command_execution",
            "command": "ruff check",
            "aggregated_output": "line1\nline2\nline3",
            "exit_code": 0,
        },
        "timestamp": "2026-03-10T14:32:09+00:00",
    }
    line = fmt.format_plain(event)
    assert line is not None
    assert "OUTPUT" in line
    assert "exit 0" in line
    assert "3 lines" in line


def test_format_command_completed_exit_nonzero() -> None:
    fmt = EventFormatter(color=False)
    event: dict = {
        "type": "item.completed",
        "item": {
            "type": "command_execution",
            "command": "pytest",
            "aggregated_output": "FAILED",
            "exit_code": 1,
        },
        "timestamp": "2026-03-10T14:32:18+00:00",
    }
    line = fmt.format_plain(event)
    assert line is not None
    assert "exit 1" in line


def test_format_agent_message() -> None:
    fmt = EventFormatter(color=False)
    event: dict = {
        "type": "item.completed",
        "item": {"type": "agent_message", "text": "Hello world"},
        "timestamp": "2026-03-10T14:32:05+00:00",
    }
    line = fmt.format_plain(event)
    assert line is not None
    assert "MESSAGE" in line
    assert "Hello world" in line


def test_format_file_change() -> None:
    fmt = EventFormatter(color=False)
    event: dict = {
        "type": "item.completed",
        "item": {"type": "file_change", "file": "src/foo.py"},
        "timestamp": "2026-03-10T14:32:12+00:00",
    }
    line = fmt.format_plain(event)
    assert line is not None
    assert "FILE" in line
    assert "src/foo.py" in line


def test_format_reasoning() -> None:
    fmt = EventFormatter(color=False)
    event: dict = {
        "type": "item.completed",
        "item": {"type": "reasoning", "text": "I need to check the test file"},
        "timestamp": "2026-03-10T14:32:06+00:00",
    }
    line = fmt.format_plain(event)
    assert line is not None
    assert "REASON" in line


def test_format_turn_completed_with_usage() -> None:
    fmt = EventFormatter(color=False)
    event: dict = {
        "type": "turn.completed",
        "usage": {"input_tokens": 1234, "output_tokens": 567},
        "timestamp": "2026-03-10T14:32:20+00:00",
    }
    line = fmt.format_plain(event)
    assert line is not None
    assert "TURN" in line
    assert "1,234 in" in line
    assert "567 out" in line


def test_format_turn_failed() -> None:
    fmt = EventFormatter(color=False)
    event: dict = {
        "type": "turn.failed",
        "timestamp": "2026-03-10T14:32:20+00:00",
    }
    line = fmt.format_plain(event)
    assert line is not None
    assert "TURN" in line
    assert "Failed" in line


def test_format_plan_updated() -> None:
    fmt = EventFormatter(color=False)
    event: dict = {
        "type": "turn.plan.updated",
        "items": ["step 1", "step 2"],
        "timestamp": "2026-03-10T14:32:10+00:00",
    }
    line = fmt.format_plain(event)
    assert line is not None
    assert "PLAN" in line
    assert "2 items" in line


def test_format_orchestrator_builder_started() -> None:
    fmt = EventFormatter(color=False)
    event: dict = {
        "event_type": "builder_started",
        "component": "builder",
        "message": "Started builder adapter.",
        "data": {},
        "timestamp": "2026-03-10T14:32:01+00:00",
    }
    line = fmt.format_plain(event)
    assert line is not None
    assert "BUILDER" in line
    assert "Started" in line


def test_format_orchestrator_verification_step() -> None:
    fmt = EventFormatter(color=False)
    event: dict = {
        "event_type": "verification_step_completed",
        "component": "verification",
        "message": "lint step",
        "data": {"step": "lint", "exit_code": 0},
        "timestamp": "2026-03-10T14:32:25+00:00",
    }
    line = fmt.format_plain(event)
    assert line is not None
    assert "VERIFY" in line
    assert "lint" in line
    assert "passed" in line


def test_format_orchestrator_gate_mergeable() -> None:
    fmt = EventFormatter(color=False)
    event: dict = {
        "event_type": "gate_evaluated",
        "component": "gate",
        "message": "Evaluated gate verdict.",
        "data": {"mergeable": True, "failed_conditions": []},
        "timestamp": "2026-03-10T14:32:36+00:00",
    }
    line = fmt.format_plain(event)
    assert line is not None
    assert "GATE" in line
    assert "MERGEABLE" in line


def test_format_orchestrator_gate_blocked() -> None:
    fmt = EventFormatter(color=False)
    event: dict = {
        "event_type": "gate_evaluated",
        "component": "gate",
        "message": "Evaluated gate verdict.",
        "data": {"mergeable": False, "failed_conditions": ["verification", "review"]},
        "timestamp": "2026-03-10T14:32:36+00:00",
    }
    line = fmt.format_plain(event)
    assert line is not None
    assert "GATE" in line
    assert "BLOCKED" in line
    assert "verification" in line


def test_colored_output_contains_ansi() -> None:
    fmt = EventFormatter(color=True)
    event: dict = {
        "type": "turn.failed",
        "timestamp": "2026-03-10T14:32:20+00:00",
    }
    line = fmt.format(event)
    assert line is not None
    assert "\033[" in line


def test_verbose_mode_shows_full_output() -> None:
    output = "\n".join(f"line {i}" for i in range(20))
    fmt = EventFormatter(color=False, verbose=True)
    event: dict = {
        "type": "item.completed",
        "item": {
            "type": "command_execution",
            "command": "cat big.txt",
            "aggregated_output": output,
            "exit_code": 0,
        },
        "timestamp": "2026-03-10T14:32:09+00:00",
    }
    line = fmt.format_plain(event)
    assert line is not None
    assert "line 19" in line


def test_default_mode_truncates_output() -> None:
    output = "\n".join(f"line {i}" for i in range(20))
    fmt = EventFormatter(color=False, verbose=False)
    event: dict = {
        "type": "item.completed",
        "item": {
            "type": "command_execution",
            "command": "cat big.txt",
            "aggregated_output": output,
            "exit_code": 0,
        },
        "timestamp": "2026-03-10T14:32:09+00:00",
    }
    line = fmt.format_plain(event)
    assert line is not None
    assert "more lines" in line
    assert "line 19" not in line


def test_skips_unknown_item_started() -> None:
    fmt = EventFormatter(color=False)
    event: dict = {
        "type": "item.started",
        "item": {"type": "web_search"},
        "timestamp": "2026-03-10T14:32:08+00:00",
    }
    line = fmt.format_plain(event)
    assert line is None
