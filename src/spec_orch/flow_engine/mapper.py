"""FlowMapper — resolve Intent + issue metadata to a FlowType."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from spec_orch.domain.models import FlowType

logger = logging.getLogger(__name__)

_DEFAULT_RULES: dict[str, str] = {
    "feature": "full",
    "architecture": "full",
    "bug": "standard",
    "improvement": "standard",
    "quick_fix": "standard",
    "documentation": "standard",
    "hotfix": "hotfix",
    "security": "hotfix",
}

_LABEL_OVERRIDES: dict[str, str] = {
    "hotfix": "hotfix",
}


class FlowMapper:
    """Map intent categories and issue metadata to FlowType.

    Supports YAML-based configuration with label-level overrides.
    """

    def __init__(
        self,
        rules: dict[str, str] | None = None,
        label_overrides: dict[str, str] | None = None,
    ) -> None:
        self._rules = rules or dict(_DEFAULT_RULES)
        self._label_overrides = label_overrides or dict(_LABEL_OVERRIDES)

    @classmethod
    def from_yaml(cls, path: Path) -> FlowMapper:
        import yaml

        with open(path) as f:
            data: dict[str, Any] = yaml.safe_load(f) or {}
        rules = data.get("intent_to_flow", {})
        overrides = data.get("label_overrides", {})
        return cls(rules=rules, label_overrides=overrides)

    def resolve_flow_type(
        self,
        intent: str | None = None,
        *,
        labels: list[str] | None = None,
        run_class: str | None = None,
    ) -> FlowType | None:
        """Resolve to a FlowType.  Returns None if intent is non-actionable."""
        for label in labels or []:
            override = self._label_overrides.get(label.lower())
            if override:
                try:
                    return FlowType(override)
                except ValueError:
                    logger.warning("Invalid override flow %r for label %r", override, label)

        key = (intent or run_class or "").lower()
        if not key:
            return None

        mapped = self._rules.get(key)
        if mapped:
            try:
                return FlowType(mapped)
            except ValueError:
                logger.warning("Invalid flow %r for key %r", mapped, key)
                return None

        return None
