"""Compliance checking for builder agents.

This module has two layers:

1. **ComplianceEngine** (vendor-neutral): evaluates a sequence of
   ``BuilderEvent`` objects against configurable rules.  The orchestrator
   and gate use this exclusively.

2. **Codex-specific helpers** (``evaluate_pre_action_narration_compliance``
   etc.): operate on raw Codex JSONL events.  These are retained for
   backward compatibility and are called inside
   ``CodexExecBuilderAdapter`` which maps Codex events into
   ``BuilderEvent`` before forwarding to the engine.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from spec_orch.domain.models import BuilderEvent

# ---------------------------------------------------------------------------
# ComplianceEngine: vendor-neutral
# ---------------------------------------------------------------------------

ComplianceRule = Callable[[Sequence[BuilderEvent]], list[dict[str, Any]]]


class ComplianceEngine:
    """Evaluate builder events against a set of compliance rules.

    Rules are callables that receive a sequence of ``BuilderEvent`` and
    return a (possibly empty) list of violation dicts.
    """

    def __init__(self, rules: list[ComplianceRule] | None = None) -> None:
        self._rules: list[ComplianceRule] = rules or [
            pre_action_narration_rule,
        ]

    def register(self, rule: ComplianceRule) -> None:
        self._rules.append(rule)

    def evaluate(
        self,
        events: Sequence[BuilderEvent],
    ) -> dict[str, Any]:
        all_violations: list[dict[str, Any]] = []
        first_action = _find_first_action(events)
        for rule in self._rules:
            all_violations.extend(rule(events))
        return {
            "compliant": not all_violations,
            "first_action_seen": first_action is not None,
            "first_action_kind": first_action.kind if first_action else None,
            "first_action_text": first_action.text if first_action else None,
            "violations": all_violations,
        }


def _find_first_action(events: Sequence[BuilderEvent]) -> BuilderEvent | None:
    for evt in events:
        if evt.kind in ("command_start", "file_change"):
            return evt
    return None


def pre_action_narration_rule(
    events: Sequence[BuilderEvent],
) -> list[dict[str, Any]]:
    """Flag message events before the first concrete action that contain
    planning/narration language."""
    violations: list[dict[str, Any]] = []
    for evt in events:
        if evt.kind in ("command_start", "file_change"):
            break
        if evt.kind != "message" or not evt.text.strip():
            continue
        pattern = _matching_pre_action_pattern(evt.text)
        if pattern:
            violations.append(
                {
                    "timestamp": evt.timestamp,
                    "kind": evt.kind,
                    "text": evt.text,
                    "pattern": pattern.pattern,
                }
            )
    return violations


# ---------------------------------------------------------------------------
# Legacy Codex-specific helpers (kept for backward compatibility)
# ---------------------------------------------------------------------------

PRE_ACTION_NARRATION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bskill\b", re.IGNORECASE),
    re.compile(r"\bplan\b", re.IGNORECASE),
    re.compile(r"\bplanning process\b", re.IGNORECASE),
    re.compile(r"\bapproach\b", re.IGNORECASE),
    re.compile(r"\bI will\b", re.IGNORECASE),
    re.compile(r"\bI['\u2019]m going to\b", re.IGNORECASE),
    re.compile(r"\bI['\u2019]ve read\b", re.IGNORECASE),
    re.compile(r"\bFirst I will\b", re.IGNORECASE),
)


def default_turn_contract_compliance() -> dict[str, Any]:
    return {
        "compliant": True,
        "first_action_seen": False,
        "first_action_method": None,
        "first_action_excerpt": None,
        "violations": [],
    }


def evaluate_pre_action_narration_compliance(
    incoming_events: Path | Sequence[dict[str, Any]],
) -> dict[str, Any]:
    if isinstance(incoming_events, Path):
        if not incoming_events.exists():
            return default_turn_contract_compliance()
        events = [
            json.loads(line)
            for line in incoming_events.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    else:
        events = list(incoming_events)

    first_action_method: str | None = None
    first_action_excerpt: str | None = None
    violations: list[dict[str, Any]] = []

    for event in events:
        method = event.get("method")
        excerpt = event.get("excerpt")
        if _is_first_concrete_action_event(method=method, excerpt=excerpt):
            first_action_method = method
            first_action_excerpt = excerpt
            break
        if method != "item/agentMessage/delta":
            continue
        if not isinstance(excerpt, str) or not excerpt.strip():
            continue
        pattern = _matching_pre_action_pattern(excerpt)
        if pattern is None:
            continue
        violations.append(
            {
                "observed_at": event.get("observed_at"),
                "method": method,
                "excerpt": excerpt,
                "pattern": pattern.pattern,
            }
        )

    return {
        "compliant": not violations,
        "first_action_seen": first_action_method is not None,
        "first_action_method": first_action_method,
        "first_action_excerpt": first_action_excerpt,
        "violations": violations,
    }


def _is_first_concrete_action_event(*, method: str | None, excerpt: str | None) -> bool:
    if method == "codex/event/exec_command_begin":
        return True
    if method == "item/started" and isinstance(excerpt, str):
        return excerpt.startswith("commandExecution:")
    return False


def _matching_pre_action_pattern(excerpt: str) -> re.Pattern[str] | None:
    for pattern in PRE_ACTION_NARRATION_PATTERNS:
        if pattern.search(excerpt):
            return pattern
    return None
