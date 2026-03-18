from __future__ import annotations

import re

from spec_orch.domain.models import Issue, IssueContext
from spec_orch.services.linear_client import LinearClient

BUILDER_PROMPT_SECTION = re.compile(r"## Builder Prompt\s*\n(.*?)(?=\n## |\Z)", re.DOTALL)
ACCEPTANCE_CRITERIA_SECTION = re.compile(r"## Acceptance Criteria\s*\n(.*?)(?=\n## |\Z)", re.DOTALL)
CONTEXT_SECTION = re.compile(r"## Context\s*\n(.*?)(?=\n## |\Z)", re.DOTALL)


class LinearIssueSource:
    def __init__(
        self,
        *,
        client: LinearClient,
        default_verification_commands: dict[str, list[str]] | None = None,
    ) -> None:
        self._client = client
        self._default_verification = default_verification_commands or {
            "lint": ["{python}", "-m", "ruff", "check", "src/"],
            "typecheck": ["{python}", "-m", "mypy", "src/"],
            "test": ["{python}", "-m", "pytest", "-q"],
            "build": ["{python}", "-c", "print('build ok')"],
        }

    def load(self, issue_id: str) -> Issue:
        raw = self._client.get_issue(issue_id)
        description = raw.get("description", "") or ""
        builder_prompt = self._extract_section(BUILDER_PROMPT_SECTION, description)
        acceptance_criteria = self._extract_list(ACCEPTANCE_CRITERIA_SECTION, description)
        context = self._extract_context(description)

        labels_data = raw.get("labels", {}).get("nodes", [])
        labels = [lbl.get("name", "") for lbl in labels_data if lbl.get("name")]

        return Issue(
            issue_id=raw.get("identifier", issue_id),
            title=raw.get("title", ""),
            summary=description[:200] if description else "",
            builder_prompt=builder_prompt,
            verification_commands=self._default_verification,
            context=context,
            acceptance_criteria=acceptance_criteria,
            labels=labels,
        )

    def _extract_section(self, pattern: re.Pattern[str], text: str) -> str | None:
        match = pattern.search(text)
        if not match:
            return None
        content = match.group(1).strip()
        return content if content else None

    def _extract_list(self, pattern: re.Pattern[str], text: str) -> list[str]:
        match = pattern.search(text)
        if not match:
            return []
        content = match.group(1).strip()
        items = []
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("- ") or line.startswith("* "):
                items.append(line[2:].strip())
        return items

    def _extract_context(self, text: str) -> IssueContext:
        match = CONTEXT_SECTION.search(text)
        if not match:
            return IssueContext()
        content = match.group(1).strip()
        files: list[str] = []
        notes_lines: list[str] = []
        for line in content.splitlines():
            stripped = line.strip()
            if (stripped.startswith("- ") or stripped.startswith("* ")) and "/" in stripped:
                files.append(stripped[2:].strip())
            elif stripped:
                notes_lines.append(stripped)
        return IssueContext(
            files_to_read=files,
            architecture_notes="\n".join(notes_lines),
        )
