from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from spec_orch.domain.models import ReviewSummary


class LocalReviewAdapter:
    VALID_VERDICTS = {"pass", "changes_requested", "uncertain"}

    def initialize(self, *, issue_id: str, workspace: Path) -> ReviewSummary:
        report_path = workspace / "review_report.json"
        summary = ReviewSummary(
            verdict="pending",
            reviewed_by=None,
            report_path=report_path,
        )
        self._write_report(issue_id=issue_id, summary=summary)
        return summary

    def review(
        self,
        *,
        issue_id: str,
        workspace: Path,
        verdict: str,
        reviewed_by: str,
    ) -> ReviewSummary:
        if verdict not in self.VALID_VERDICTS:
            raise ValueError(f"invalid review verdict: {verdict}")

        summary = ReviewSummary(
            verdict=verdict,
            reviewed_by=reviewed_by,
            report_path=workspace / "review_report.json",
        )
        self._write_report(issue_id=issue_id, summary=summary)
        return summary

    def _write_report(self, *, issue_id: str, summary: ReviewSummary) -> None:
        if summary.report_path is None:
            raise ValueError("review report path is required")

        summary.report_path.write_text(
            json.dumps(
                {
                    "issue_id": issue_id,
                    "verdict": summary.verdict,
                    "reviewed_by": summary.reviewed_by,
                    "reviewed_at": datetime.now(UTC).isoformat(),
                },
                indent=2,
            )
            + "\n"
        )
