from __future__ import annotations

from dataclasses import replace
from typing import Any

from spec_orch.domain.models import AcceptanceIssueProposal, AcceptanceReviewResult


class LinearAcceptanceFiler:
    def __init__(
        self,
        *,
        client: Any,
        team_key: str,
        min_confidence: float = 0.8,
        min_severity: str = "high",
    ) -> None:
        self.client = client
        self.team_key = team_key
        self.min_confidence = min_confidence
        self.min_severity = min_severity

    def apply(
        self,
        result: AcceptanceReviewResult,
        *,
        mission_id: str,
        round_id: int,
    ) -> AcceptanceReviewResult:
        proposals: list[AcceptanceIssueProposal] = []
        for proposal in result.issue_proposals:
            if not self._should_file(result, proposal):
                proposals.append(replace(proposal, filing_status="skipped", filing_error=""))
                continue
            try:
                issue = self.client.create_issue(
                    team_key=self.team_key,
                    title=proposal.title,
                    description=self._build_description(
                        mission_id=mission_id,
                        round_id=round_id,
                        result=result,
                        proposal=proposal,
                    ),
                )
                identifier = str(issue.get("identifier") or issue.get("id") or "")
                proposals.append(
                    replace(
                        proposal,
                        linear_issue_id=identifier,
                        filing_status="filed",
                        filing_error="",
                    )
                )
            except Exception as exc:
                proposals.append(
                    replace(
                        proposal,
                        filing_status="failed",
                        filing_error=str(exc),
                    )
                )
        return replace(result, issue_proposals=proposals)

    def _should_file(
        self,
        result: AcceptanceReviewResult,
        proposal: AcceptanceIssueProposal,
    ) -> bool:
        if result.status != "fail":
            return False
        confidence = max(result.confidence, proposal.confidence)
        if confidence < self.min_confidence:
            return False
        return self._severity_rank(proposal.severity) >= self._severity_rank(self.min_severity)

    @staticmethod
    def _severity_rank(severity: str) -> int:
        ranks = {
            "low": 1,
            "medium": 2,
            "warning": 2,
            "high": 3,
            "critical": 4,
            "blocking": 4,
        }
        return ranks.get(str(severity).lower(), 0)

    @staticmethod
    def _build_description(
        *,
        mission_id: str,
        round_id: int,
        result: AcceptanceReviewResult,
        proposal: AcceptanceIssueProposal,
    ) -> str:
        lines = [
            f"Acceptance evaluator rejected mission `{mission_id}` round `{round_id}`.",
            "",
            f"Summary: {result.summary}",
            "",
            f"Issue: {proposal.summary}",
        ]
        if proposal.route:
            lines.extend(["", f"Route: {proposal.route}"])
        if proposal.expected:
            lines.extend(["", f"Expected: {proposal.expected}"])
        if proposal.actual:
            lines.extend(["", f"Actual: {proposal.actual}"])
        if proposal.repro_steps:
            lines.extend(["", "Repro steps:"])
            lines.extend([f"- {step}" for step in proposal.repro_steps])
        return "\n".join(lines)
