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

    adapter = CodexHarnessBuilderAdapter(
        command=[sys.executable, str(fake_server)],
    )
    issue = Issue(
        issue_id="SPC-20",
        title="Run builder",
        summary="Execute Codex app-server in workspace.",
        builder_prompt="Implement the issue in this workspace.",
    )

    result = adapter.run(issue=issue, workspace=tmp_path)

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

