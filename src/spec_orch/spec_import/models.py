"""Unified spec structure model for cross-format import."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SpecStructure:
    """Format-agnostic representation of a specification."""

    # IAC canonical fields
    intent: str = ""
    acceptance_criteria: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    # Legacy aliases (kept for backward compatibility during migration)
    goal: str = ""
    scope: str = ""
    raw_sections: dict[str, str] = field(default_factory=dict)
    source_format: str = ""
    source_path: str = ""

    def to_markdown(self, title: str) -> str:
        intent = self.intent or self.goal
        if not intent and self.scope:
            intent = self.scope

        lines = [f"# {title}", ""]
        lines += ["## Intent", "", intent or "<!-- describe the user value -->", ""]
        lines += ["## Acceptance Criteria", ""]
        for ac in self.acceptance_criteria:
            lines.append(f"- {ac}")
        if not self.acceptance_criteria:
            lines.append("- <!-- criterion -->")
        lines.append("")
        lines += ["## Constraints", ""]
        for c in self.constraints:
            lines.append(f"- {c}")
        if not self.constraints:
            lines.append("- <!-- constraint -->")
        lines.append("")
        lines += ["## Interface Contracts", "", "<!-- frozen APIs / schemas -->", ""]
        for section_name, content in self.raw_sections.items():
            if section_name.strip().lower() in {"goal", "scope", "intent"}:
                continue
            lines += [f"## {section_name}", "", content, ""]
        return "\n".join(lines)
