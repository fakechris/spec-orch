"""FlowPolicyEvolver — adjust flow selection thresholds from promotion/demotion evidence.

Reads Episodic Memory for ``flow-promotion`` / ``flow-demotion`` events and
the current ``flow_mapping.yaml``, analyses patterns, and produces threshold
adjustment suggestions.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_EVOLUTION_DIR = ".spec_orch_evolution"
_SUGGESTIONS_FILE = "flow_policy_suggestions.json"


@dataclass
class FlowPolicySuggestion:
    intent_category: str
    current_flow: str
    suggested_flow: str
    confidence_min: float = 0.0
    change_threshold: int = 0
    rationale: str = ""
    event_count: int = 0


@dataclass
class FlowPolicyEvolveResult:
    suggestions: list[FlowPolicySuggestion] = field(default_factory=list)
    total_events_analysed: int = 0
    created_at: str = ""


class FlowPolicyEvolver:
    """Produces flow mapping threshold suggestions from historical evidence."""

    MIN_EVENTS_FOR_EVOLVE = 5

    def __init__(self, repo_root: Path, planner: Any | None = None) -> None:
        self._repo_root = repo_root
        self._planner = planner
        self._evo_dir = repo_root / _EVOLUTION_DIR
        self._evo_dir.mkdir(parents=True, exist_ok=True)
        self._suggestions_path = self._evo_dir / _SUGGESTIONS_FILE

    def load_flow_mapping(self) -> dict[str, Any]:
        mapping_path = self._repo_root / "src" / "spec_orch" / "flow_mapping.yaml"
        if not mapping_path.exists():
            logger.warning("flow_mapping.yaml not found, using empty mapping")
            return {}
        try:
            return yaml.safe_load(mapping_path.read_text()) or {}
        except Exception:
            logger.warning("Failed to read flow_mapping.yaml", exc_info=True)
            return {}

    def recall_flow_events(self) -> list[dict[str, Any]]:
        try:
            from spec_orch.services.memory.service import get_memory_service
            from spec_orch.services.memory.types import MemoryLayer, MemoryQuery

            svc = get_memory_service(repo_root=self._repo_root)
            promos = svc.recall(MemoryQuery(layer=MemoryLayer.EPISODIC, tags=["flow-promotion"]))
            demos = svc.recall(MemoryQuery(layer=MemoryLayer.EPISODIC, tags=["flow-demotion"]))
            return [e.metadata for e in promos + demos if e.metadata]
        except ImportError:
            return []

    def analyse_patterns(self) -> dict[str, Any]:
        events = self.recall_flow_events()
        if not events:
            return {}

        promotion_by_intent: Counter[str] = Counter()
        demotion_by_intent: Counter[str] = Counter()

        for ev in events:
            intent = ev.get("intent_category", "unknown")
            trigger = ev.get("trigger", "")
            if "promotion" in trigger:
                promotion_by_intent[intent] += 1
            elif "demotion" in trigger:
                demotion_by_intent[intent] += 1

        return {
            "total_events": len(events),
            "promotions_by_intent": dict(promotion_by_intent),
            "demotions_by_intent": dict(demotion_by_intent),
        }

    def evolve(self) -> FlowPolicyEvolveResult | None:
        """Analyse flow events and produce threshold suggestions."""
        patterns = self.analyse_patterns()
        total = patterns.get("total_events", 0)
        if total < self.MIN_EVENTS_FOR_EVOLVE:
            logger.info("Not enough flow events for evolution (%d)", total)
            return None

        mapping = self.load_flow_mapping()
        intent_to_flow = mapping.get("intent_to_flow", {})

        suggestions: list[FlowPolicySuggestion] = []
        promotions = patterns.get("promotions_by_intent", {})
        for intent, count in promotions.items():
            if count < 2:
                continue
            current = intent_to_flow.get(intent, "standard")
            suggested = "full" if current != "full" else current
            if suggested != current:
                suggestions.append(
                    FlowPolicySuggestion(
                        intent_category=intent,
                        current_flow=current,
                        suggested_flow=suggested,
                        rationale=f"{count} promotions detected — consider upgrading default flow",
                        event_count=count,
                    )
                )

        demotions = patterns.get("demotions_by_intent", {})
        for intent, count in demotions.items():
            if count < 2:
                continue
            current = intent_to_flow.get(intent, "standard")
            suggested = (
                "hotfix" if current == "standard" else "standard" if current == "full" else current
            )
            if suggested != current:
                suggestions.append(
                    FlowPolicySuggestion(
                        intent_category=intent,
                        current_flow=current,
                        suggested_flow=suggested,
                        rationale=f"{count} demotions detected — consider downgrading default flow",
                        event_count=count,
                    )
                )

        result = FlowPolicyEvolveResult(
            suggestions=suggestions,
            total_events_analysed=total,
            created_at=datetime.now(UTC).isoformat(),
        )
        self._save_suggestions(result)
        return result

    def _save_suggestions(self, result: FlowPolicyEvolveResult) -> None:
        data = {
            "total_events_analysed": result.total_events_analysed,
            "created_at": result.created_at,
            "suggestions": [asdict(s) for s in result.suggestions],
        }
        self._suggestions_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    def load_suggestions(self) -> FlowPolicyEvolveResult | None:
        if not self._suggestions_path.exists():
            return None
        try:
            data = json.loads(self._suggestions_path.read_text())
            return FlowPolicyEvolveResult(
                suggestions=[FlowPolicySuggestion(**s) for s in data.get("suggestions", [])],
                total_events_analysed=data.get("total_events_analysed", 0),
                created_at=data.get("created_at", ""),
            )
        except (json.JSONDecodeError, TypeError):
            return None
