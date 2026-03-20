"""Skill degradation detection (Epic G).

Monitors three degradation modes:
1. Routing confusion — skill descriptions unclear, agent picks wrong skill
2. Model drift — model update causes skill performance drop
3. Baseline corruption — evaluation criteria become stale

Provides routing audit logging and baseline tracking.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RoutingDecision:
    """Record of a skill routing decision for audit."""

    timestamp: float
    skill_name: str
    selected: bool
    reason: str
    context_hint: str = ""


@dataclass(frozen=True)
class SkillBaseline:
    """Effectiveness baseline for a skill."""

    skill_name: str
    success_rate: float
    sample_count: int
    model_version: str
    measured_at: str


@dataclass
class SkillDegradationDetector:
    """Track skill effectiveness and detect degradation."""

    repo_root: Path
    _baselines: dict[str, SkillBaseline] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._load_baselines()

    def _baselines_path(self) -> Path:
        return self.repo_root / ".spec_orch" / "skill_baselines.json"

    def _audit_log_path(self) -> Path:
        return self.repo_root / ".spec_orch" / "skill_routing_audit.jsonl"

    def _load_baselines(self) -> None:
        path = self._baselines_path()
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for name, entry in data.items():
                self._baselines[name] = SkillBaseline(**entry)
        except (json.JSONDecodeError, TypeError, KeyError):
            logger.warning("Failed to load skill baselines from %s", path)

    def save_baselines(self) -> None:
        path = self._baselines_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {name: asdict(bl) for name, bl in self._baselines.items()}
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    def record_baseline(self, baseline: SkillBaseline) -> None:
        self._baselines[baseline.skill_name] = baseline
        self.save_baselines()

    def log_routing_decision(self, decision: RoutingDecision) -> None:
        path = self._audit_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(decision), ensure_ascii=False) + "\n")

    def check_degradation(
        self, skill_name: str, current_success_rate: float, sample_count: int
    ) -> tuple[bool, str]:
        """Check if a skill has degraded below its baseline.

        Returns (is_degraded, reason).
        """
        baseline = self._baselines.get(skill_name)
        if baseline is None:
            return False, "no baseline established"
        if sample_count < 5:
            return False, "insufficient samples"
        drop = baseline.success_rate - current_success_rate
        if drop > 0.15:
            return True, (
                f"success rate dropped {drop:.0%} "
                f"(baseline={baseline.success_rate:.0%}, "
                f"current={current_success_rate:.0%})"
            )
        return False, "within acceptable range"

    def get_baselines(self) -> dict[str, SkillBaseline]:
        return dict(self._baselines)

    def recent_routing_decisions(self, limit: int = 50) -> list[RoutingDecision]:
        path = self._audit_log_path()
        if not path.exists():
            return []
        decisions: list[RoutingDecision] = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    data = json.loads(line)
                    decisions.append(RoutingDecision(**data))
        except (json.JSONDecodeError, TypeError, KeyError):
            pass
        return decisions[-limit:]
