"""ContextRanker — priority-aware context truncation.

Replaces naive `text[:limit]` truncation with priority-based allocation.
Each context section is assigned a retention priority from CompactRetentionPriority.
Higher-priority sections get proportionally more budget; lower-priority sections
are truncated first.

This implements the "上下文选择策略" from R5.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_CHARS_PER_TOKEN = 4


@dataclass(frozen=True)
class RankedSection:
    """A context section with its content and retention priority."""

    name: str
    content: str
    priority: int  # lower = higher priority (1=keep, 5=discard first)


class ContextRanker:
    """Allocate token budget across sections by priority."""

    @staticmethod
    def allocate(
        sections: list[RankedSection],
        total_budget_tokens: int,
    ) -> dict[str, str]:
        """Distribute token budget across sections by priority.

        Returns a dict mapping section name to (possibly truncated) content.
        Higher priority sections get proportionally more of the remaining budget.
        """
        if not sections:
            return {}

        total_chars = total_budget_tokens * _CHARS_PER_TOKEN
        result: dict[str, str] = {}

        sorted_sections = sorted(sections, key=lambda s: s.priority)

        section_sizes = {s.name: len(s.content) for s in sorted_sections}
        total_content = sum(section_sizes.values())

        if total_content <= total_chars:
            return {s.name: s.content for s in sorted_sections}

        remaining_budget = total_chars
        remaining_sections = list(sorted_sections)

        for i, section in enumerate(remaining_sections):
            content_len = len(section.content)

            if i == len(remaining_sections) - 1:
                alloc = remaining_budget
            else:
                weight = _priority_weight(section.priority)
                total_weight = sum(_priority_weight(s.priority) for s in remaining_sections[i:])
                alloc = int(remaining_budget * weight / total_weight) if total_weight > 0 else 0

            if content_len <= alloc:
                result[section.name] = section.content
                remaining_budget -= content_len
            else:
                if alloc > 20:
                    result[section.name] = section.content[:alloc] + "\n... [truncated]"
                else:
                    result[section.name] = ""
                remaining_budget = max(0, remaining_budget - alloc)

        return result


def _priority_weight(priority: int) -> float:
    """Higher priority (lower number) -> higher weight."""
    return max(1.0, 6.0 - priority)
