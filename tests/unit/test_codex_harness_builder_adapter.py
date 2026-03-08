from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from spec_orch.domain.models import Issue
from spec_orch.services.codex_harness_builder_adapter import (
    CodexHarnessBuilderAdapter,
    CodexHarnessTransportError,
)


def test_codex_harness_builder_adapter_runs_builder_turn_over_stdio(tmp_path: Path) -> None:
    request_log = tmp_path / "requests.jsonl"
    fake_server = tmp_path / "fake_codex_app_server.py"
    fake_server.write_text(
        "\n".join(
            [
                "import json",
                "import os",
                "import sys",
                f"request_log = {str(request_log)!r}",
                "for line in sys.stdin:",
                "    message = json.loads(line)",
                "    with open(request_log, 'a', encoding='utf-8') as handle:",
                "        handle.write(json.dumps(message) + '\\n')",
                "    method = message.get('method')",
                "    if method == 'initialize':",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': {'serverInfo': {'name': 'fake-codex', 'version': '0.1'}}}) + '\\n')",
                "        sys.stdout.flush()",
                "    elif method == 'thread/start':",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': {'thread': {'id': 'thread-123'}, 'cwd': os.getcwd(), 'approvalPolicy': 'never', 'sandbox': {'mode': 'workspace-write'}, 'model': 'codex-mini', 'modelProvider': 'openai'}}) + '\\n')",
                "        sys.stdout.flush()",
                "    elif method == 'turn/start':",
                "        turn_id = 'turn-456'",
                "        thread_id = message['params']['threadId']",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': {'turn': {'id': turn_id, 'status': 'in_progress'}}}) + '\\n')",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'method': 'item/agentMessage/delta', 'params': {'threadId': thread_id, 'turnId': turn_id, 'itemId': 'msg-1', 'delta': 'Implemented builder changes.'}}) + '\\n')",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'method': 'turn/plan/updated', 'params': {'threadId': thread_id, 'turnId': turn_id, 'items': [{'id': 'plan-1', 'text': 'Edit files'}, {'id': 'plan-2', 'text': 'Run tests'}]}}) + '\\n')",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'method': 'turn/completed', 'params': {'threadId': thread_id, 'turn': {'id': turn_id, 'status': 'completed'}}}) + '\\n')",
                "        sys.stdout.flush()",
                "        break",
            ]
        )
        + "\n"
    )

    events: list[dict] = []
    adapter = CodexHarnessBuilderAdapter(
        command=[sys.executable, str(fake_server)],
    )
    issue = Issue(
        issue_id="SPC-20",
        title="Run builder",
        summary="Execute Codex app-server in workspace.",
        builder_prompt="Implement the issue in this workspace.",
    )

    result = adapter.run(
        issue=issue,
        workspace=tmp_path,
        run_id="run-spc-20",
        event_logger=events.append,
    )

    assert result.succeeded is True
    assert result.command == [sys.executable, str(fake_server)]
    assert result.adapter == "codex_harness"
    assert result.agent == "codex"
    assert "Implemented builder changes." in result.stdout
    assert result.report_path.exists()
    report_data = json.loads(result.report_path.read_text())
    assert report_data["adapter"] == "codex_harness"
    assert report_data["agent"] == "codex"
    assert report_data["metadata"]["thread_id"] == "thread-123"
    assert report_data["metadata"]["turn_id"] == "turn-456"
    assert report_data["metadata"]["plan"] == ["Edit files", "Run tests"]
    requests = [json.loads(line) for line in request_log.read_text().splitlines()]
    assert [request["method"] for request in requests] == [
        "initialize",
        "thread/start",
        "turn/start",
    ]
    turn_start = requests[2]
    assert turn_start["params"]["input"] == [
        {
            "type": "text",
            "text": (
                "You are the SpecOrch builder for this issue workspace. "
                "Minimize workflow narration, tool-loading commentary, and process summaries. "
                "Move directly into implementation and verification. "
                "Only stop to explain when blocked, when requesting approval, or when reporting the final outcome.\n\n"
                "Issue builder prompt:\n"
                "Implement the issue in this workspace."
            ),
        }
    ]
    assert [event["event_type"] for event in events] == [
        "thread_started",
        "turn_started",
        "turn_completed",
    ]
    assert events[0]["data"]["thread_id"] == "thread-123"
    assert events[1]["data"]["turn_id"] == "turn-456"


def test_codex_harness_builder_adapter_handles_approval_requests_and_logs_events(
    tmp_path: Path,
) -> None:
    response_log = tmp_path / "responses.jsonl"
    fake_server = tmp_path / "fake_codex_approval_server.py"
    fake_server.write_text(
        "\n".join(
            [
                "import json",
                "import sys",
                f"response_log = {str(response_log)!r}",
                "for line in sys.stdin:",
                "    message = json.loads(line)",
                "    method = message.get('method')",
                "    if method == 'initialize':",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': {'serverInfo': {'name': 'fake-codex', 'version': '0.1'}}}) + '\\n')",
                "        sys.stdout.flush()",
                "    elif method == 'thread/start':",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': {'thread': {'id': 'thread-appr'}}}) + '\\n')",
                "        sys.stdout.flush()",
                "    elif method == 'turn/start':",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': {'turn': {'id': 'turn-appr', 'status': 'in_progress'}}}) + '\\n')",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'method': 'item/commandExecution/requestApproval', 'id': 'approve-1', 'params': {'threadId': 'thread-appr', 'turnId': 'turn-appr', 'itemId': 'cmd-1'}}) + '\\n')",
                "        sys.stdout.flush()",
                "    elif message.get('id') == 'approve-1':",
                "        with open(response_log, 'a', encoding='utf-8') as handle:",
                "            handle.write(json.dumps(message) + '\\n')",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'method': 'item/agentMessage/delta', 'params': {'threadId': 'thread-appr', 'turnId': 'turn-appr', 'itemId': 'msg-1', 'delta': 'approval ok'}}) + '\\n')",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'method': 'turn/completed', 'params': {'threadId': 'thread-appr', 'turn': {'id': 'turn-appr', 'status': 'completed'}}}) + '\\n')",
                "        sys.stdout.flush()",
                "        break",
            ]
        )
        + "\n"
    )

    events: list[dict] = []
    adapter = CodexHarnessBuilderAdapter(command=[sys.executable, str(fake_server)])
    issue = Issue(
        issue_id="SPC-22",
        title="Approval flow",
        summary="Accept approval requests during a Codex turn.",
        builder_prompt="Implement with approval.",
    )

    result = adapter.run(
        issue=issue,
        workspace=tmp_path,
        run_id="run-spc-22",
        event_logger=events.append,
    )

    assert result.succeeded is True
    assert "approval ok" in result.stdout
    responses = [json.loads(line) for line in response_log.read_text().splitlines()]
    assert responses == [
        {"jsonrpc": "2.0", "id": "approve-1", "result": {"decision": "accept"}}
    ]
    assert [event["event_type"] for event in events] == [
        "thread_started",
        "turn_started",
        "approval_requested",
        "approval_resolved",
        "turn_completed",
    ]
    assert events[2]["data"]["approval_type"] == "command"
    assert events[3]["data"]["decision"] == "accept"


def test_codex_harness_builder_adapter_keeps_turn_alive_while_progress_continues(
    tmp_path: Path,
) -> None:
    fake_server = tmp_path / "fake_codex_progress_server.py"
    fake_server.write_text(
        "\n".join(
            [
                "import json",
                "import sys",
                "import time",
                "for line in sys.stdin:",
                "    message = json.loads(line)",
                "    method = message.get('method')",
                "    if method == 'initialize':",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': {'serverInfo': {'name': 'fake-codex', 'version': '0.1'}}}) + '\\n')",
                "        sys.stdout.flush()",
                "    elif method == 'thread/start':",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': {'thread': {'id': 'thread-progress'}}}) + '\\n')",
                "        sys.stdout.flush()",
                "    elif method == 'turn/start':",
                "        thread_id = message['params']['threadId']",
                "        turn_id = 'turn-progress'",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': {'turn': {'id': turn_id, 'status': 'in_progress'}}}) + '\\n')",
                "        sys.stdout.flush()",
                "        time.sleep(0.06)",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'method': 'item/agentMessage/delta', 'params': {'threadId': thread_id, 'turnId': turn_id, 'itemId': 'msg-1', 'delta': 'still working'}}) + '\\n')",
                "        sys.stdout.flush()",
                "        time.sleep(0.06)",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'method': 'turn/plan/updated', 'params': {'threadId': thread_id, 'turnId': turn_id, 'items': [{'id': 'plan-1', 'text': 'Keep going'}]}}) + '\\n')",
                "        sys.stdout.flush()",
                "        time.sleep(0.06)",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'method': 'turn/completed', 'params': {'threadId': thread_id, 'turn': {'id': turn_id, 'status': 'completed'}}}) + '\\n')",
                "        sys.stdout.flush()",
                "        break",
            ]
        )
        + "\n"
    )

    adapter = CodexHarnessBuilderAdapter(
        command=[sys.executable, str(fake_server)],
        request_timeout_seconds=0.2,
        idle_timeout_seconds=0.1,
        stalled_timeout_seconds=0.25,
        absolute_timeout_seconds=1.0,
    )
    issue = Issue(
        issue_id="SPC-23",
        title="Progress flow",
        summary="Keep alive while the turn is still progressing.",
        builder_prompt="Implement with multiple progress updates.",
    )

    result = adapter.run(
        issue=issue,
        workspace=tmp_path,
        run_id="run-spc-23",
    )

    assert result.succeeded is True
    assert result.metadata["observation"]["timeout_reason"] is None
    assert result.metadata["observation"]["last_progress_kind"] == "turn_completed"
    state_data = json.loads((tmp_path / "telemetry" / "harness_state.json").read_text())
    assert state_data["status"] == "completed"
    assert state_data["last_progress_kind"] == "turn_completed"


def test_codex_harness_builder_adapter_writes_parsed_incoming_events_and_output_excerpts(
    tmp_path: Path,
) -> None:
    fake_server = tmp_path / "fake_codex_observation_server.py"
    fake_server.write_text(
        "\n".join(
            [
                "import json",
                "import sys",
                "for line in sys.stdin:",
                "    message = json.loads(line)",
                "    method = message.get('method')",
                "    if method == 'initialize':",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': {'serverInfo': {'name': 'fake-codex', 'version': '0.1'}}}) + '\\n')",
                "        sys.stdout.flush()",
                "    elif method == 'thread/start':",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': {'thread': {'id': 'thread-observe'}}}) + '\\n')",
                "        sys.stdout.flush()",
                "    elif method == 'turn/start':",
                "        thread_id = message['params']['threadId']",
                "        turn_id = 'turn-observe'",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': {'turn': {'id': turn_id, 'status': 'in_progress'}}}) + '\\n')",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'method': 'item/started', 'params': {'threadId': thread_id, 'turnId': turn_id, 'item': {'id': 'cmd-1', 'type': 'command_execution'}}}) + '\\n')",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'method': 'item/commandExecution/outputDelta', 'params': {'threadId': thread_id, 'turnId': turn_id, 'itemId': 'cmd-1', 'stream': 'stdout', 'delta': 'pytest output line'}}) + '\\n')",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'method': 'item/agentMessage/delta', 'params': {'threadId': thread_id, 'turnId': turn_id, 'itemId': 'msg-1', 'delta': 'Investigating the failing CLI command.'}}) + '\\n')",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'method': 'turn/completed', 'params': {'threadId': thread_id, 'turn': {'id': turn_id, 'status': 'completed'}}}) + '\\n')",
                "        sys.stdout.flush()",
                "        break",
            ]
        )
        + "\n"
    )

    adapter = CodexHarnessBuilderAdapter(command=[sys.executable, str(fake_server)])
    issue = Issue(
        issue_id="SPC-26",
        title="Parsed observation",
        summary="Capture parsed incoming messages and excerpts for debugging.",
        builder_prompt="Observe command output in detail.",
    )

    result = adapter.run(
        issue=issue,
        workspace=tmp_path,
        run_id="run-spc-26",
    )

    assert result.succeeded is True
    incoming_path = tmp_path / "telemetry" / "incoming_events.jsonl"
    incoming_events = [json.loads(line) for line in incoming_path.read_text().splitlines()]
    assert incoming_events
    assert incoming_events[0]["observed_at"]
    assert incoming_events[0]["kind"]
    assert any(event["method"] for event in incoming_events)
    assert any(event["excerpt"] for event in incoming_events)
    assert any(
        event["method"] == "item/commandExecution/outputDelta"
        and event["kind"] == "command_output_delta"
        and event["excerpt"] == "pytest output line"
        for event in incoming_events
    )
    assert any(
        event["method"] == "item/agentMessage/delta"
        and event["kind"] == "agent_message_delta"
        and event["excerpt"] == "Investigating the failing CLI command."
        for event in incoming_events
    )
    state_data = json.loads((tmp_path / "telemetry" / "harness_state.json").read_text())
    assert state_data["last_output_excerpt"] == "Investigating the failing CLI command."
    assert state_data["last_agent_excerpt"] == "Investigating the failing CLI command."
    assert state_data["last_command_output_excerpt"] == "pytest output line"


def test_codex_harness_builder_adapter_aggregates_agent_message_deltas_into_excerpt(
    tmp_path: Path,
) -> None:
    fake_server = tmp_path / "fake_codex_agent_message_server.py"
    fake_server.write_text(
        "\n".join(
            [
                "import json",
                "import sys",
                "for line in sys.stdin:",
                "    message = json.loads(line)",
                "    method = message.get('method')",
                "    if method == 'initialize':",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': {'serverInfo': {'name': 'fake-codex', 'version': '0.1'}}}) + '\\n')",
                "        sys.stdout.flush()",
                "    elif method == 'thread/start':",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': {'thread': {'id': 'thread-agent'}}}) + '\\n')",
                "        sys.stdout.flush()",
                "    elif method == 'turn/start':",
                "        thread_id = message['params']['threadId']",
                "        turn_id = 'turn-agent'",
                "        item_id = 'msg-aggregate'",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': {'turn': {'id': turn_id, 'status': 'in_progress'}}}) + '\\n')",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'method': 'item/agentMessage/delta', 'params': {'threadId': thread_id, 'turnId': turn_id, 'itemId': item_id, 'delta': 'Investigating'}}) + '\\n')",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'method': 'item/agentMessage/delta', 'params': {'threadId': thread_id, 'turnId': turn_id, 'itemId': item_id, 'delta': ' the failing'}}) + '\\n')",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'method': 'item/agentMessage/delta', 'params': {'threadId': thread_id, 'turnId': turn_id, 'itemId': item_id, 'delta': ' CLI command.'}}) + '\\n')",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'method': 'turn/completed', 'params': {'threadId': thread_id, 'turn': {'id': turn_id, 'status': 'completed'}}}) + '\\n')",
                "        sys.stdout.flush()",
                "        break",
            ]
        )
        + "\n"
    )

    adapter = CodexHarnessBuilderAdapter(command=[sys.executable, str(fake_server)])
    issue = Issue(
        issue_id="SPC-27",
        title="Aggregate agent message",
        summary="Capture a readable last agent excerpt instead of only the last delta token.",
        builder_prompt="Aggregate agent deltas into a readable excerpt.",
    )

    result = adapter.run(
        issue=issue,
        workspace=tmp_path,
        run_id="run-spc-27",
    )

    assert result.succeeded is True
    state_data = json.loads((tmp_path / "telemetry" / "harness_state.json").read_text())
    assert state_data["last_agent_excerpt"] == "Investigating the failing CLI command."
    assert state_data["last_output_excerpt"] == "Investigating the failing CLI command."


def test_codex_harness_builder_adapter_times_out_when_turn_goes_idle(tmp_path: Path) -> None:
    fake_server = tmp_path / "fake_codex_idle_server.py"
    fake_server.write_text(
        "\n".join(
            [
                "import json",
                "import sys",
                "import time",
                "for line in sys.stdin:",
                "    message = json.loads(line)",
                "    method = message.get('method')",
                "    if method == 'initialize':",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': {'serverInfo': {'name': 'fake-codex', 'version': '0.1'}}}) + '\\n')",
                "        sys.stdout.flush()",
                "    elif method == 'thread/start':",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': {'thread': {'id': 'thread-idle'}}}) + '\\n')",
                "        sys.stdout.flush()",
                "    elif method == 'turn/start':",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': {'turn': {'id': 'turn-idle', 'status': 'in_progress'}}}) + '\\n')",
                "        sys.stdout.flush()",
                "        time.sleep(0.3)",
                "        break",
            ]
        )
        + "\n"
    )

    events: list[dict] = []
    adapter = CodexHarnessBuilderAdapter(
        command=[sys.executable, str(fake_server)],
        request_timeout_seconds=0.2,
        idle_timeout_seconds=0.1,
        stalled_timeout_seconds=0.5,
        absolute_timeout_seconds=1.0,
    )
    issue = Issue(
        issue_id="SPC-24",
        title="Idle timeout",
        summary="Fail when the turn goes silent.",
        builder_prompt="Wait forever without output.",
    )

    with pytest.raises(CodexHarnessTransportError, match="idle timeout"):
        adapter.run(
            issue=issue,
            workspace=tmp_path,
            run_id="run-spc-24",
            event_logger=events.append,
        )

    assert any(
        event["event_type"] == "turn_timeout"
        and event["data"]["reason"] == "idle_timeout"
        for event in events
    )
    state_data = json.loads((tmp_path / "telemetry" / "harness_state.json").read_text())
    assert state_data["status"] == "timed_out"
    assert state_data["timeout_reason"] == "idle_timeout"


def test_codex_harness_builder_adapter_times_out_when_turn_has_no_progress(
    tmp_path: Path,
) -> None:
    fake_server = tmp_path / "fake_codex_stalled_server.py"
    fake_server.write_text(
        "\n".join(
            [
                "import json",
                "import sys",
                "import time",
                "for line in sys.stdin:",
                "    message = json.loads(line)",
                "    method = message.get('method')",
                "    if method == 'initialize':",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': {'serverInfo': {'name': 'fake-codex', 'version': '0.1'}}}) + '\\n')",
                "        sys.stdout.flush()",
                "    elif method == 'thread/start':",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': {'thread': {'id': 'thread-stalled'}}}) + '\\n')",
                "        sys.stdout.flush()",
                "    elif method == 'turn/start':",
                "        thread_id = message['params']['threadId']",
                "        turn_id = 'turn-stalled'",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': {'turn': {'id': turn_id, 'status': 'in_progress'}}}) + '\\n')",
                "        sys.stdout.flush()",
                "        for _ in range(5):",
                "            time.sleep(0.04)",
                "            sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'method': 'thread/tokenUsage/updated', 'params': {'threadId': thread_id, 'turnId': turn_id, 'tokenUsage': {'total': {'totalTokens': 1}}}}) + '\\n')",
                "            sys.stdout.flush()",
                "        time.sleep(0.2)",
                "        break",
            ]
        )
        + "\n"
    )

    events: list[dict] = []
    adapter = CodexHarnessBuilderAdapter(
        command=[sys.executable, str(fake_server)],
        request_timeout_seconds=0.2,
        idle_timeout_seconds=0.2,
        stalled_timeout_seconds=0.12,
        absolute_timeout_seconds=1.0,
    )
    issue = Issue(
        issue_id="SPC-25",
        title="Stalled timeout",
        summary="Fail when protocol noise continues without progress.",
        builder_prompt="Only heartbeat, no progress.",
    )

    with pytest.raises(CodexHarnessTransportError, match="stalled timeout"):
        adapter.run(
            issue=issue,
            workspace=tmp_path,
            run_id="run-spc-25",
            event_logger=events.append,
        )

    assert any(
        event["event_type"] == "turn_timeout"
        and event["data"]["reason"] == "stalled_timeout"
        for event in events
    )
    state_data = json.loads((tmp_path / "telemetry" / "harness_state.json").read_text())
    assert state_data["status"] == "timed_out"
    assert state_data["timeout_reason"] == "stalled_timeout"
