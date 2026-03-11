from __future__ import annotations

import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

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
