"""Analyze historical run data and produce aggregate pattern summaries."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

RUN_DIRS = (".spec_orch_runs", ".worktrees")


@dataclass
class PatternSummary:
    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    success_rate: float = 0.0
    top_failure_reasons: list[tuple[str, int]] = field(default_factory=list)
    top_deviation_files: list[tuple[str, int]] = field(default_factory=list)
    average_verification_pass_rate: float = 0.0
    total_deviations: int = 0
    has_retrospectives: int = 0


class EvidenceAnalyzer:
    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root

    def analyze(self) -> PatternSummary:
        """Scan all historical runs and return aggregate patterns."""
        run_dirs = self._collect_run_dirs()
        if not run_dirs:
            return PatternSummary()

        total = 0
        successful = 0
        failure_counts: dict[str, int] = {}
        deviation_file_counts: dict[str, int] = {}
        total_deviations = 0
        has_retrospectives = 0
        verification_rates: list[float] = []

        for rd in run_dirs:
            report = self._read_report(rd)
            if report is None:
                continue

            total += 1
            if report.get("mergeable") is True:
                successful += 1

            for reason in report.get("failed_conditions", []):
                failure_counts[reason] = failure_counts.get(reason, 0) + 1

            vr = self._verification_pass_rate(report)
            if vr is not None:
                verification_rates.append(vr)

            deviations = self._read_deviations(rd)
            total_deviations += len(deviations)
            for dev in deviations:
                fp = dev.get("file_path", "")
                if fp:
                    deviation_file_counts[fp] = deviation_file_counts.get(fp, 0) + 1

            if (rd / "retrospective.md").exists():
                has_retrospectives += 1

        failed = total - successful
        success_rate = successful / total if total > 0 else 0.0
        avg_vpr = (
            sum(verification_rates) / len(verification_rates)
            if verification_rates
            else 0.0
        )

        top_failures = sorted(failure_counts.items(), key=lambda x: x[1], reverse=True)[
            :5
        ]
        top_devs = sorted(
            deviation_file_counts.items(), key=lambda x: x[1], reverse=True
        )[:10]

        return PatternSummary(
            total_runs=total,
            successful_runs=successful,
            failed_runs=failed,
            success_rate=success_rate,
            top_failure_reasons=top_failures,
            top_deviation_files=top_devs,
            average_verification_pass_rate=avg_vpr,
            total_deviations=total_deviations,
            has_retrospectives=has_retrospectives,
        )

    def format_summary(self, summary: PatternSummary) -> str:
        """Format summary as human-readable text."""
        lines = [
            "Evidence Summary",
            "=" * 40,
            f"Total runs:        {summary.total_runs}",
            f"Successful:        {summary.successful_runs}",
            f"Failed:            {summary.failed_runs}",
            f"Success rate:      {summary.success_rate:.1%}",
            f"Avg verify rate:   {summary.average_verification_pass_rate:.1%}",
            f"Total deviations:  {summary.total_deviations}",
            f"Retrospectives:    {summary.has_retrospectives}",
        ]

        if summary.top_failure_reasons:
            lines.append("")
            lines.append("Top failure reasons:")
            for reason, count in summary.top_failure_reasons:
                lines.append(f"  - {reason}: {count}")

        if summary.top_deviation_files:
            lines.append("")
            lines.append("Top deviation files:")
            for fp, count in summary.top_deviation_files:
                lines.append(f"  - {fp}: {count}")

        return "\n".join(lines)

    def format_as_llm_context(self, summary: PatternSummary) -> str:
        """Format summary as LLM context injection string."""
        if summary.total_runs == 0:
            return "<evidence>No historical run data available.</evidence>"

        parts = [
            "<evidence>",
            f"Historical run analysis: {summary.total_runs} runs, "
            f"{summary.success_rate:.0%} success rate.",
        ]

        if summary.top_failure_reasons:
            reasons = ", ".join(
                f"{r} ({c}x)" for r, c in summary.top_failure_reasons
            )
            parts.append(f"Common failures: {reasons}.")

        if summary.top_deviation_files:
            files = ", ".join(f for f, _ in summary.top_deviation_files[:5])
            parts.append(f"Frequently deviating files: {files}.")

        if summary.total_deviations > 0:
            parts.append(f"Total deviations observed: {summary.total_deviations}.")

        parts.append(
            f"Average verification pass rate: {summary.average_verification_pass_rate:.0%}."
        )
        parts.append("</evidence>")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _collect_run_dirs(self) -> list[Path]:
        dirs: list[Path] = []
        for parent_name in RUN_DIRS:
            parent = self._repo_root / parent_name
            if parent.is_dir():
                for child in sorted(parent.iterdir()):
                    if child.is_dir():
                        dirs.append(child)
        return dirs

    def _read_report(self, run_dir: Path) -> dict | None:
        report_path = run_dir / "report.json"
        if not report_path.exists():
            return None
        try:
            return json.loads(report_path.read_text())  # type: ignore[no-any-return]
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Skipping malformed report %s: %s", report_path, exc)
            return None

    def _read_deviations(self, run_dir: Path) -> list[dict]:
        dev_path = run_dir / "deviations.jsonl"
        if not dev_path.exists():
            return []
        results: list[dict] = []
        try:
            for line in dev_path.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    logger.warning(
                        "Skipping malformed deviation line in %s: %s", dev_path, exc
                    )
        except OSError as exc:
            logger.warning("Could not read deviations %s: %s", dev_path, exc)
        return results

    def _verification_pass_rate(self, report: dict) -> float | None:
        verification = report.get("verification")
        if not isinstance(verification, dict) or not verification:
            return None
        total = 0
        passed = 0
        for _check_name, check_data in verification.items():
            if isinstance(check_data, dict) and "exit_code" in check_data:
                total += 1
                if check_data["exit_code"] == 0:
                    passed += 1
        if total == 0:
            return None
        return passed / total
