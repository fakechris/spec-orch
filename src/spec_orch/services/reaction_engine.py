from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class ReactionRule:
    name: str
    trigger: str
    action: str
    enabled: bool = True
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ReactionDecision:
    rule_name: str
    action: str
    reason: str
    params: dict[str, Any] = field(default_factory=dict)


KNOWN_TRIGGERS = frozenset({"ci_failed", "changes_requested", "approved_and_green"})
KNOWN_ACTIONS = frozenset(
    {
        "comment_ci_failed",
        "comment_changes_requested",
        "auto_merge",
        "requeue_ready",
        "noop",
    }
)


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


def interpolate_template(template: str, context: dict[str, Any]) -> str:
    """Replace ``{key}`` placeholders only for keys present in *context*.

    Unknown placeholders are left unchanged to avoid accidental ``str.format``
    evaluation of user-controlled strings.
    """
    out = template
    for key, value in context.items():
        if not isinstance(key, str):
            continue
        token = "{" + key + "}"
        if token in out:
            out = out.replace(token, str(value))
    return out


def parse_reactions_yaml(raw: dict[str, Any]) -> tuple[list[ReactionRule], list[str]]:
    """Parse ``reactions`` list; return rules and validation warnings."""
    errors: list[str] = []
    rules: list[ReactionRule] = []
    items = raw.get("reactions", [])
    if not isinstance(items, list):
        errors.append("reactions must be a list")
        return rules, errors

    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"reactions[{idx}] must be a mapping")
            continue
        name = str(item.get("name", "")).strip()
        trigger = str(item.get("trigger", "")).strip()
        action = str(item.get("action", "")).strip()
        if not name or not trigger or not action:
            errors.append(f"reactions[{idx}]: name, trigger, and action are required")
            continue
        if trigger not in KNOWN_TRIGGERS:
            errors.append(
                f"reactions[{idx}] ({name}): unknown trigger {trigger!r}; "
                f"expected one of {sorted(KNOWN_TRIGGERS)}"
            )
        if action not in KNOWN_ACTIONS:
            errors.append(
                f"reactions[{idx}] ({name}): unknown action {action!r}; "
                f"expected one of {sorted(KNOWN_ACTIONS)}"
            )
        raw_params = item.get("params")
        params: dict[str, Any] = {}
        if raw_params is not None:
            if not isinstance(raw_params, dict):
                errors.append(f"reactions[{idx}] ({name}): params must be a mapping")
                continue
            params = dict(raw_params)

        rules.append(
            ReactionRule(
                name=name,
                trigger=trigger,
                action=action,
                enabled=bool(item.get("enabled", True)),
                params=params,
            )
        )
    return rules, errors


def validate_reactions_file(path: Path) -> list[str]:
    """Validate a reactions recipe file; return human-readable issues."""
    issues: list[str] = []
    if not path.exists():
        return [f"file not found: {path}"]
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except (yaml.YAMLError, OSError) as exc:
        return [f"failed to read YAML: {exc}"]
    if not isinstance(raw, dict):
        return ["root must be a mapping"]
    _rules, errs = parse_reactions_yaml(raw)
    issues.extend(errs)
    return issues


class ReactionEngine:
    """Evaluate PR signals and return reaction actions."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.load_warnings: list[str] = []
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
                        params=dict(rule.params),
                    )
                )
        return decisions

    def _load_rules(self) -> list[ReactionRule]:
        self.load_warnings = []
        recipe_path = self.repo_root / ".spec_orch" / "reactions.yaml"
        if not recipe_path.exists():
            return list(DEFAULT_RULES)
        try:
            raw = yaml.safe_load(recipe_path.read_text()) or {}
        except (yaml.YAMLError, OSError) as exc:
            self.load_warnings.append(f"reactions.yaml unreadable: {exc}")
            return list(DEFAULT_RULES)
        if not isinstance(raw, dict):
            self.load_warnings.append("reactions.yaml root must be a mapping")
            return list(DEFAULT_RULES)
        rules, errs = parse_reactions_yaml(raw)
        self.load_warnings.extend(errs)
        if rules:
            return rules
        if errs:
            self.load_warnings.append("no valid rules; falling back to defaults")
        return list(DEFAULT_RULES)

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
