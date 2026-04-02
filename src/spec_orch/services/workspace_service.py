from __future__ import annotations

import hashlib
import logging
import re
import subprocess
from pathlib import Path

_VALID_ISSUE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
logger = logging.getLogger(__name__)


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
        self._prune_worktrees()
        branch_name = f"issue/{issue_id.lower()}"
        if self._branch_exists(branch_name) and self._branch_checked_out_elsewhere(branch_name):
            return self._prepare_scoped_issue_workspace(workspace, issue_id, branch_name)
        try:
            if self._branch_exists(branch_name):
                self._run_git("worktree", "add", str(workspace), branch_name)
            else:
                self._run_git("worktree", "add", str(workspace), "-b", branch_name, "HEAD")
        except subprocess.CalledProcessError as exc:
            if not self._branch_is_checked_out_elsewhere(exc):
                raise
            return self._prepare_scoped_issue_workspace(workspace, issue_id, branch_name)

        return workspace

    def issue_workspace_path(self, issue_id: str) -> Path:
        if not _VALID_ISSUE_ID_RE.match(issue_id):
            raise ValueError(
                f"Invalid issue_id: {issue_id!r}. "
                "Only alphanumeric characters, hyphens, and underscores are allowed."
            )
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

    def _prune_worktrees(self) -> None:
        result = subprocess.run(
            ["git", "worktree", "prune"],
            cwd=self.repo_root,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode != 0:
            logger.warning(
                "git worktree prune failed under %s: %s",
                self.repo_root,
                result.stderr.strip() or f"exit {result.returncode}",
            )

    def _run_git(self, *args: str) -> None:
        subprocess.run(
            ["git", *args],
            cwd=self.repo_root,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )

    def _branch_is_checked_out_elsewhere(self, exc: subprocess.CalledProcessError) -> bool:
        output_parts: list[str] = []
        if isinstance(exc.stderr, str):
            output_parts.append(exc.stderr.lower())
        if isinstance(exc.stdout, str):
            output_parts.append(exc.stdout.lower())
        output = "\n".join(output_parts)
        return (
            "already checked out" in output
            or "already used by worktree" in output
            or "already in use by worktree" in output
        )

    def _branch_checked_out_elsewhere(self, branch_name: str) -> bool:
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=self.repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return False
        target_ref = f"refs/heads/{branch_name}"
        current_worktree = self.repo_root.resolve()
        seen_worktree: Path | None = None
        for line in result.stdout.splitlines():
            if line.startswith("worktree "):
                seen_worktree = Path(line.removeprefix("worktree ").strip()).resolve()
                continue
            if (
                line.startswith("branch ")
                and seen_worktree
                and line.removeprefix("branch ").strip() == target_ref
                and seen_worktree != current_worktree
            ):
                return True
        return False

    def _scoped_issue_branch_name(self, issue_id: str) -> str:
        repo_scope = hashlib.sha1(str(self.repo_root.resolve()).encode("utf-8")).hexdigest()[:8]
        return f"issue/{issue_id.lower()}-{repo_scope}"

    def _prepare_scoped_issue_workspace(
        self, workspace: Path, issue_id: str, branch_name: str
    ) -> Path:
        scoped_branch = self._scoped_issue_branch_name(issue_id)
        start_point = branch_name if self._branch_exists(branch_name) else "HEAD"
        if not self._branch_exists(scoped_branch):
            self._run_git("branch", scoped_branch, start_point)
        self._run_git("worktree", "add", str(workspace), scoped_branch)
        return workspace
