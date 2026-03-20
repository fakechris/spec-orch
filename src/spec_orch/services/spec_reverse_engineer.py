"""Reverse-engineer a structured spec from example content using an LLM."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_REVERSE_PROMPT = """\
You are a spec author. Given the following reference content and a mission title,
produce a structured spec in Markdown with these sections:

# {title}

## Intent
(What user value does this deliver?)

## Acceptance Criteria
(Bullet list of verifiable conditions)

## Constraints
(Technical or process constraints)

## Interface Contracts
(APIs, schemas, or protocols that must be respected)

---
Reference content:
{content}
---

Output ONLY the Markdown spec. Do not add explanations outside the spec.
"""


def _extract_json_fields(raw: str) -> str:
    """If raw is JSON, extract key fields for a more focused prompt input."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw

    if not isinstance(data, dict):
        return raw

    parts: list[str] = []
    for key in (
        "summary",
        "title",
        "description",
        "builder_prompt",
        "acceptance_criteria",
        "body",
        "content",
    ):
        val = data.get(key)
        if val:
            parts.append(f"**{key}**: {val}")
    return "\n\n".join(parts) if parts else raw


def reverse_engineer_spec(
    content: str,
    title: str,
    *,
    planner: Any | None = None,
) -> str:
    """Call an LLM to reverse-engineer a spec from example content.

    Parameters
    ----------
    content:
        Raw example text (JSON, Markdown, or plain text).
    title:
        The mission title to use in the generated spec.
    planner:
        An optional planner adapter (e.g. LiteLLMPlannerAdapter) with a
        ``generate(prompt)`` method.  When *None*, a rule-based fallback
        produces a skeleton spec.

    Returns
    -------
    str
        The generated spec in Markdown format.
    """
    extracted = _extract_json_fields(content)
    prompt = _REVERSE_PROMPT.format(title=title, content=extracted)

    if planner is not None and hasattr(planner, "generate"):
        result: str = planner.generate(prompt)
        return result

    logger.warning("FALLBACK [SpecReverseEngineer]: llm → rule_skeleton — no planner available")
    try:
        from spec_orch.services.event_bus import get_event_bus

        get_event_bus().emit_fallback(
            component="SpecReverseEngineer",
            primary="llm_generation",
            fallback="rule_skeleton",
            reason="No planner adapter available",
        )
    except Exception:
        pass
    return _rule_based_fallback(title, extracted)


def _rule_based_fallback(title: str, content: str) -> str:
    """Produce a minimal spec skeleton when no LLM is available."""
    preview = content[:500]
    if len(content) > 500:
        preview += "\n..."
    return (
        f"# {title}\n\n"
        "## Intent\n\n<!-- describe the user value -->\n\n"
        "## Acceptance Criteria\n\n"
        "- <!-- criterion 1 -->\n\n"
        "## Constraints\n\n"
        "- <!-- constraint 1 -->\n\n"
        "## Interface Contracts\n\n"
        "<!-- frozen APIs / schemas -->\n\n"
        "---\n\n"
        "### Reference (auto-extracted)\n\n"
        f"```\n{preview}\n```\n"
    )
