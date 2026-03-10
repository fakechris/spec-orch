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

    fake_exec_script = tmp_path / "fake_codex_exec.py"
    fake_exec_script.write_text(
        "\n".join(
            [
                "import json, sys, os",
                "prompt = sys.argv[-1]",
                "with open(os.path.join(os.getcwd(), 'builder-args.txt'), 'w') as f:",
                "    f.write(prompt + '\\n')",
                "events = [",
                "    {'type': 'item.completed', 'item': {'id': 'msg-1', 'type': 'agent_message', 'text': 'builder ok'}},",
                "    {'type': 'turn.plan.updated', 'items': [{'id': 'plan-1', 'text': 'Modify this workspace.'}]},",
                "    {'type': 'turn.completed', 'usage': {}},",
                "]",
                "for e in events:",
                "    sys.stdout.write(json.dumps(e) + '\\n')",
                "    sys.stdout.flush()",
            ]
        )
        + "\n"
    )

    fake_codex = tmp_path / "fake-codex"
    fake_codex.write_text(
        "\n".join(
            [
                "#!/bin/sh",
                f'exec {sys.executable} {fake_exec_script} "$@"',
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
                "summary": "Use codex exec builder before verification.",
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
    assert '"adapter": "codex_exec"' in result.report.read_text()
    assert '"agent": "codex"' in result.report.read_text()
    assert "Modify this workspace." in (result.workspace / "builder-args.txt").read_text()
    telemetry_dir = result.workspace / "telemetry"
    assert telemetry_dir.exists()
    assert (telemetry_dir / "events.jsonl").exists()
    assert (telemetry_dir / "incoming_events.jsonl").exists()
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
