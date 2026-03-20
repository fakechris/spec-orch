"""LLM-based intent classification for the Conductor.

Classifies each user message into one of the ``IntentCategory`` values
and returns a confidence score, summary, and optional suggested title.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from spec_orch.services.conductor.types import IntentCategory, IntentSignal

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are an intent classifier for a software engineering orchestration system.

Given a user message (and optionally recent conversation history), classify
the user's PRIMARY intent into exactly one category:

- exploration: Thinking aloud, brainstorming, "what if we...", vague ideas
- question: Asking how something works, requesting information
- quick_fix: A small, concrete fix (typo, config tweak, rename) that needs no planning
- feature: A concrete feature request or enhancement
- bug: Reporting a bug or broken behavior
- drift: The user changed topic from what was being discussed

Respond with a JSON object (no markdown fences):
{
  "category": "<one of the categories above>",
  "confidence": <float 0.0-1.0>,
  "summary": "<1-sentence summary of what the user wants>",
  "suggested_title": "<short issue title if category is feature/bug/quick_fix, else empty>",
  "reasoning": "<brief reasoning for your classification>"
}
"""


def classify_intent(
    message: str,
    *,
    conversation_history: list[dict[str, str]] | None = None,
    planner: Any | None = None,
    context: Any | None = None,
) -> IntentSignal:
    """Classify a user message's intent.

    If *planner* is provided (any object with a ``chat_completion`` or
    ``brainstorm``-compatible method), uses the LLM. Otherwise falls back
    to rule-based heuristics.

    *context* is an optional ``ContextBundle`` that enriches the LLM
    prompt with task constraints and execution facts.
    """
    if planner is not None and hasattr(planner, "chat_completion"):
        return _llm_classify(message, conversation_history or [], planner, context)
    logger.warning("FALLBACK [IntentClassifier]: llm → rules — no planner available")
    try:
        from spec_orch.services.event_bus import get_event_bus

        get_event_bus().emit_fallback(
            component="IntentClassifier",
            primary="llm_classification",
            fallback="rule_heuristics",
            reason="No planner adapter with chat_completion",
        )
    except Exception:
        pass
    return _rule_classify(message)


def _llm_classify(
    message: str,
    history: list[dict[str, str]],
    planner: Any,
    context: Any | None = None,
) -> IntentSignal:
    """Use the LLM planner for classification."""
    context_lines = []
    for turn in history[-6:]:
        role = turn.get("role", "user")
        context_lines.append(f"[{role}] {turn.get('content', '')[:200]}")
    context_block = "\n".join(context_lines)

    extra = ""
    if context is not None:
        parts: list[str] = []
        task = getattr(context, "task", None)
        if task:
            issue = getattr(task, "issue", None)
            if issue:
                parts.append(
                    f"Current issue: {getattr(issue, 'title', '')} "
                    f"({getattr(issue, 'issue_id', '')})"
                )
            if getattr(task, "constraints", []):
                parts.append("Constraints: " + "; ".join(task.constraints[:5]))
        learning = getattr(context, "learning", None)
        if learning:
            hints = getattr(learning, "scoper_hints", [])
            if hints:
                parts.append(f"Active scoper hints: {len(hints)}")
        if parts:
            extra = "\n\nOrchestration context:\n" + "\n".join(parts) + "\n"

    user_prompt = (
        f"Recent conversation:\n{context_block}\n{extra}\nNew message to classify:\n{message}"
    )

    try:
        raw: str = planner.chat_completion(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        return _parse_llm_response(raw)
    except Exception:
        logger.debug("LLM classification failed, falling back to rules", exc_info=True)
        return _rule_classify(message)


def _parse_llm_response(raw: str) -> IntentSignal:
    """Parse the JSON response from the LLM."""
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return IntentSignal(
            category=IntentCategory.EXPLORATION,
            confidence=0.3,
            reasoning="Failed to parse LLM response",
        )

    try:
        category = IntentCategory(data.get("category", "exploration"))
    except ValueError:
        category = IntentCategory.EXPLORATION

    return IntentSignal(
        category=category,
        confidence=min(1.0, max(0.0, float(data.get("confidence", 0.5)))),
        summary=data.get("summary", ""),
        suggested_title=data.get("suggested_title", ""),
        reasoning=data.get("reasoning", ""),
    )


# -- Rule-based fallback ----------------------------------------------------

_BUG_PATTERNS = re.compile(
    r"\b(bug|broken|crash|error|fail|fix|issue|wrong|not working|doesn't work)\b",
    re.IGNORECASE,
)
_FEATURE_PATTERNS = re.compile(
    r"\b(add|implement|create|build|need|want|should have|feature|component|module)\b",
    re.IGNORECASE,
)
_QUESTION_PATTERNS = re.compile(
    r"^(how|what|where|why|when|can you explain|tell me)\b|[?]\s*$",
    re.IGNORECASE,
)
_EXPLORE_PATTERNS = re.compile(
    r"\b(think|maybe|what if|wonder|consider|explore|brainstorm|idea)\b",
    re.IGNORECASE,
)
_QUICK_FIX_PATTERNS = re.compile(
    r"\b(typo|rename|tweak|change|update|config|small)\b",
    re.IGNORECASE,
)


def _rule_classify(message: str) -> IntentSignal:
    """Simple pattern-matching fallback when no LLM is available."""
    msg = message.strip()

    if _QUESTION_PATTERNS.search(msg):
        return IntentSignal(
            category=IntentCategory.QUESTION,
            confidence=0.6,
            summary=msg[:100],
            reasoning="Pattern match: question markers",
        )

    if _BUG_PATTERNS.search(msg) and len(msg) > 20:
        return IntentSignal(
            category=IntentCategory.BUG,
            confidence=0.55,
            summary=msg[:100],
            suggested_title=msg[:60],
            reasoning="Pattern match: bug-related keywords",
        )

    if _QUICK_FIX_PATTERNS.search(msg) and len(msg) < 100:
        return IntentSignal(
            category=IntentCategory.QUICK_FIX,
            confidence=0.5,
            summary=msg[:100],
            suggested_title=msg[:60],
            reasoning="Pattern match: small-change keywords + short message",
        )

    if _FEATURE_PATTERNS.search(msg) and len(msg) > 30:
        return IntentSignal(
            category=IntentCategory.FEATURE,
            confidence=0.55,
            summary=msg[:100],
            suggested_title=msg[:60],
            reasoning="Pattern match: feature-related keywords",
        )

    if _EXPLORE_PATTERNS.search(msg):
        return IntentSignal(
            category=IntentCategory.EXPLORATION,
            confidence=0.6,
            summary=msg[:100],
            reasoning="Pattern match: exploratory language",
        )

    return IntentSignal(
        category=IntentCategory.EXPLORATION,
        confidence=0.4,
        summary=msg[:100],
        reasoning="No strong pattern match, defaulting to exploration",
    )
