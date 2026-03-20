"""Offline eval runner for harness evaluation (P6 baseline).

Scans historical run artifacts, computes per-run and aggregate metrics,
and outputs a structured eval report. Designed for:
- Harness A/B comparison (e.g. prompt variant vs baseline)
- Regression detection after evolution changes
- Offline quality dashboards
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RunScore:
    """Per-run scoring record."""

    run_id: str
    issue_id: str
    verdict: str
    mergeable: bool
    failed_conditions: list[str]
    verification_pass_rate: float | None
    deviation_count: int
    builder_adapter: str
    has_retro: bool
    tags: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class EvalReport:
    """Aggregate evaluation over a set of runs."""

    total: int = 0
    passed: int = 0
    failed: int = 0
    pass_rate: float = 0.0
    avg_verification_rate: float = 0.0
    avg_deviation_count: float = 0.0
    failure_breakdown: dict[str, int] = field(default_factory=dict)
    adapter_breakdown: dict[str, dict[str, int]] = field(default_factory=dict)
    run_scores: list[RunScore] = field(default_factory=list)
    generated_at: str = ""
    filter_tags: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["run_scores"] = [asdict(s) for s in self.run_scores]
        return d


class EvalRunner:
    """Scan run artifacts and produce an EvalReport."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root

    def evaluate(
        self,
        *,
        filter_tags: dict[str, str] | None = None,
        run_dirs: list[Path] | None = None,
    ) -> EvalReport:
        dirs = run_dirs if run_dirs is not None else self._collect_run_dirs()
        scores: list[RunScore] = []
        for d in dirs:
            score = self._score_run(d)
            if score is None:
                continue
            if filter_tags and not self._matches_tags(score, filter_tags):
                continue
            scores.append(score)
        return self._aggregate(scores, filter_tags or {})

    def write_report(self, report: EvalReport, output: Path) -> Path:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return output

    def _collect_run_dirs(self) -> list[Path]:
        dirs: list[Path] = []
        for parent_name in (".spec_orch_runs", ".worktrees"):
            parent = self.repo_root / parent_name
            if parent.is_dir():
                for child in sorted(parent.iterdir()):
                    if child.is_dir():
                        dirs.append(child)
        return dirs

    def _score_run(self, run_dir: Path) -> RunScore | None:
        conclusion = self._read_json(run_dir / "run_artifact" / "conclusion.json")
        live = self._read_json(run_dir / "run_artifact" / "live.json")
        report = self._read_json(run_dir / "report.json")

        data = conclusion or report
        if not data:
            return None

        live_data = live or report or {}
        run_id = str(data.get("run_id") or report.get("run_id") or run_dir.name)
        issue_id = str(data.get("issue_id") or run_dir.name)
        verdict = str(data.get("verdict", "fail" if not data.get("mergeable") else "pass"))
        mergeable = bool(data.get("mergeable", False))
        failed_conditions = data.get("failed_conditions", [])
        if not isinstance(failed_conditions, list):
            failed_conditions = []

        vr = self._verification_rate(live_data.get("verification"))
        dev_count = self._count_deviations(run_dir)
        builder = live_data.get("builder", {})
        adapter = str(builder.get("adapter", "")) if isinstance(builder, dict) else ""
        has_retro = (run_dir / "run_artifact" / "retro.json").exists() or (
            run_dir / "retrospective.md"
        ).exists()

        tags = self._extract_tags(data, live_data)

        return RunScore(
            run_id=run_id,
            issue_id=issue_id,
            verdict=verdict,
            mergeable=mergeable,
            failed_conditions=[str(f) for f in failed_conditions],
            verification_pass_rate=vr,
            deviation_count=dev_count,
            builder_adapter=adapter,
            has_retro=has_retro,
            tags=tags,
        )

    @staticmethod
    def _extract_tags(
        conclusion: dict[str, Any],
        live: dict[str, Any],
    ) -> dict[str, str]:
        """Extract tags for filtering (prompt_variant, flow_type, etc.)."""
        tags: dict[str, str] = {}
        builder = live.get("builder", {})
        if isinstance(builder, dict):
            agent = builder.get("agent")
            if agent:
                tags["agent"] = str(agent)
            adapter = builder.get("adapter")
            if adapter:
                tags["adapter"] = str(adapter)
        state = conclusion.get("state") or live.get("state")
        if state:
            tags["state"] = str(state)
        return tags

    @staticmethod
    def _verification_rate(verification: Any) -> float | None:
        if not isinstance(verification, dict) or not verification:
            return None
        total = 0
        passed = 0
        for _name, check in verification.items():
            if isinstance(check, dict) and "exit_code" in check:
                total += 1
                if check["exit_code"] == 0:
                    passed += 1
        return (passed / total) if total > 0 else None

    def _count_deviations(self, run_dir: Path) -> int:
        dev_path = run_dir / "deviations.jsonl"
        if not dev_path.exists():
            return 0
        count = 0
        try:
            for line in dev_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    count += 1
        except OSError:
            pass
        return count

    @staticmethod
    def _matches_tags(score: RunScore, required: dict[str, str]) -> bool:
        return all(score.tags.get(k) == v for k, v in required.items())

    @staticmethod
    def _aggregate(scores: list[RunScore], filter_tags: dict[str, str]) -> EvalReport:
        total = len(scores)
        passed = sum(1 for s in scores if s.mergeable)
        failed = total - passed
        pass_rate = (passed / total) if total > 0 else 0.0

        vr_values = [
            s.verification_pass_rate for s in scores if s.verification_pass_rate is not None
        ]
        avg_vr = (sum(vr_values) / len(vr_values)) if vr_values else 0.0
        avg_dev = (sum(s.deviation_count for s in scores) / total) if total > 0 else 0.0

        failure_breakdown: dict[str, int] = {}
        for s in scores:
            for fc in s.failed_conditions:
                failure_breakdown[fc] = failure_breakdown.get(fc, 0) + 1

        adapter_breakdown: dict[str, dict[str, int]] = {}
        for s in scores:
            key = s.builder_adapter or "unknown"
            bucket = adapter_breakdown.setdefault(key, {"total": 0, "passed": 0})
            bucket["total"] += 1
            if s.mergeable:
                bucket["passed"] += 1

        return EvalReport(
            total=total,
            passed=passed,
            failed=failed,
            pass_rate=pass_rate,
            avg_verification_rate=avg_vr,
            avg_deviation_count=avg_dev,
            failure_breakdown=failure_breakdown,
            adapter_breakdown=adapter_breakdown,
            run_scores=scores,
            generated_at=datetime.now(UTC).isoformat(),
            filter_tags=filter_tags,
        )

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}
