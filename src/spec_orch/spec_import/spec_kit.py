"""Parser for Spec Kit format (.specify/ directory)."""

from __future__ import annotations

import re
from pathlib import Path

from spec_orch.spec_import.models import SpecStructure


class SpecKitParser:
    """Parse .specify/ directories into SpecStructure."""

    @property
    def format_id(self) -> str:
        return "spec-kit"

    def parse(self, path: Path) -> SpecStructure:
        path = Path(path)
        if path.is_file():
            path = path.parent

        spec_md = path / "spec.md"
        plan_md = path / "plan.md"

        goal = ""
        scope = ""
        acceptance_criteria: list[str] = []
        raw_sections: dict[str, str] = {}

        if spec_md.exists():
            content = spec_md.read_text()
            goal, ac_list, sections = self._parse_spec(content)
            acceptance_criteria = ac_list
            raw_sections.update(sections)

        if plan_md.exists():
            scope = plan_md.read_text().strip()

        return SpecStructure(
            goal=goal,
            scope=scope,
            acceptance_criteria=acceptance_criteria,
            raw_sections=raw_sections,
            source_format="spec-kit",
            source_path=str(path),
        )

    @staticmethod
    def _parse_spec(content: str) -> tuple[str, list[str], dict[str, str]]:
        sections: dict[str, str] = {}
        current_heading = ""
        current_lines: list[str] = []

        for line in content.split("\n"):
            heading_match = re.match(r"^##\s+(.+)$", line)
            if heading_match:
                if current_heading:
                    sections[current_heading] = "\n".join(current_lines).strip()
                current_heading = heading_match.group(1).strip()
                current_lines = []
            else:
                current_lines.append(line)

        if current_heading:
            sections[current_heading] = "\n".join(current_lines).strip()

        goal = sections.pop("Goal", sections.pop("goal", ""))
        ac_text = sections.pop("Requirements", sections.pop("Acceptance Criteria", ""))
        ac_list = [
            line.lstrip("- ").strip()
            for line in ac_text.split("\n")
            if line.strip().startswith("-")
        ]

        return goal, ac_list, sections
