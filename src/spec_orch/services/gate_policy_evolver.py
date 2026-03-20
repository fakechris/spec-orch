"""GatePolicyEvolver — detect false positive/negative patterns and suggest gate policy changes.

Reads Episodic Memory for ``gate-verdict`` entries plus downstream results
(merge outcomes from ``issue-result``), identifies false positive/negative
patterns, and produces YAML-compatible gate policy suggestions.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spec_orch.services.io import atomic_write_json

logger = logging.getLogger(__name__)

_EVOLUTION_DIR = ".spec_orch_evolution"
_SUGGESTIONS_FILE = "gate_policy_suggestions.json"


@dataclass
class GatePolicySuggestion:
    suggestion_type: str  # "add_rule" | "adjust_severity" | "add_condition"
    condition: str = ""
    rationale: str = ""
    source_issues: list[str] = field(default_factory=list)
    confidence: str = "medium"


@dataclass
class GatePolicyEvolveResult:
    suggestions: list[GatePolicySuggestion] = field(default_factory=list)
    false_positives: int = 0
    false_negatives: int = 0
    total_verdicts: int = 0
    created_at: str = ""


class GatePolicyEvolver:
    """Produces gate policy suggestions from historical verdict + outcome data."""

    MIN_VERDICTS_FOR_EVOLVE = 5
    _FP_CONFIDENCE_THRESHOLD = 3
    _MAX_SOURCE_ISSUES = 10
    _FN_CONDITION_THRESHOLD = 3

    def __init__(self, repo_root: Path, planner: Any | None = None) -> None:
        self._repo_root = repo_root
        self._planner = planner
        self._evo_dir = repo_root / _EVOLUTION_DIR
        self._evo_dir.mkdir(parents=True, exist_ok=True)
        self._suggestions_path = self._evo_dir / _SUGGESTIONS_FILE

    def recall_gate_verdicts(self) -> list[dict[str, Any]]:
        try:
            from spec_orch.services.memory.service import get_memory_service
            from spec_orch.services.memory.types import MemoryLayer, MemoryQuery

            svc = get_memory_service(repo_root=self._repo_root)
            entries = svc.recall(MemoryQuery(layer=MemoryLayer.EPISODIC, tags=["gate-verdict"]))
            return [e.metadata for e in entries if e.metadata]
        except ImportError:
            return []

    def recall_issue_outcomes(self) -> dict[str, dict[str, Any]]:
        """Map issue_id → outcome metadata from issue-result entries."""
        try:
            from spec_orch.services.memory.service import get_memory_service
            from spec_orch.services.memory.types import MemoryLayer, MemoryQuery

            svc = get_memory_service(repo_root=self._repo_root)
            entries = svc.recall(MemoryQuery(layer=MemoryLayer.EPISODIC, tags=["issue-result"]))
            return {
                e.metadata.get("issue_id", ""): e.metadata
                for e in entries
                if e.metadata and e.metadata.get("issue_id")
            }
        except ImportError:
            return {}

    def detect_false_patterns(self) -> dict[str, Any]:
        verdicts = self.recall_gate_verdicts()
        outcomes = self.recall_issue_outcomes()
        if not verdicts:
            return {}

        false_positives: list[str] = []
        false_negatives: list[str] = []
        failed_condition_counts: Counter[str] = Counter()
        fn_failed_conditions: Counter[str] = Counter()

        for v in verdicts:
            issue_id = v.get("issue_id", "")
            passed = v.get("passed", False)
            outcome = outcomes.get(issue_id, {})
            succeeded_downstream = outcome.get("succeeded", None)

            if passed and succeeded_downstream is False:
                false_positives.append(issue_id)
            elif not passed and succeeded_downstream is True:
                false_negatives.append(issue_id)
                for cond in v.get("failed_conditions", []):
                    fn_failed_conditions[cond] += 1

            for cond in v.get("failed_conditions", []):
                failed_condition_counts[cond] += 1

        return {
            "total_verdicts": len(verdicts),
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "failed_condition_frequency": dict(failed_condition_counts),
            "fn_failed_conditions": dict(fn_failed_conditions),
        }

    def evolve(self, *, context: Any | None = None) -> GatePolicyEvolveResult | None:
        """Analyse gate verdicts and produce policy suggestions."""
        patterns = self.detect_false_patterns()
        total = patterns.get("total_verdicts", 0)
        if total < self.MIN_VERDICTS_FOR_EVOLVE:
            logger.info("Not enough gate verdicts for evolution (%d)", total)
            return None

        suggestions: list[GatePolicySuggestion] = []
        fp_issues = patterns.get("false_positives", [])
        fn_issues = patterns.get("false_negatives", [])

        if fp_issues:
            suggestions.append(
                GatePolicySuggestion(
                    suggestion_type="add_condition",
                    condition="regression_check",
                    rationale=(
                        f"{len(fp_issues)} issues passed gate but failed downstream — "
                        "consider adding post-merge regression verification"
                    ),
                    source_issues=fp_issues[: self._MAX_SOURCE_ISSUES],
                    confidence="high"
                    if len(fp_issues) >= self._FP_CONFIDENCE_THRESHOLD
                    else "medium",
                )
            )

        fn_conds: dict[str, int] = patterns.get("fn_failed_conditions", {})
        for cond, count in fn_conds.items():
            if count >= self._FN_CONDITION_THRESHOLD:
                suggestions.append(
                    GatePolicySuggestion(
                        suggestion_type="adjust_severity",
                        condition=cond,
                        rationale=(
                            f"Condition '{cond}' failed {count} times but overrides succeeded"
                        ),
                        confidence="medium",
                    )
                )

        result = GatePolicyEvolveResult(
            suggestions=suggestions,
            false_positives=len(fp_issues),
            false_negatives=len(fn_issues),
            total_verdicts=total,
            created_at=datetime.now(UTC).isoformat(),
        )
        self._save_suggestions(result)
        return result

    def _save_suggestions(self, result: GatePolicyEvolveResult) -> None:
        data = {
            "total_verdicts": result.total_verdicts,
            "false_positives": result.false_positives,
            "false_negatives": result.false_negatives,
            "created_at": result.created_at,
            "suggestions": [asdict(s) for s in result.suggestions],
        }
        atomic_write_json(self._suggestions_path, data)

    def load_suggestions(self) -> GatePolicyEvolveResult | None:
        if not self._suggestions_path.exists():
            return None
        try:
            data = json.loads(self._suggestions_path.read_text())
            return GatePolicyEvolveResult(
                suggestions=[GatePolicySuggestion(**s) for s in data.get("suggestions", [])],
                false_positives=data.get("false_positives", 0),
                false_negatives=data.get("false_negatives", 0),
                total_verdicts=data.get("total_verdicts", 0),
                created_at=data.get("created_at", ""),
            )
        except (json.JSONDecodeError, TypeError):
            return None
