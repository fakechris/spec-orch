from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from spec_orch.services.run_controller import RunController


def test_run_controller_creates_git_worktree_for_issue(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)

    fixtures_dir = tmp_path / "fixtures" / "issues"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "SPC-1.json").write_text(
        json.dumps(
            {
                "issue_id": "SPC-1",
                "title": "Build workspace-aware runner",
                "summary": "Use a real git worktree for issue execution.",
                "verification_commands": {
                    "lint": ["{python}", "-c", "print('lint ok')"],
                    "typecheck": ["{python}", "-c", "print('type ok')"],
                    "test": ["{python}", "-c", "print('test ok')"],
                    "build": ["{python}", "-c", "print('build ok')"]
                }
            }
        )
    )
    _git(tmp_path, "add", ".")
    _git_commit(tmp_path, "add fixture")

    controller = RunController(repo_root=tmp_path)

    result = controller.run_issue("SPC-1")

    assert result.workspace == tmp_path / ".worktrees" / "SPC-1"
    assert result.workspace.exists()
    assert (result.workspace / ".git").exists()
    assert result.explain.exists()
    assert "mergeable=False" in result.explain.read_text()
    assert "blocked_by=review, human_acceptance" in result.explain.read_text()


def test_run_controller_runs_builder_when_prompt_is_present(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)

    fake_server = tmp_path / "fake_codex_app_server.py"
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
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': {'thread': {'id': 'thread-it'}, 'cwd': '.', 'approvalPolicy': 'never', 'sandbox': {'mode': 'workspace-write'}, 'model': 'codex-mini', 'modelProvider': 'openai'}}) + '\\n')",
                "        sys.stdout.flush()",
                "    elif method == 'turn/start':",
                "        prompt = message['params']['input'][0]['text']",
                "        with open('builder-args.txt', 'w', encoding='utf-8') as handle:",
                "            handle.write(prompt + '\\n')",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': {'turn': {'id': 'turn-it', 'status': 'in_progress'}}}) + '\\n')",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'method': 'item/agentMessage/delta', 'params': {'threadId': 'thread-it', 'turnId': 'turn-it', 'itemId': 'msg-1', 'delta': 'builder ok'}}) + '\\n')",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'method': 'turn/plan/updated', 'params': {'threadId': 'thread-it', 'turnId': 'turn-it', 'items': [{'id': 'plan-1', 'text': 'Modify this workspace.'}]}}) + '\\n')",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'method': 'turn/completed', 'params': {'threadId': 'thread-it', 'turn': {'id': 'turn-it', 'status': 'completed'}}}) + '\\n')",
                "        sys.stdout.flush()",
                "        break",
            ]
        )
        + "\n"
    )

    fake_codex = tmp_path / "fake-codex"
    fake_codex.write_text(
        "\n".join(
            [
                "#!/bin/sh",
                "if [ \"$1\" = \"app-server\" ]; then",
                "  shift",
                f"  exec {sys.executable} {fake_server}",
                "fi",
                "echo 'unexpected invocation' >&2",
                "exit 1",
            ]
        )
        + "\n"
    )
    fake_codex.chmod(0o755)

    fixtures_dir = tmp_path / "fixtures" / "issues"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "SPC-2.json").write_text(
        json.dumps(
            {
                "issue_id": "SPC-2",
                "title": "Run builder adapter",
                "summary": "Use codex harness builder before verification.",
                "builder_prompt": "Modify this workspace.",
                "verification_commands": {
                    "lint": ["{python}", "-c", "print('lint ok')"],
                    "typecheck": ["{python}", "-c", "print('type ok')"],
                    "test": ["{python}", "-c", "print('test ok')"],
                    "build": ["{python}", "-c", "print('build ok')"]
                }
            }
        )
    )
    _git(tmp_path, "add", ".")
    _git_commit(tmp_path, "add builder fixture")

    controller = RunController(repo_root=tmp_path, codex_executable=str(fake_codex))

    result = controller.run_issue("SPC-2")

    assert result.workspace.exists()
    assert result.builder.report_path.exists()
    assert result.gate.mergeable is False
    assert "human_acceptance" in result.gate.failed_conditions
    assert "review" in result.gate.failed_conditions
    assert "builder" not in result.gate.failed_conditions
    assert "builder_status=passed" in result.explain.read_text()
    assert '"adapter": "codex_harness"' in result.report.read_text()
    assert '"agent": "codex"' in result.report.read_text()
    assert "Modify this workspace." in (result.workspace / "builder-args.txt").read_text()
    telemetry_dir = result.workspace / "telemetry"
    assert telemetry_dir.exists()
    assert (telemetry_dir / "events.jsonl").exists()
    assert (telemetry_dir / "raw_harness_in.jsonl").exists()
    assert (telemetry_dir / "raw_harness_out.jsonl").exists()
    events = [json.loads(line) for line in (telemetry_dir / "events.jsonl").read_text().splitlines()]
    assert any(event["event_type"] == "builder_started" for event in events)
    assert any(event["event_type"] == "builder_completed" for event in events)
    assert any(
        event["event_type"] == "verification_step_completed"
        and event["data"]["step"] == "build"
        and event["data"]["exit_code"] == 0
        for event in events
    )
    assert any(
        event["event_type"] == "gate_evaluated"
        and event["data"]["mergeable"] is False
        and "review" in event["data"]["failed_conditions"]
        for event in events
    )
    report_data = json.loads(result.report.read_text())
    builder_data = json.loads(result.builder.report_path.read_text())
    assert report_data["run_id"]
    assert builder_data["metadata"]["run_id"] == report_data["run_id"]
    assert builder_data["metadata"]["thread_id"] == "thread-it"
    assert builder_data["metadata"]["turn_id"] == "turn-it"


def _init_git_repo(repo_root: Path) -> None:
    _git(repo_root, "init", "-b", "main")
    (repo_root / "README.md").write_text("# Temp Repo\n")
    _git(repo_root, "add", "README.md")
    _git_commit(repo_root, "initial commit")


def _git(repo_root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo_root, check=True)


def _git_commit(repo_root: Path, message: str) -> None:
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=SpecOrch Test",
            "-c",
            "user.email=spec-orch@example.com",
            "commit",
            "-m",
            message,
        ],
        cwd=repo_root,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
