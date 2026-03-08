from __future__ import annotations

import subprocess
from pathlib import Path


class WorkspaceService:
    def __init__(self, *, repo_root: Path) -> None:
        self.repo_root = Path(repo_root)

    def prepare_issue_workspace(self, issue_id: str) -> Path:
        workspace = self.issue_workspace_path(issue_id)
        if not self._is_git_repository():
            workspace.mkdir(parents=True, exist_ok=True)
            return workspace

        if workspace.exists() and (workspace / ".git").exists():
            return workspace

        workspace.parent.mkdir(parents=True, exist_ok=True)
        branch_name = f"issue/{issue_id.lower()}"
        if self._branch_exists(branch_name):
            self._run_git("worktree", "add", str(workspace), branch_name)
        else:
            self._run_git("worktree", "add", str(workspace), "-b", branch_name, "HEAD")

        return workspace

    def issue_workspace_path(self, issue_id: str) -> Path:
        if self._is_git_repository():
            return self.repo_root / ".worktrees" / issue_id
        return self.repo_root / ".spec_orch_runs" / issue_id

    def _is_git_repository(self) -> bool:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=self.repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    def _branch_exists(self, branch_name: str) -> bool:
        result = subprocess.run(
            ["git", "show-ref", "--verify", f"refs/heads/{branch_name}"],
            cwd=self.repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    def _run_git(self, *args: str) -> None:
        subprocess.run(
            ["git", *args],
            cwd=self.repo_root,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
