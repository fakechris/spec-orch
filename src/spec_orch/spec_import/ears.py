"""Parser for EARS (Easy Approach to Requirements Syntax) format."""

from __future__ import annotations

import re
from pathlib import Path

from spec_orch.spec_import.models import SpecStructure

_EARS_PATTERN = re.compile(
    r"(?:WHEN|WHILE|WHERE|IF|AFTER)\s+.+?"
    r"(?:,?\s*THE\s+SYSTEM\s+SHALL\s+.+?)\.?$",
    re.IGNORECASE | re.MULTILINE,
)


class EarsParser:
    """Parse EARS-style requirement documents into SpecStructure."""

    @property
    def format_id(self) -> str:
        return "ears"

    def parse(self, path: Path) -> SpecStructure:
        content = Path(path).read_text()

        matches = _EARS_PATTERN.findall(content)

        acceptance_criteria = [m.strip().rstrip(".") for m in matches]

        title_match = re.match(r"^#\s+(.+)$", content, re.MULTILINE)
        goal = title_match.group(1).strip() if title_match else ""

        return SpecStructure(
            goal=goal,
            acceptance_criteria=acceptance_criteria,
            raw_sections={"Original EARS Content": content[:2000]},
            source_format="ears",
            source_path=str(path),
        )
