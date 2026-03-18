"""AI-assisted merge conflict resolution.

When a rebase fails, this module classifies conflicts and attempts
resolution through formatting tools or an AI builder before escalating
to a human.
"""

from __future__ import annotations

import enum
import logging
import re
import subprocess
from pathlib import Path
from typing import Any

from spec_orch.domain.models import Issue

logger = logging.getLogger(__name__)

_FORMATTING_PATTERNS = re.compile(
    r"^(import\s|from\s\S+\simport\s)",
    re.MULTILINE,
)

_ARCHITECTURE_INDICATORS = [
    "__init__.py",
    "setup.py",
    "setup.cfg",
    "pyproject.toml",
    "Makefile",
    "Dockerfile",
    ".github/workflows/",
    "migrations/",
]

_MAX_CONFLICTING_FILES_FOR_BUILDER = 5


class ConflictType(enum.StrEnum):
    FORMATTING = "formatting"
    LOGIC = "logic"
    ARCHITECTURE = "architecture"


class ConflictResult:
    """Outcome of an AI conflict-resolution attempt."""

    __slots__ = ("resolved", "method", "details")

    def __init__(
        self,
        *,
        resolved: bool,
        method: str,
        details: str = "",
    ) -> None:
        self.resolved = resolved
        self.method = method
        self.details = details

    def __repr__(self) -> str:
        return f"ConflictResult(resolved={self.resolved}, method={self.method!r})"


class ConflictResolver:
    """Classifies merge conflicts and attempts automatic resolution."""

    def __init__(
        self,
        *,
        builder_adapter: Any | None = None,
        linear_client: Any | None = None,
    ) -> None:
        self._builder = builder_adapter
        self._linear = linear_client

    def classify(
        self,
        conflicting_files: list[str],
        workspace: Path,
    ) -> ConflictType:
        """Classify the overall conflict type from ``git merge-tree`` output.

        Each entry in *conflicting_files* is a line like
        ``CONFLICT (content): Merge conflict in path/to/file.py``.
        """
        file_paths = self._extract_paths(conflicting_files)

        if any(any(ind in fp for ind in _ARCHITECTURE_INDICATORS) for fp in file_paths):
            return ConflictType.ARCHITECTURE

        if not file_paths:
            return ConflictType.LOGIC

        conflict_texts = self._read_conflict_markers(workspace, file_paths)
        non_empty = [t for t in conflict_texts if t]
        if not non_empty:
            return ConflictType.LOGIC

        formatting_score = sum(1 for text in non_empty if _FORMATTING_PATTERNS.search(text))
        ratio = formatting_score / len(non_empty)
        if ratio >= 0.8:
            return ConflictType.FORMATTING

        return ConflictType.LOGIC

    def resolve(
        self,
        *,
        issue: Issue,
        workspace: Path,
        conflicting_files: list[str],
        base: str = "main",
    ) -> ConflictResult:
        """Orchestrate full resolution: classify -> trivial -> builder -> escalate."""
        conflict_type = self.classify(conflicting_files, workspace)
        logger.info(
            "Conflict type for %s: %s (%d files)",
            issue.issue_id,
            conflict_type,
            len(conflicting_files),
        )

        if not self._prepare_conflict_state(workspace, base):
            return ConflictResult(
                resolved=False,
                method="prepare_failed",
                details="Could not reproduce conflict state for resolution",
            )

        if conflict_type == ConflictType.FORMATTING:
            result = self._resolve_trivial(workspace)
            if result.resolved:
                return result

        if conflict_type in (ConflictType.FORMATTING, ConflictType.LOGIC):
            file_paths = self._extract_paths(conflicting_files)
            if len(file_paths) <= _MAX_CONFLICTING_FILES_FOR_BUILDER and self._builder is not None:
                result = self._resolve_with_builder(issue, workspace, file_paths)
                if result.resolved:
                    return result

        self._escalate(issue.issue_id, conflicting_files)
        return ConflictResult(
            resolved=False,
            method="escalated",
            details=f"Conflict type: {conflict_type}",
        )

    def _prepare_conflict_state(self, workspace: Path, base: str) -> bool:
        """Attempt a real merge to get conflict markers in the worktree."""
        merge = subprocess.run(
            ["git", "merge", f"origin/{base}", "--no-commit"],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
        return merge.returncode != 0

    def _resolve_trivial(self, workspace: Path) -> ConflictResult:
        """Try to resolve formatting/import conflicts with tooling."""
        subprocess.run(
            ["git", "checkout", "--theirs", "."],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )

        for cmd in [
            ["python3", "-m", "ruff", "format", "."],
            ["python3", "-m", "ruff", "check", "--fix", "--select", "I", "."],
        ]:
            res = subprocess.run(
                cmd,
                cwd=workspace,
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode != 0:
                logger.warning(
                    "Tooling command failed: %s — %s",
                    " ".join(cmd),
                    res.stderr.strip(),
                )
                self._abort_merge(workspace)
                return ConflictResult(
                    resolved=False,
                    method="trivial",
                    details=f"Tooling failed: {' '.join(cmd)}",
                )

        return self._finalize_merge(workspace, method="trivial")

    def _resolve_with_builder(
        self,
        issue: Issue,
        workspace: Path,
        file_paths: list[str],
    ) -> ConflictResult:
        """Use the builder adapter to resolve conflicts via AI."""
        if self._builder is None:
            return ConflictResult(resolved=False, method="builder_unavailable")

        conflict_context = self._read_conflict_markers(workspace, file_paths)
        prompt_parts = [
            "Resolve the following merge conflicts. "
            "For each file, pick the correct resolution and remove "
            "all conflict markers (<<<<<<, ======, >>>>>>).",
            "",
        ]
        for path, markers in zip(file_paths, conflict_context, strict=True):
            prompt_parts.append(f"### {path}")
            prompt_parts.append(f"```\n{markers}\n```")
            prompt_parts.append("")

        conflict_issue = Issue(
            issue_id=f"{issue.issue_id}-conflict",
            title=f"Resolve merge conflicts for {issue.issue_id}",
            summary="\n".join(prompt_parts),
            builder_prompt="\n".join(prompt_parts),
        )

        try:
            result = self._builder.run(
                issue=conflict_issue,
                workspace=workspace,
            )
        except Exception as exc:
            logger.warning("Builder conflict resolution failed: %s", exc)
            return ConflictResult(
                resolved=False,
                method="builder",
                details=str(exc),
            )

        if not result.succeeded:
            self._abort_merge(workspace)
            return ConflictResult(resolved=False, method="builder")

        return self._finalize_merge(workspace, method="builder")

    def _escalate(self, issue_id: str, conflicting_files: list[str]) -> None:
        """Post a comment on Linear and add a conflict label."""
        if self._linear is None:
            logger.info(
                "No Linear client — skipping escalation for %s",
                issue_id,
            )
            return

        file_list = "\n".join(f"- {f}" for f in conflicting_files[:20])
        body = (
            f"**Merge conflict could not be resolved automatically.**\n\n"
            f"Conflicting files:\n{file_list}\n\n"
            f"Manual intervention required."
        )
        try:
            linear_uid = self._linear.find_issue_id(issue_id)
            if linear_uid:
                self._linear.add_comment(linear_uid, body)
                self._linear.add_label(linear_uid, "conflict")
        except Exception as exc:
            logger.warning("Escalation to Linear failed: %s", exc)

    def _finalize_merge(self, workspace: Path, *, method: str) -> ConflictResult:
        """Stage, check for remaining conflicts, commit, and push."""
        add = subprocess.run(
            ["git", "add", "-A"],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
        if add.returncode != 0:
            self._abort_merge(workspace)
            return ConflictResult(resolved=False, method=method)

        remaining = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=U"],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
        if remaining.stdout.strip():
            self._abort_merge(workspace)
            return ConflictResult(
                resolved=False,
                method=method,
                details="Conflict markers remain after resolution",
            )

        commit = subprocess.run(
            ["git", "commit", "--no-edit"],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
        if commit.returncode != 0:
            self._abort_merge(workspace)
            return ConflictResult(resolved=False, method=method)

        push = subprocess.run(
            ["git", "push", "--force-with-lease"],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
        if push.returncode != 0:
            return ConflictResult(
                resolved=False,
                method=method,
                details="Commit succeeded but push failed",
            )

        return ConflictResult(resolved=True, method=method)

    def _abort_merge(self, workspace: Path) -> None:
        subprocess.run(
            ["git", "merge", "--abort"],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )

    @staticmethod
    def _extract_paths(conflicting_files: list[str]) -> list[str]:
        """Extract file paths from ``CONFLICT ... in <path>`` lines."""
        paths: list[str] = []
        for line in conflicting_files:
            match = re.search(r"(?:in|:)\s+(\S+)$", line)
            if match:
                paths.append(match.group(1))
        return paths

    @staticmethod
    def _read_conflict_markers(workspace: Path, file_paths: list[str]) -> list[str]:
        """Read conflict-marker regions from files."""
        results: list[str] = []
        for fp in file_paths:
            full = workspace / fp
            if not full.exists():
                results.append("")
                continue
            try:
                content = full.read_text(errors="replace")
                if "<<<<<<" in content:
                    results.append(content)
                else:
                    results.append("")
            except OSError:
                results.append("")
        return results
