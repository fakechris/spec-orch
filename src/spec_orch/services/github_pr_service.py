from __future__ import annotations

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

    def _ensure_remote_branch(self, workspace: Path, branch: str) -> None:
        subprocess.run(
            ["git", "push", "-u", "origin", branch],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
