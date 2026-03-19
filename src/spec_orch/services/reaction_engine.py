from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class ReactionRule:
    name: str
    trigger: str
    action: str
    enabled: bool = True


@dataclass(slots=True)
class ReactionDecision:
    rule_name: str
    action: str
    reason: str


DEFAULT_RULES = [
    ReactionRule(
        name="ci-failed",
        trigger="ci_failed",
        action="comment_ci_failed",
    ),
    ReactionRule(
        name="changes-requested",
        trigger="changes_requested",
        action="comment_changes_requested",
    ),
    ReactionRule(
        name="approved-and-green",
        trigger="approved_and_green",
        action="auto_merge",
    ),
]


class ReactionEngine:
    """Evaluate PR signals and return reaction actions."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.rules = self._load_rules()

    def evaluate(self, signal: dict[str, Any]) -> list[ReactionDecision]:
        decisions: list[ReactionDecision] = []
        for rule in self.rules:
            if not rule.enabled:
                continue
            if self._matches(rule.trigger, signal):
                decisions.append(
                    ReactionDecision(
                        rule_name=rule.name,
                        action=rule.action,
                        reason=f"trigger={rule.trigger}",
                    )
                )
        return decisions

    def _load_rules(self) -> list[ReactionRule]:
        recipe_path = self.repo_root / ".spec_orch" / "reactions.yaml"
        if not recipe_path.exists():
            return list(DEFAULT_RULES)
        try:
            raw = yaml.safe_load(recipe_path.read_text()) or {}
        except (yaml.YAMLError, OSError):
            return list(DEFAULT_RULES)
        items = raw.get("reactions", [])
        rules: list[ReactionRule] = []
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "")).strip()
                trigger = str(item.get("trigger", "")).strip()
                action = str(item.get("action", "")).strip()
                if not name or not trigger or not action:
                    continue
                rules.append(
                    ReactionRule(
                        name=name,
                        trigger=trigger,
                        action=action,
                        enabled=bool(item.get("enabled", True)),
                    )
                )
        return rules or list(DEFAULT_RULES)

    @staticmethod
    def _matches(trigger: str, signal: dict[str, Any]) -> bool:
        review_decision = str(signal.get("review_decision", "")).upper()
        checks_passed = bool(signal.get("checks_passed", False))
        checks_failed = bool(signal.get("checks_failed", False))
        mergeable = bool(signal.get("mergeable", False))
        if trigger == "ci_failed":
            return checks_failed
        if trigger == "changes_requested":
            return review_decision == "CHANGES_REQUESTED"
        if trigger == "approved_and_green":
            return review_decision == "APPROVED" and checks_passed and mergeable
        return False
