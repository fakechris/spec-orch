from __future__ import annotations

from spec_orch.domain.models import (
    AcceptanceIssueProposal,
    AcceptanceReviewResult,
)


def test_linear_acceptance_filer_files_high_confidence_failures() -> None:
    from spec_orch.services.acceptance.linear_filing import LinearAcceptanceFiler

    class StubLinearClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, str]] = []

        def create_issue(
            self, *, team_key: str, title: str, description: str = ""
        ) -> dict[str, str]:
            self.calls.append({"team_key": team_key, "title": title, "description": description})
            return {"id": "issue-1", "identifier": "SON-999", "title": title}

    client = StubLinearClient()
    filer = LinearAcceptanceFiler(client=client, team_key="SON", min_confidence=0.8)
    result = AcceptanceReviewResult(
        status="fail",
        summary="Reject this run.",
        confidence=0.93,
        evaluator="acceptance_llm",
        issue_proposals=[
            AcceptanceIssueProposal(
                title="Restore CTA",
                summary="Primary CTA is missing from the home page.",
                severity="high",
                confidence=0.91,
            )
        ],
    )

    filed = filer.apply(result, mission_id="mission-1", round_id=1)

    assert client.calls
    assert filed.issue_proposals[0].linear_issue_id == "SON-999"
    assert filed.issue_proposals[0].filing_status == "filed"


def test_linear_acceptance_filer_skips_low_confidence_warnings() -> None:
    from spec_orch.services.acceptance.linear_filing import LinearAcceptanceFiler

    class StubLinearClient:
        def create_issue(
            self, *, team_key: str, title: str, description: str = ""
        ) -> dict[str, str]:
            raise AssertionError("should not file low-confidence warnings")

    filer = LinearAcceptanceFiler(client=StubLinearClient(), team_key="SON", min_confidence=0.8)
    result = AcceptanceReviewResult(
        status="warn",
        summary="This is a warning only.",
        confidence=0.42,
        evaluator="acceptance_llm",
        issue_proposals=[
            AcceptanceIssueProposal(
                title="Minor spacing issue",
                summary="Spacing looks slightly off.",
                severity="low",
                confidence=0.42,
            )
        ],
    )

    filed = filer.apply(result, mission_id="mission-1", round_id=1)

    assert filed.issue_proposals[0].filing_status == "skipped"
    assert filed.issue_proposals[0].linear_issue_id == ""


def test_linear_acceptance_filer_records_failure_without_raising() -> None:
    from spec_orch.services.acceptance.linear_filing import LinearAcceptanceFiler

    class StubLinearClient:
        def create_issue(
            self, *, team_key: str, title: str, description: str = ""
        ) -> dict[str, str]:
            raise RuntimeError("Linear outage")

    filer = LinearAcceptanceFiler(client=StubLinearClient(), team_key="SON", min_confidence=0.8)
    result = AcceptanceReviewResult(
        status="fail",
        summary="Reject this run.",
        confidence=0.97,
        evaluator="acceptance_llm",
        issue_proposals=[
            AcceptanceIssueProposal(
                title="Fix regression",
                summary="Regression detected on the home page.",
                severity="high",
                confidence=0.97,
            )
        ],
    )

    filed = filer.apply(result, mission_id="mission-1", round_id=1)

    assert filed.issue_proposals[0].filing_status == "failed"
    assert "Linear outage" in filed.issue_proposals[0].filing_error
