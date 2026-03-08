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
