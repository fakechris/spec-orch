from __future__ import annotations

import json
import subprocess
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
    assert "blocked_by=human_acceptance" in result.explain.read_text()


def test_run_controller_runs_builder_when_prompt_is_present(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)

    fake_pi = tmp_path / "fake-pi"
    fake_pi.write_text(
        "\n".join(
            [
                "#!/bin/sh",
                "printf '%s\n' \"$@\" > builder-args.txt",
                "echo 'builder ok'",
            ]
        )
        + "\n"
    )
    fake_pi.chmod(0o755)

    fixtures_dir = tmp_path / "fixtures" / "issues"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "SPC-2.json").write_text(
        json.dumps(
            {
                "issue_id": "SPC-2",
                "title": "Run builder adapter",
                "summary": "Use pi builder before verification.",
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

    controller = RunController(repo_root=tmp_path, pi_executable=str(fake_pi))

    result = controller.run_issue("SPC-2")

    assert result.workspace.exists()
    assert result.gate.mergeable is False
    assert "human_acceptance" in result.gate.failed_conditions
    assert "builder" not in result.gate.failed_conditions
    assert "Modify this workspace." in (result.workspace / "builder-args.txt").read_text()


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
