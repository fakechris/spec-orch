"""Readiness checker for Linear issues before daemon execution.

Evaluates whether an issue description is complete enough for an agent
to execute autonomously.  Uses rule-based checks first, optionally
followed by an LLM assessment that generates targeted questions.

When a ``ContextBundle`` is provided, the LLM assessment includes
spec snapshots, constraints, and historical failure samples to produce
more calibrated triage decisions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from spec_orch.services.linear_intake import (
    contains_linear_intake_sections,
    has_blocking_open_questions,
    parse_linear_intake_description,
)

if TYPE_CHECKING:
    from spec_orch.domain.context import ContextBundle


@dataclass(slots=True)
class ReadinessResult:
    """Outcome of a readiness check."""

    ready: bool
    missing_fields: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)

    def format_comment(self) -> str:
        """Format as a Linear comment for the issue author."""
        lines = [
            "## SpecOrch: Clarification Needed",
            "",
            "This issue was moved to **Ready**, but some information "
            "is missing for automated execution.",
            "",
        ]
        if self.missing_fields:
            lines.append("### Missing Fields")
            lines.append("")
            for mf in self.missing_fields:
                lines.append(f"- {mf}")
            lines.append("")

        if self.questions:
            lines.append("### Questions")
            lines.append("")
            for i, q in enumerate(self.questions, 1):
                lines.append(f"{i}. {q}")
            lines.append("")

        lines.append(
            "_Please update the issue description or reply to this comment. "
            "The daemon will re-evaluate on the next poll cycle._"
        )
        return "\n".join(lines)


_HEADING_RE = re.compile(r"^##\s+(.+)", re.MULTILINE)
_CHECKBOX_RE = re.compile(r"^-\s*\[[ x]\]\s+", re.MULTILINE)
_BULLET_RE = re.compile(r"^-\s+`[^`]+`", re.MULTILINE)


class ReadinessChecker:
    """Check whether an issue description meets minimum completeness."""

    def __init__(
        self,
        *,
        planner: Any | None = None,
        evidence_context: str | None = None,
    ) -> None:
        self._planner = planner
        self._evidence_context = evidence_context

    def check(
        self,
        description: str | None,
        context: ContextBundle | None = None,
    ) -> ReadinessResult:
        """Run rule-based checks, optionally followed by LLM assessment."""
        if not description or not description.strip():
            return ReadinessResult(
                ready=False,
                missing_fields=["Goal", "Acceptance Criteria", "Files in Scope"],
                questions=["The issue has no description. Please add context."],
            )

        if contains_linear_intake_sections(description):
            result = self._check_linear_intake(description)
            if not result.ready:
                return result
            if self._planner is not None:
                return self._llm_check(description, context)
            return result

        missing = self._rule_check(description)
        if missing:
            return ReadinessResult(
                ready=False,
                missing_fields=missing,
                questions=self._questions_from_missing(missing),
            )

        if self._planner is not None:
            return self._llm_check(description, context)

        return ReadinessResult(ready=True)

    def _check_linear_intake(self, description: str) -> ReadinessResult:
        document = parse_linear_intake_description(description)
        missing: list[str] = []
        questions: list[str] = []

        if not document.problem.strip():
            missing.append("Problem")
            questions.append("What is wrong, who is affected, and why does it matter now?")
        if not document.goal.strip():
            missing.append("Goal")
            questions.append("What outcome should this Linear intake item achieve?")
        if (
            not document.acceptance.success_conditions
            and not document.acceptance.failure_conditions
            and not document.acceptance.verification_expectations
        ):
            missing.append("Acceptance")
            questions.append("What does success and failure look like for this issue?")
        if not document.acceptance.verification_expectations:
            missing.append("Verification Expectations")
            questions.append("How should the system or operator verify this work?")
        if has_blocking_open_questions(document):
            missing.append("Blocking Open Questions")
            questions.extend(document.open_questions)

        if missing:
            return ReadinessResult(
                ready=False,
                missing_fields=missing,
                questions=questions,
            )
        return ReadinessResult(ready=True)

    def _rule_check(self, description: str) -> list[str]:
        """Check for required sections per the issue template."""
        headings = {h.strip().lower() for h in _HEADING_RE.findall(description)}
        missing: list[str] = []

        goal_section = self._extract_section(description, "goal")
        if not goal_section.strip():
            missing.append("Goal")

        has_ac = (
            "acceptance criteria" in headings
            or "acceptance" in headings
            or bool(_CHECKBOX_RE.search(description))
        )
        if not has_ac:
            missing.append("Acceptance Criteria")

        has_files = (
            "files in scope" in headings
            or "files" in headings
            or bool(_BULLET_RE.search(description))
        )
        if not has_files:
            missing.append("Files in Scope")

        return missing

    def _extract_section(self, description: str, heading: str) -> str:
        """Extract text under a markdown heading."""
        pattern = re.compile(
            rf"^##\s+{re.escape(heading)}\s*\n(.*?)(?=^##\s|\Z)",
            re.MULTILINE | re.DOTALL | re.IGNORECASE,
        )
        match = pattern.search(description)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _questions_from_missing(missing: list[str]) -> list[str]:
        templates = {
            "Goal": "What is the specific goal of this task?",
            "Acceptance Criteria": (
                "What are the acceptance criteria? Please add at least one `- [ ] ...` checkbox."
            ),
            "Files in Scope": (
                "Which files should be modified? "
                "Please list them as `- \\`path/to/file\\`` or state 'any'."
            ),
        }
        return [templates.get(m, f"Please provide: {m}") for m in missing]

    def _llm_check(
        self,
        description: str,
        context: ContextBundle | None = None,
    ) -> ReadinessResult:
        """Use the planner LLM to assess description completeness."""
        evidence_block = ""
        if self._evidence_context:
            evidence_block = (
                "\n\nUse the following historical evidence to calibrate "
                "your assessment. For example, issues in areas with high "
                "failure rates may need more explicit acceptance criteria "
                "or scope constraints:\n\n" + self._evidence_context + "\n\n"
            )

        context_block = ""
        if context is not None:
            parts: list[str] = []
            if context.task.spec_snapshot_text:
                parts.append(f"### Spec Snapshot\n{context.task.spec_snapshot_text[:2000]}")
            if context.task.constraints:
                parts.append(
                    "### Constraints\n" + "\n".join(f"- {c}" for c in context.task.constraints)
                )
            if context.task.acceptance_criteria:
                parts.append(
                    "### Acceptance Criteria\n"
                    + "\n".join(f"- {c}" for c in context.task.acceptance_criteria)
                )
            if context.execution.file_tree:
                parts.append(
                    f"### Codebase Structure\n```\n{context.execution.file_tree[:1000]}\n```"
                )
            if context.learning.similar_failure_samples:
                lines = []
                for s in context.learning.similar_failure_samples[:3]:
                    lines.append(f"- {s.get('key', '?')}: {s.get('content', '')[:200]}")
                parts.append("### Recent Failure Samples (from similar tasks)\n" + "\n".join(lines))
            if parts:
                context_block = (
                    "\n\nAdditional context from the orchestration system:\n\n"
                    + "\n\n".join(parts)
                    + "\n\n"
                )

        prompt = (
            "You are a triage assistant. Evaluate whether the following issue "
            "description is clear and complete enough for an AI coding agent "
            "to execute autonomously.\n\n"
            "Check for:\n"
            "1. Clear goal / what needs to be built or fixed\n"
            "2. Acceptance criteria (how to verify success)\n"
            "3. Scope (which files or areas are affected)\n"
            "4. Any ambiguities that would block execution\n\n"
            + evidence_block
            + context_block
            + "If the description is sufficient, respond with exactly: READY\n"
            "If not, respond with a numbered list of specific questions "
            "the agent needs answered before it can proceed.\n\n"
            f"Issue description:\n---\n{description}\n---"
        )
        assert self._planner is not None
        try:
            raw = self._planner.brainstorm(
                conversation_history=[{"role": "user", "content": prompt}],
            )
            text = raw.strip() if isinstance(raw, str) else str(raw)
            if text.upper().startswith("READY"):
                return ReadinessResult(ready=True)
            questions = [
                line.lstrip("0123456789.) ").strip()
                for line in text.splitlines()
                if line.strip() and line.strip()[0].isdigit()
            ]
            if not questions:
                questions = [text]
            return ReadinessResult(
                ready=False,
                questions=questions,
            )
        except Exception as exc:
            print(f"[readiness_checker] LLM check failed, defaulting to ready: {exc}")
            return ReadinessResult(ready=True)
