from __future__ import annotations

import json as _json
import subprocess
from pathlib import Path

from spec_orch.domain.models import GateVerdict, RunResult


class GitHubPRService:
    def __init__(self, *, gh_executable: str = "gh") -> None:
        self.gh = gh_executable

    def create_pr(
        self,
        *,
        workspace: Path,
        title: str,
        body: str,
        base: str = "main",
        draft: bool = True,
    ) -> str | None:
        branch = self._current_branch(workspace)
        if not branch or branch == base:
            return None

        self._ensure_remote_branch(workspace, branch)

        result = subprocess.run(
            [
                self.gh,
                "pr",
                "create",
                "--title",
                title,
                "--body",
                body,
                "--base",
                base,
                "--head",
                branch,
                *(["--draft"] if draft else []),
            ],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"gh pr create failed: {result.stderr.strip()}")
        return result.stdout.strip()

    def create_pr_from_result(
        self, *, result: RunResult, draft: bool = True, base: str = "main"
    ) -> str | None:
        body = self._build_pr_body(result)
        return self.create_pr(
            workspace=result.workspace,
            title=f"[SpecOrch] {result.issue.issue_id}: {result.issue.title}",
            body=body,
            base=base,
            draft=draft,
        )

    def set_gate_status(
        self,
        *,
        workspace: Path,
        sha: str | None = None,
        gate: GateVerdict,
        context: str = "specorch/gate",
    ) -> None:
        if not sha:
            sha = self._head_sha(workspace)
        if not sha:
            return

        state = "success" if gate.mergeable else "failure"
        description = (
            "All gate conditions passed"
            if gate.mergeable
            else f"Blocked: {', '.join(gate.failed_conditions)}"
        )

        subprocess.run(
            [
                self.gh,
                "api",
                "-X",
                "POST",
                f"repos/{{owner}}/{{repo}}/statuses/{sha}",
                "-f",
                f"state={state}",
                "-f",
                f"context={context}",
                "-f",
                f"description={description}",
            ],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )

    def _build_pr_body(self, result: RunResult) -> str:
        gate = result.gate
        builder = result.builder
        issue = result.issue
        lines = [
            "## SpecOrch Automated PR",
            "",
            f"**Issue**: {issue.issue_id} — {issue.title}",
            f"**Builder**: {builder.adapter} ({builder.agent})",
            "",
            "### Gate Status",
            "",
            f"**Mergeable**: {'yes' if gate.mergeable else 'no'}",
        ]
        if gate.failed_conditions:
            lines.append(f"**Blocked by**: {', '.join(gate.failed_conditions)}")

        if issue.acceptance_criteria:
            lines.extend(["", "### Acceptance Criteria", ""])
            for ac in issue.acceptance_criteria:
                lines.append(f"- [ ] {ac}")

        explain = result.explain
        if explain.exists():
            text = explain.read_text().strip()
            if len(text) > 3000:
                text = text[:3000] + "\n\n*(truncated)*"
            lines.extend(["", "### Explain Report", "", text])

        lines.extend(["", f"Closes {issue.issue_id}"])
        return "\n".join(lines)

    def _current_branch(self, workspace: Path) -> str | None:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
        branch = result.stdout.strip()
        return branch if result.returncode == 0 and branch else None

    def _head_sha(self, workspace: Path) -> str | None:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
        sha = result.stdout.strip()
        return sha if result.returncode == 0 and sha else None

    def mark_ready(self, workspace: Path, pr_number: int | None = None) -> bool:
        """Convert a draft PR to ready-for-review."""
        if pr_number is None:
            pr_number = self._current_pr_number(workspace)
        if not pr_number:
            return False
        result = subprocess.run(
            [self.gh, "pr", "ready", str(pr_number)],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0

    def merge_pr(
        self,
        workspace: Path,
        *,
        pr_number: int | None = None,
        method: str = "squash",
        delete_branch: bool = True,
    ) -> bool:
        """Merge a PR. Returns True on success."""
        if pr_number is None:
            pr_number = self._current_pr_number(workspace)
        if not pr_number:
            return False

        self.mark_ready(workspace, pr_number)

        cmd = [
            self.gh, "pr", "merge", str(pr_number),
            f"--{method}",
            "--auto",
        ]
        if delete_branch:
            cmd.append("--delete-branch")
        result = subprocess.run(
            cmd,
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0

    def _current_pr_number(self, workspace: Path) -> int | None:
        """Get the PR number for the current branch."""
        result = subprocess.run(
            [self.gh, "pr", "view", "--json", "number", "-q", ".number"],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return None
        try:
            return int(result.stdout.strip())
        except ValueError:
            return None

    def list_open_prs(
        self, workspace: Path, *, base: str = "main",
    ) -> list[dict]:
        """List open PRs created by SpecOrch (matching title prefix)."""
        result = subprocess.run(
            [
                self.gh, "pr", "list",
                "--state", "open",
                "--base", base,
                "--json", "number,title,headRefName,headRefOid",
                "--search", "[SpecOrch]",
            ],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return []
        try:
            return _json.loads(result.stdout)
        except _json.JSONDecodeError:
            return []

    def check_mergeable(
        self, workspace: Path, *, branch: str, base: str = "main",
    ) -> dict:
        """Dry-run merge to check for conflicts.

        Returns {"mergeable": bool, "conflicting_files": list[str]}.
        """
        fetch = subprocess.run(
            ["git", "fetch", "origin", base],
            cwd=workspace, capture_output=True, text=True, check=False,
        )
        if fetch.returncode != 0:
            return {"mergeable": False, "conflicting_files": ["git fetch failed"]}

        merge_result = subprocess.run(
            ["git", "merge-tree", f"origin/{base}", branch],
            cwd=workspace, capture_output=True, text=True, check=False,
        )

        if merge_result.returncode == 0:
            return {"mergeable": True, "conflicting_files": []}

        conflicts: list[str] = []
        for line in merge_result.stdout.splitlines():
            if line.startswith("CONFLICT"):
                conflicts.append(line)
        return {"mergeable": False, "conflicting_files": conflicts}

    def auto_rebase(
        self, workspace: Path, *, base: str = "main",
    ) -> bool:
        """Attempt to rebase the current branch onto base. Returns True on success."""
        fetch = subprocess.run(
            ["git", "fetch", "origin", base],
            cwd=workspace, capture_output=True, text=True, check=False,
        )
        if fetch.returncode != 0:
            return False

        rebase = subprocess.run(
            ["git", "rebase", f"origin/{base}"],
            cwd=workspace, capture_output=True, text=True, check=False,
        )
        if rebase.returncode != 0:
            subprocess.run(
                ["git", "rebase", "--abort"],
                cwd=workspace, capture_output=True, text=True, check=False,
            )
            return False

        push = subprocess.run(
            ["git", "push", "--force-with-lease"],
            cwd=workspace, capture_output=True, text=True, check=False,
        )
        return push.returncode == 0

    def _ensure_remote_branch(self, workspace: Path, branch: str) -> None:
        subprocess.run(
            ["git", "push", "-u", "origin", branch],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
