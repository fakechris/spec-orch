from __future__ import annotations

import json
import re
from pathlib import Path

from spec_orch.domain.models import Issue, IssueContext

_VALID_ISSUE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class FixtureIssueSource:
    def __init__(self, *, repo_root: Path) -> None:
        self.repo_root = repo_root

    def load(self, issue_id: str) -> Issue:
        if not _VALID_ISSUE_ID_RE.match(issue_id):
            raise ValueError(
                f"Invalid issue_id: {issue_id!r}. "
                "Only alphanumeric characters, hyphens, and underscores are allowed."
            )
        fixture_path = self.repo_root / "fixtures" / "issues" / f"{issue_id}.json"
        if not fixture_path.exists():
            raise FileNotFoundError(
                f"Fixture not found: {fixture_path}. "
                f"Create {fixture_path} with issue_id, title, summary fields."
            )
        data = json.loads(fixture_path.read_text())
        ctx_raw = data.get("context", {})
        context = IssueContext(
            files_to_read=ctx_raw.get("files_to_read", []),
            architecture_notes=ctx_raw.get("architecture_notes", ""),
            constraints=ctx_raw.get("constraints", []),
        )
        return Issue(
            issue_id=data["issue_id"],
            title=data["title"],
            summary=data["summary"],
            builder_prompt=data.get("builder_prompt"),
            verification_commands=data.get("verification_commands", {}),
            context=context,
            acceptance_criteria=data.get("acceptance_criteria", []),
        )
