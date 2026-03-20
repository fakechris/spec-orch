"""Skill / pipeline degradation detector.

Compares recent run quality against a historical baseline to surface
regressions in pass rate, verification rate, or deviation frequency.
Built on top of EvalRunner.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from spec_orch.services.eval_runner import RunScore

logger = logging.getLogger(__name__)

DEFAULT_RECENT_WINDOW = 10
DEFAULT_BASELINE_WINDOW = 30
REGRESSION_THRESHOLD = 0.10


@dataclass(slots=True)
class DegradationSignal:
    """A single degradation signal."""

    metric: str
    baseline_value: float
    recent_value: float
    delta: float
    severity: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DegradationReport:
    """Overall degradation analysis."""

    degraded: bool = False
    signals: list[DegradationSignal] = field(default_factory=list)
    baseline_runs: int = 0
    recent_runs: int = 0
    generated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["signals"] = [s.to_dict() for s in self.signals]
        return d


class DegradationDetector:
    """Detect quality regressions by comparing recent vs baseline windows."""

    def __init__(
        self,
        repo_root: Path,
        *,
        recent_window: int = DEFAULT_RECENT_WINDOW,
        baseline_window: int = DEFAULT_BASELINE_WINDOW,
        threshold: float = REGRESSION_THRESHOLD,
    ) -> None:
        self.repo_root = repo_root
        self.recent_window = recent_window
        self.baseline_window = baseline_window
        self.threshold = threshold

    def detect(self) -> DegradationReport:
        from spec_orch.services.eval_runner import EvalRunner

        runner = EvalRunner(self.repo_root)
        full_report = runner.evaluate()

        scores = full_report.run_scores
        if len(scores) < self.recent_window + 1:
            return DegradationReport(
                generated_at=datetime.now(UTC).isoformat(),
                baseline_runs=len(scores),
                recent_runs=0,
            )

        recent = scores[-self.recent_window :]
        baseline_end = len(scores) - self.recent_window
        baseline_start = max(0, baseline_end - self.baseline_window)
        baseline = scores[baseline_start:baseline_end]

        if not baseline:
            return DegradationReport(
                generated_at=datetime.now(UTC).isoformat(),
                baseline_runs=0,
                recent_runs=len(recent),
            )

        if not recent:
            return DegradationReport(
                generated_at=datetime.now(UTC).isoformat(),
                baseline_runs=len(baseline),
                recent_runs=0,
            )

        signals: list[DegradationSignal] = []

        b_pass = sum(1 for s in baseline if s.mergeable) / len(baseline)
        r_pass = sum(1 for s in recent if s.mergeable) / len(recent)
        delta_pass = r_pass - b_pass
        if delta_pass < -self.threshold:
            signals.append(
                DegradationSignal(
                    metric="pass_rate",
                    baseline_value=round(b_pass, 3),
                    recent_value=round(r_pass, 3),
                    delta=round(delta_pass, 3),
                    severity="high" if delta_pass < -2 * self.threshold else "medium",
                )
            )

        b_vr = self._avg_verification(baseline)
        r_vr = self._avg_verification(recent)
        if b_vr is not None and r_vr is not None:
            delta_vr = r_vr - b_vr
            if delta_vr < -self.threshold:
                signals.append(
                    DegradationSignal(
                        metric="verification_rate",
                        baseline_value=round(b_vr, 3),
                        recent_value=round(r_vr, 3),
                        delta=round(delta_vr, 3),
                        severity="medium",
                    )
                )

        b_dev = sum(s.deviation_count for s in baseline) / len(baseline)
        r_dev = sum(s.deviation_count for s in recent) / len(recent)
        if (b_dev == 0 and r_dev > self.threshold) or (
            b_dev > 0 and r_dev > b_dev * (1 + self.threshold)
        ):
            signals.append(
                DegradationSignal(
                    metric="avg_deviations",
                    baseline_value=round(b_dev, 2),
                    recent_value=round(r_dev, 2),
                    delta=round(r_dev - b_dev, 2),
                    severity="low",
                )
            )

        return DegradationReport(
            degraded=len(signals) > 0,
            signals=signals,
            baseline_runs=len(baseline),
            recent_runs=len(recent),
            generated_at=datetime.now(UTC).isoformat(),
        )

    def write_report(self, report: DegradationReport, output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _avg_verification(scores: list[RunScore]) -> float | None:
        vals = [s.verification_pass_rate for s in scores if s.verification_pass_rate is not None]
        return (sum(vals) / len(vals)) if vals else None
