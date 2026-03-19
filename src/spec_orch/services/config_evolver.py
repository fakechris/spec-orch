"""Config Evolver — suggests spec-orch.toml updates from run evidence.

Analyses historical verification results, builder outcomes, and gate
verdicts to propose configuration improvements:
- Remove verification steps that are always skipped
- Add verification steps for recurring failure patterns
- Adjust timeouts based on actual builder durations
- Suggest tool upgrades based on observed toolchain issues
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MIN_RUNS_FOR_SUGGESTION = 5


@dataclass(slots=True)
class ConfigSuggestion:
    """A proposed change to spec-orch.toml."""

    section: str
    key: str
    current_value: Any
    suggested_value: Any
    reason: str
    confidence: str = "medium"


@dataclass(slots=True)
class ConfigEvolutionResult:
    """Outcome of config evolution analysis."""

    suggestions: list[ConfigSuggestion] = field(default_factory=list)
    runs_analyzed: int = 0
    timestamp: str = ""


class ConfigEvolver:
    """Analyses run artifacts and proposes spec-orch.toml updates."""

    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root
        self._evo_dir = repo_root / ".spec_orch_evolution"
        self._suggestions_path = self._evo_dir / "config_suggestions.json"
        self._run_dirs = [
            repo_root / ".spec_orch_runs",
            repo_root / ".worktrees",
        ]

    def evolve(self, *, context: Any | None = None) -> ConfigEvolutionResult | None:
        """Analyse historical runs and propose config changes."""
        reports = self._load_reports()
        if len(reports) < _MIN_RUNS_FOR_SUGGESTION:
            logger.info(
                "Only %d runs available (need %d), skipping config evolution",
                len(reports),
                _MIN_RUNS_FOR_SUGGESTION,
            )
            return None

        result = ConfigEvolutionResult(
            runs_analyzed=len(reports),
            timestamp=datetime.now(UTC).isoformat(),
        )

        result.suggestions.extend(self._check_skipped_steps(reports))
        result.suggestions.extend(self._check_timeout_fit(reports))
        result.suggestions.extend(self._check_consistent_failures(reports))

        if result.suggestions:
            self._save_suggestions(result)

        return result

    def _load_reports(self) -> list[dict[str, Any]]:
        """Load unified run artifacts with legacy report fallback."""
        reports: list[dict[str, Any]] = []
        for run_dir in self._run_dirs:
            if not run_dir.exists():
                continue
            for child in run_dir.iterdir():
                conclusion_path = child / "run_artifact" / "conclusion.json"
                live_path = child / "run_artifact" / "live.json"
                if conclusion_path.exists():
                    try:
                        conclusion = json.loads(conclusion_path.read_text())
                        if not isinstance(conclusion, dict):
                            continue
                        merged = dict(conclusion)
                        if live_path.exists():
                            live = json.loads(live_path.read_text())
                            if isinstance(live, dict):
                                for key in ("verification", "builder", "review"):
                                    if key in live:
                                        merged[key] = live.get(key)
                        reports.append(merged)
                        continue
                    except (json.JSONDecodeError, OSError):
                        continue

                report_path = child / "report.json"
                if report_path.exists():
                    try:
                        data = json.loads(report_path.read_text())
                        reports.append(data)
                    except (json.JSONDecodeError, OSError):
                        continue
        return reports

    def _check_skipped_steps(self, reports: list[dict[str, Any]]) -> list[ConfigSuggestion]:
        """Suggest removing verification steps that are always skipped."""
        suggestions: list[ConfigSuggestion] = []
        step_counts: dict[str, int] = {}
        step_skipped: dict[str, int] = {}

        for report in reports:
            verification = report.get("verification", {})
            for step_name, detail in verification.items():
                if not isinstance(detail, dict):
                    continue
                step_counts[step_name] = step_counts.get(step_name, 0) + 1
                cmd = detail.get("command", [])
                if not cmd or detail.get("stderr", "") == "not configured — skipped":
                    step_skipped[step_name] = step_skipped.get(step_name, 0) + 1

        for step, total in step_counts.items():
            skipped = step_skipped.get(step, 0)
            if total >= _MIN_RUNS_FOR_SUGGESTION and skipped == total:
                suggestions.append(
                    ConfigSuggestion(
                        section="verification",
                        key=step,
                        current_value="(configured but never executed)",
                        suggested_value="(remove)",
                        reason=f"Step '{step}' was skipped in all {total} runs",
                        confidence="high",
                    )
                )
        return suggestions

    def _check_timeout_fit(self, reports: list[dict[str, Any]]) -> list[ConfigSuggestion]:
        """Suggest timeout adjustments based on actual durations."""
        suggestions: list[ConfigSuggestion] = []
        durations: list[float] = []

        for report in reports:
            builder = report.get("builder", {})
            duration = builder.get("duration_seconds")
            if isinstance(duration, (int, float)) and duration > 0:
                durations.append(float(duration))

        if len(durations) < _MIN_RUNS_FOR_SUGGESTION:
            return suggestions

        max_duration = max(durations)
        avg_duration = sum(durations) / len(durations)

        current_cfg = self._load_current_config()
        current_timeout = current_cfg.get("builder", {}).get("timeout_seconds", 1800)

        if max_duration < current_timeout * 0.3 and current_timeout > 300:
            suggested = int(max_duration * 2.5)
            suggested = max(suggested, 300)
            suggestions.append(
                ConfigSuggestion(
                    section="builder",
                    key="timeout_seconds",
                    current_value=current_timeout,
                    suggested_value=suggested,
                    reason=(
                        f"Max observed duration is {max_duration:.0f}s "
                        f"(avg {avg_duration:.0f}s), current timeout {current_timeout}s "
                        f"is {current_timeout / max_duration:.1f}x the max"
                    ),
                    confidence="medium",
                )
            )
        return suggestions

    def _check_consistent_failures(self, reports: list[dict[str, Any]]) -> list[ConfigSuggestion]:
        """Flag verification steps that consistently fail."""
        suggestions: list[ConfigSuggestion] = []
        step_runs: dict[str, int] = {}
        step_fails: dict[str, int] = {}

        for report in reports:
            verification = report.get("verification", {})
            for step_name, detail in verification.items():
                if not isinstance(detail, dict):
                    continue
                cmd = detail.get("command", [])
                if not cmd:
                    continue
                step_runs[step_name] = step_runs.get(step_name, 0) + 1
                if detail.get("exit_code", 0) != 0:
                    step_fails[step_name] = step_fails.get(step_name, 0) + 1

        for step, total in step_runs.items():
            fails = step_fails.get(step, 0)
            if total >= _MIN_RUNS_FOR_SUGGESTION and fails == total:
                suggestions.append(
                    ConfigSuggestion(
                        section="verification",
                        key=step,
                        current_value="(always failing)",
                        suggested_value="(review command or fix toolchain)",
                        reason=(
                            f"Step '{step}' has failed in all {total} runs — "
                            "the command may be misconfigured"
                        ),
                        confidence="high",
                    )
                )
        return suggestions

    def _load_current_config(self) -> dict[str, Any]:
        config_path = self._repo_root / "spec-orch.toml"
        if not config_path.exists():
            return {}
        try:
            import tomllib

            with config_path.open("rb") as f:
                return tomllib.load(f)
        except Exception:
            logger.warning("Could not load spec-orch.toml for config analysis", exc_info=True)
            return {}

    def _save_suggestions(self, result: ConfigEvolutionResult) -> None:
        self._evo_dir.mkdir(parents=True, exist_ok=True)
        existing: list[dict] = []
        if self._suggestions_path.exists():
            try:
                existing = json.loads(self._suggestions_path.read_text())
            except (json.JSONDecodeError, OSError):
                logger.warning("Could not load existing config suggestions", exc_info=True)
        entry = {
            "timestamp": result.timestamp,
            "runs_analyzed": result.runs_analyzed,
            "suggestions": [
                {
                    "section": s.section,
                    "key": s.key,
                    "current_value": s.current_value,
                    "suggested_value": s.suggested_value,
                    "reason": s.reason,
                    "confidence": s.confidence,
                }
                for s in result.suggestions
            ],
        }
        existing.append(entry)
        self._suggestions_path.write_text(json.dumps(existing, indent=2) + "\n")
