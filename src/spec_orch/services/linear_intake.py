from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum


class LinearIntakeState(StrEnum):
    RAW = "raw"
    CLARIFYING = "clarifying"
    ACCEPTANCE_DRAFTING = "acceptance_drafting"
    READY_FOR_WORKSPACE = "ready_for_workspace"
    WORKSPACE_CREATED = "workspace_created"


@dataclass(slots=True)
class LinearAcceptanceDraft:
    success_conditions: list[str] = field(default_factory=list)
    failure_conditions: list[str] = field(default_factory=list)
    verification_expectations: list[str] = field(default_factory=list)
    human_judgment_required: list[str] = field(default_factory=list)
    priority_routes_or_surfaces: list[str] = field(default_factory=list)


@dataclass(slots=True)
class LinearIntakeDocument:
    problem: str = ""
    goal: str = ""
    constraints: list[str] = field(default_factory=list)
    acceptance: LinearAcceptanceDraft = field(default_factory=LinearAcceptanceDraft)
    evidence_expectations: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    current_system_understanding: str = ""

    def has_structured_content(self) -> bool:
        return any(
            (
                self.problem.strip(),
                self.goal.strip(),
                self.constraints,
                self.acceptance.success_conditions,
                self.acceptance.verification_expectations,
                self.evidence_expectations,
                self.open_questions,
                self.current_system_understanding.strip(),
            )
        )


_SECTION_TITLES = (
    "Problem",
    "Goal",
    "Constraints",
    "Acceptance",
    "Evidence Expectations",
    "Open Questions",
    "Current System Understanding",
)
_SUBSECTION_TITLES = (
    "Success Conditions",
    "Failure Conditions",
    "Verification Expectations",
    "Human Judgment Required",
    "Priority Routes or Surfaces",
)


def contains_linear_intake_sections(text: str | None) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(
        marker in lowered
        for marker in (
            "## problem",
            "## evidence expectations",
            "## open questions",
            "## current system understanding",
            "### success conditions",
            "### verification expectations",
        )
    )


def parse_linear_intake_description(text: str | None) -> LinearIntakeDocument:
    if not text:
        return LinearIntakeDocument()

    acceptance_block = _extract_section(text, "Acceptance")
    return LinearIntakeDocument(
        problem=_extract_section(text, "Problem"),
        goal=_extract_section(text, "Goal"),
        constraints=_extract_bullets(_extract_section(text, "Constraints")),
        acceptance=LinearAcceptanceDraft(
            success_conditions=_extract_bullets(
                _extract_subsection(acceptance_block, "Success Conditions")
            ),
            failure_conditions=_extract_bullets(
                _extract_subsection(acceptance_block, "Failure Conditions")
            ),
            verification_expectations=_extract_bullets(
                _extract_subsection(acceptance_block, "Verification Expectations")
            ),
            human_judgment_required=_extract_bullets(
                _extract_subsection(acceptance_block, "Human Judgment Required")
            ),
            priority_routes_or_surfaces=_extract_bullets(
                _extract_subsection(acceptance_block, "Priority Routes or Surfaces")
            ),
        ),
        evidence_expectations=_extract_bullets(_extract_section(text, "Evidence Expectations")),
        open_questions=_extract_bullets(_extract_section(text, "Open Questions")),
        current_system_understanding=_extract_section(text, "Current System Understanding"),
    )


def render_linear_intake_description(document: LinearIntakeDocument) -> str:
    sections = [
        ("Problem", document.problem),
        ("Goal", document.goal),
        ("Constraints", _render_bullets(document.constraints)),
        ("Acceptance", _render_acceptance(document.acceptance)),
        ("Evidence Expectations", _render_bullets(document.evidence_expectations)),
        ("Open Questions", _render_bullets(document.open_questions)),
        ("Current System Understanding", document.current_system_understanding),
    ]
    rendered: list[str] = []
    for title, content in sections:
        rendered.append(f"## {title}")
        rendered.append("")
        rendered.append(content.strip() if content.strip() else "<!-- pending -->")
        rendered.append("")
    return "\n".join(rendered).rstrip() + "\n"


def derive_linear_intake_state(document: LinearIntakeDocument) -> LinearIntakeState:
    if not document.has_structured_content():
        return LinearIntakeState.RAW
    if not document.problem.strip() or not document.goal.strip():
        return LinearIntakeState.CLARIFYING
    if has_blocking_open_questions(document):
        return LinearIntakeState.CLARIFYING
    if (
        not document.acceptance.success_conditions
        or not document.acceptance.verification_expectations
    ):
        return LinearIntakeState.ACCEPTANCE_DRAFTING
    if "workspace created" in document.current_system_understanding.lower():
        return LinearIntakeState.WORKSPACE_CREATED
    return LinearIntakeState.READY_FOR_WORKSPACE


def has_blocking_open_questions(document: LinearIntakeDocument) -> bool:
    return any(_is_blocking_question(item) for item in document.open_questions)


def _is_blocking_question(question: str) -> bool:
    normalized = question.strip().lower()
    return normalized.startswith("[blocking]") or normalized.startswith("blocking:")


def _extract_section(text: str, heading: str) -> str:
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*\n(.*?)(?=^##\s|\Z)",
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def _extract_subsection(text: str, heading: str) -> str:
    pattern = re.compile(
        rf"^###\s+{re.escape(heading)}\s*\n(.*?)(?=^###\s|\Z)",
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def _extract_bullets(text: str) -> list[str]:
    items: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- ") or stripped.startswith("* "):
            items.append(stripped[2:].strip())
    return items


def _render_bullets(items: list[str]) -> str:
    if not items:
        return ""
    return "\n".join(f"- {item}" for item in items)


def _render_acceptance(acceptance: LinearAcceptanceDraft) -> str:
    sections: list[str] = []
    for title, items in (
        ("Success Conditions", acceptance.success_conditions),
        ("Failure Conditions", acceptance.failure_conditions),
        ("Verification Expectations", acceptance.verification_expectations),
        ("Human Judgment Required", acceptance.human_judgment_required),
        ("Priority Routes or Surfaces", acceptance.priority_routes_or_surfaces),
    ):
        sections.append(f"### {title}")
        sections.append("")
        sections.append(_render_bullets(items) or "<!-- pending -->")
        sections.append("")
    return "\n".join(sections).strip()
