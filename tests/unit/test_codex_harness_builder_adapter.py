from __future__ import annotations

import json
import sys
from pathlib import Path

from spec_orch.domain.models import Issue
from spec_orch.services.codex_harness_builder_adapter import CodexHarnessBuilderAdapter


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
