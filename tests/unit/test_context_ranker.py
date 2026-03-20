"""Tests for ContextRanker (R5)."""

from __future__ import annotations

from spec_orch.services.context_ranker import ContextRanker, RankedSection


def test_all_content_fits() -> None:
    sections = [
        RankedSection("arch", "Architecture notes", priority=1),
        RankedSection("tools", "Tool output", priority=5),
    ]
    result = ContextRanker.allocate(sections, total_budget_tokens=1000)
    assert result["arch"] == "Architecture notes"
    assert result["tools"] == "Tool output"


def test_priority_preserves_important_content() -> None:
    important = "A" * 100
    unimportant = "B" * 100
    sections = [
        RankedSection("arch", important, priority=1),
        RankedSection("tools", unimportant, priority=5),
    ]
    result = ContextRanker.allocate(sections, total_budget_tokens=30)
    assert result["arch"] == important
    assert len(result.get("tools", "")) < len(unimportant)


def test_empty_sections() -> None:
    result = ContextRanker.allocate([], total_budget_tokens=1000)
    assert result == {}


def test_single_section_gets_full_budget() -> None:
    content = "X" * 200
    sections = [RankedSection("only", content, priority=3)]
    result = ContextRanker.allocate(sections, total_budget_tokens=100)
    assert result["only"] == content


def test_single_section_truncated() -> None:
    content = "X" * 500
    sections = [RankedSection("only", content, priority=3)]
    result = ContextRanker.allocate(sections, total_budget_tokens=50)
    assert "[truncated]" in result["only"]
    assert len(result["only"]) < len(content)


def test_three_priority_levels() -> None:
    sections = [
        RankedSection("high", "H" * 80, priority=1),
        RankedSection("mid", "M" * 80, priority=3),
        RankedSection("low", "L" * 80, priority=5),
    ]
    result = ContextRanker.allocate(sections, total_budget_tokens=40)
    assert len(result.get("high", "")) >= len(result.get("mid", ""))
    assert len(result.get("mid", "")) >= len(result.get("low", ""))
