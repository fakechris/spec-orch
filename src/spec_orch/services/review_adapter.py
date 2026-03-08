from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from spec_orch.domain.models import ReviewSummary
from spec_orch.services.codex_harness_builder_adapter import (
    default_turn_contract_compliance,
)


class LocalReviewAdapter:
    VALID_VERDICTS = {"pass", "changes_requested", "uncertain"}

    def initialize(
        self,
        *,
        issue_id: str,
        workspace: Path,
        builder_turn_contract_compliance: dict | None = None,
    ) -> ReviewSummary:
        report_path = workspace / "review_report.json"
        summary = ReviewSummary(
            verdict="pending",
            reviewed_by=None,
            report_path=report_path,
        )
        self._write_report(
            issue_id=issue_id,
            summary=summary,
            builder_turn_contract_compliance=builder_turn_contract_compliance,
        )
        return summary

    def review(
        self,
        *,
        issue_id: str,
        workspace: Path,
        verdict: str,
        reviewed_by: str,
        builder_turn_contract_compliance: dict | None = None,
    ) -> ReviewSummary:
        if verdict not in self.VALID_VERDICTS:
            raise ValueError(f"invalid review verdict: {verdict}")

        summary = ReviewSummary(
            verdict=verdict,
            reviewed_by=reviewed_by,
            report_path=workspace / "review_report.json",
        )
        self._write_report(
            issue_id=issue_id,
            summary=summary,
            builder_turn_contract_compliance=builder_turn_contract_compliance,
        )
        return summary

    def _write_report(
        self,
        *,
        issue_id: str,
        summary: ReviewSummary,
        builder_turn_contract_compliance: dict | None,
    ) -> None:
        if summary.report_path is None:
            raise ValueError("review report path is required")

        summary.report_path.write_text(
            json.dumps(
                {
                    "issue_id": issue_id,
                    "verdict": summary.verdict,
                    "reviewed_by": summary.reviewed_by,
                    "reviewed_at": datetime.now(UTC).isoformat(),
                    "builder_turn_contract_compliance": (
                        builder_turn_contract_compliance
                        or default_turn_contract_compliance()
                    ),
                },
                indent=2,
            )
            + "\n"
        )
