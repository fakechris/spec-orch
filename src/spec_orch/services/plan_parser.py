from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

_FILE_PATH_RE = re.compile(
    r"`([^`\n]+/(?:[^`\n/]+/)*[^`\n/]+\.(?:py|json|yaml|toml|md|ts|js))`",
    re.IGNORECASE,
)


@dataclass(slots=True)
class PlanData:
    title: str = ""
    summary: str = ""
    file_changes: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    architecture_notes: str = ""
    files_to_read: list[str] = field(default_factory=list)


def parse_plan(path: Path) -> PlanData:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    return PlanData(
        title=_extract_title(lines),
        summary=_extract_summary(lines),
        file_changes=_extract_bullets(
            lines,
            section_aliases=[
                "file changes",
                "implementation",
                "files to create",
                "files to modify",
            ],
        ),
        acceptance_criteria=_extract_bullets(lines, section_aliases=["acceptance criteria"]),
        constraints=_extract_bullets(lines, section_aliases=["not doing", "constraints"]),
        architecture_notes=_extract_architecture_notes(lines),
        files_to_read=sorted(set(_FILE_PATH_RE.findall(text))),
    )


def _extract_title(lines: list[str]) -> str:
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return ""


def _extract_summary(lines: list[str]) -> str:
    for heading_index, heading in _iter_h2_sections(lines):
        if _heading_matches(heading, ["intent", "background", "overview", "goal"]):
            paragraph = _extract_first_paragraph_after(lines, heading_index + 1)
            if paragraph:
                return paragraph

    title_index = next(
        (index for index, line in enumerate(lines) if line.lstrip().startswith("# ")),
        -1,
    )
    return _extract_first_paragraph_after(lines, title_index + 1)


def _extract_bullets(lines: list[str], *, section_aliases: list[str]) -> list[str]:
    bullets: list[str] = []
    for heading_index, heading in _iter_h2_sections(lines):
        if not _heading_matches(heading, section_aliases):
            continue
        for line in _iter_section_lines(lines, heading_index + 1):
            stripped = line.lstrip()
            if stripped.startswith("- ") or stripped.startswith("* "):
                bullets.append(stripped[2:].strip())
    return bullets


def _extract_architecture_notes(lines: list[str]) -> str:
    blocks: list[str] = []
    for heading_index, heading in _iter_h2_sections(lines):
        if not _heading_matches(heading, ["architecture", "design"]):
            continue
        content = textwrap.dedent("\n".join(_iter_section_lines(lines, heading_index + 1))).strip()
        if content:
            blocks.append(content)
    return "\n\n".join(blocks)


def _iter_h2_sections(lines: list[str]) -> list[tuple[int, str]]:
    return [
        (index, line.lstrip()[3:].strip())
        for index, line in enumerate(lines)
        if line.lstrip().startswith("## ")
    ]


def _heading_matches(heading: str, aliases: list[str]) -> bool:
    normalized_heading = _normalize_text(heading)
    parts = [_normalize_text(part) for part in heading.split("/")]
    candidates = [normalized_heading, *parts]
    return any(
        candidate == alias or bool(re.match(rf"^{re.escape(alias)}\b", candidate))
        for alias in (_normalize_text(alias) for alias in aliases)
        for candidate in candidates
        if candidate
    )


def _extract_first_paragraph_after(lines: list[str], start_index: int) -> str:
    paragraph_lines: list[str] = []
    in_paragraph = False

    for line in lines[start_index:]:
        stripped = line.strip()
        if stripped.startswith("#"):
            if in_paragraph:
                break
            break
        if not stripped:
            if in_paragraph:
                break
            continue
        paragraph_lines.append(stripped)
        in_paragraph = True

    return " ".join(paragraph_lines).strip()


def _iter_section_lines(lines: list[str], start_index: int) -> list[str]:
    section_lines: list[str] = []
    for line in lines[start_index:]:
        if line.lstrip().startswith("## "):
            break
        section_lines.append(line)
    return section_lines


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())
