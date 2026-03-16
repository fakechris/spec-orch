"""Parser for BDD Gherkin .feature files."""

from __future__ import annotations

import re
from pathlib import Path

from spec_orch.spec_import.models import SpecStructure


class BddParser:
    """Parse Gherkin .feature files into SpecStructure."""

    @property
    def format_id(self) -> str:
        return "bdd"

    def parse(self, path: Path) -> SpecStructure:
        path = Path(path)
        if not path.is_file():
            raise ValueError(f"BDD parser requires a .feature file, got directory: {path}")
        content = path.read_text()

        feature_match = re.match(r"Feature:\s*(.+?)(?:\n|$)", content, re.IGNORECASE)
        goal = feature_match.group(1).strip() if feature_match else ""

        scenarios = re.findall(
            r"Scenario(?:\s+Outline)?:\s*(.+?)(?:\n|$)",
            content,
            re.IGNORECASE,
        )

        gwt_blocks = re.findall(
            r"((?:Given|When|Then|And|But)\s+.+?)(?=\n\s*(?:Given|When|Then|And|But|Scenario|Feature|$))",
            content,
            re.IGNORECASE,
        )

        acceptance_criteria: list[str] = []
        for scenario in scenarios:
            acceptance_criteria.append(f"Scenario: {scenario.strip()}")

        if not acceptance_criteria and gwt_blocks:
            for step in gwt_blocks:
                acceptance_criteria.append(step.strip())

        return SpecStructure(
            goal=goal,
            acceptance_criteria=acceptance_criteria,
            raw_sections={"Original Gherkin": content[:2000]},
            source_format="bdd",
            source_path=str(path),
        )
