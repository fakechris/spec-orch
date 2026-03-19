"""IntentEvolver — improve Conductor intent classifier from historical evidence.

Reads Episodic Memory for ``intent-classified`` and ``flow-promotion`` /
``flow-demotion`` events, identifies mis-classification patterns, and uses
an LLM to propose improved classifier prompts.  Follows the same
load_history / evolve / ab_test / promote pattern as PromptEvolver.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spec_orch.domain.context import ContextBundle

logger = logging.getLogger(__name__)

_HISTORY_FILE = "classifier_prompt_history.json"
_EVOLUTION_DIR = ".spec_orch_evolution"

_EVOLVE_SYSTEM_PROMPT = """\
You are a prompt-engineering specialist for an AI intent classifier.

Given the current classifier prompt, misclassification statistics, and
promotion/demotion event correlations, propose an improved prompt that
reduces the observed error patterns.

Requirements:
- Keep the same output JSON schema (category, confidence, summary, reasoning).
- Focus changes on disambiguation rules for the most frequent errors.
- Explain your reasoning in a brief rationale.

Respond with ONLY a JSON object:
{
  "variant_id": "v<next_number>",
  "prompt_text": "the full improved prompt",
  "rationale": "brief explanation",
  "target_improvements": ["list of expected improvements"]
}
"""


@dataclass
class ClassifierVariant:
    variant_id: str
    prompt_text: str
    created_at: str = ""
    rationale: str = ""
    total_runs: int = 0
    successful_runs: int = 0
    is_active: bool = False
    is_candidate: bool = False
    target_improvements: list[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.total_runs == 0:
            return 0.0
        return self.successful_runs / self.total_runs


class IntentEvolver:
    """Evolves the Conductor's intent classifier prompt."""

    MIN_ENTRIES_FOR_EVOLVE = 10

    def __init__(self, repo_root: Path, planner: Any | None = None) -> None:
        self._repo_root = repo_root
        self._planner = planner
        self._evo_dir = repo_root / _EVOLUTION_DIR
        self._evo_dir.mkdir(parents=True, exist_ok=True)
        self._history_path = self._evo_dir / _HISTORY_FILE

    def load_history(self) -> list[ClassifierVariant]:
        if not self._history_path.exists():
            return []
        try:
            data = json.loads(self._history_path.read_text())
        except (json.JSONDecodeError, OSError):
            logger.warning("Could not read classifier prompt history")
            return []
        if not isinstance(data, list):
            return []
        variants: list[ClassifierVariant] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            try:
                variants.append(
                    ClassifierVariant(
                        variant_id=item["variant_id"],
                        prompt_text=item["prompt_text"],
                        created_at=item.get("created_at", ""),
                        rationale=item.get("rationale", ""),
                        total_runs=item.get("total_runs", 0),
                        successful_runs=item.get("successful_runs", 0),
                        is_active=item.get("is_active", False),
                        is_candidate=item.get("is_candidate", False),
                        target_improvements=item.get("target_improvements", []),
                    )
                )
            except (KeyError, TypeError):
                continue
        return variants

    def save_history(self, variants: list[ClassifierVariant]) -> None:
        self._history_path.write_text(
            json.dumps([asdict(v) for v in variants], indent=2, ensure_ascii=False) + "\n"
        )

    def get_active(self) -> ClassifierVariant | None:
        for v in self.load_history():
            if v.is_active:
                return v
        return None

    def recall_intent_logs(self) -> list[dict[str, Any]]:
        """Fetch intent classification logs from Episodic Memory."""
        try:
            from spec_orch.services.memory.service import get_memory_service
            from spec_orch.services.memory.types import MemoryLayer, MemoryQuery

            svc = get_memory_service(repo_root=self._repo_root)
            entries = svc.recall(
                MemoryQuery(layer=MemoryLayer.EPISODIC, tags=["intent-classified"])
            )
            return [e.metadata for e in entries if e.metadata]
        except ImportError:
            return []

    def recall_flow_events(self) -> list[dict[str, Any]]:
        """Fetch promotion/demotion events from Episodic Memory."""
        try:
            from spec_orch.services.memory.service import get_memory_service
            from spec_orch.services.memory.types import MemoryLayer, MemoryQuery

            svc = get_memory_service(repo_root=self._repo_root)
            promos = svc.recall(MemoryQuery(layer=MemoryLayer.EPISODIC, tags=["flow-promotion"]))
            demos = svc.recall(MemoryQuery(layer=MemoryLayer.EPISODIC, tags=["flow-demotion"]))
            return [e.metadata for e in promos + demos if e.metadata]
        except ImportError:
            return []

    def compute_error_patterns(self) -> dict[str, Any]:
        """Analyse intent logs + flow events and return error statistics."""
        logs = self.recall_intent_logs()
        if not logs:
            return {}
        category_counts: Counter[str] = Counter()
        for log in logs:
            cat = log.get("intent_category", "unknown")
            category_counts[cat] += 1

        flow_events = self.recall_flow_events()
        promotion_intents: Counter[str] = Counter()
        demotion_intents: Counter[str] = Counter()
        for ev in flow_events:
            trigger = ev.get("trigger", "")
            intent = ev.get("intent_category", "unknown")
            if "promotion" in trigger:
                promotion_intents[intent] += 1
            elif "demotion" in trigger:
                demotion_intents[intent] += 1

        return {
            "total_classifications": len(logs),
            "category_distribution": dict(category_counts),
            "promotion_correlations": dict(promotion_intents),
            "demotion_correlations": dict(demotion_intents),
        }

    def evolve(self, context: ContextBundle | None = None) -> ClassifierVariant | None:
        """Use LLM to propose an improved classifier prompt."""
        if self._planner is None:
            logger.info("No planner configured, skipping intent evolution")
            return None

        patterns = self.compute_error_patterns()
        if not patterns or patterns.get("total_classifications", 0) < self.MIN_ENTRIES_FOR_EVOLVE:
            logger.info(
                "Not enough intent data for evolution (%s entries)",
                patterns.get("total_classifications", 0),
            )
            return None

        active = self.get_active()
        current_prompt = active.prompt_text if active else "(no active prompt)"

        user_msg = (
            f"Current classifier prompt:\n{current_prompt}\n\n"
            f"Error patterns:\n{json.dumps(patterns, indent=2)}\n\n"
            f"Propose an improved version."
        )

        try:
            text = self._planner.chat_completion(
                system_prompt=_EVOLVE_SYSTEM_PROMPT,
                user_prompt=user_msg,
            )
            data = json.loads(text)
        except Exception:
            logger.warning("LLM call for intent evolution failed", exc_info=True)
            return None

        history = self.load_history()
        next_id = f"v{len(history)}"
        variant = ClassifierVariant(
            variant_id=data.get("variant_id", next_id),
            prompt_text=data.get("prompt_text", ""),
            rationale=data.get("rationale", ""),
            created_at=datetime.now(UTC).isoformat(),
            is_candidate=True,
            target_improvements=data.get("target_improvements", []),
        )
        history.append(variant)
        self.save_history(history)
        return variant

    def promote(self, variant_id: str) -> bool:
        history = self.load_history()
        target = None
        for v in history:
            if v.variant_id == variant_id:
                target = v
                break
        if target is None:
            return False
        for v in history:
            v.is_active = False
            v.is_candidate = False
        target.is_active = True
        self.save_history(history)
        return True
