from __future__ import annotations

from spec_orch.domain.models import (
    AcceptanceCampaign,
    AcceptanceIssueProposal,
    AcceptanceMode,
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


def test_linear_acceptance_filer_is_idempotent_for_already_filed_proposals() -> None:
    from spec_orch.services.acceptance.linear_filing import LinearAcceptanceFiler

    class StubLinearClient:
        def create_issue(
            self, *, team_key: str, title: str, description: str = ""
        ) -> dict[str, str]:
            raise AssertionError("should not recreate already-filed issues")

    filer = LinearAcceptanceFiler(client=StubLinearClient(), team_key="SON", min_confidence=0.8)
    result = AcceptanceReviewResult(
        status="fail",
        summary="Reject this run.",
        confidence=0.97,
        evaluator="acceptance_llm",
        issue_proposals=[
            AcceptanceIssueProposal(
                title="Existing issue",
                summary="Already filed.",
                severity="high",
                confidence=0.97,
                linear_issue_id="SON-555",
                filing_status="filed",
            )
        ],
    )

    filed = filer.apply(result, mission_id="mission-1", round_id=1)

    assert filed.issue_proposals[0].linear_issue_id == "SON-555"
    assert filed.issue_proposals[0].filing_status == "filed"


def test_linear_acceptance_filer_records_failure_when_issue_identifier_missing() -> None:
    from spec_orch.services.acceptance.linear_filing import LinearAcceptanceFiler

    class StubLinearClient:
        def create_issue(
            self, *, team_key: str, title: str, description: str = ""
        ) -> dict[str, str]:
            return {"title": title}

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
    assert "identifier" in filed.issue_proposals[0].filing_error


def test_linear_acceptance_filer_coerces_string_proposal_confidence_from_llm_payload() -> None:
    from spec_orch.services.acceptance.linear_filing import LinearAcceptanceFiler

    class StubLinearClient:
        def create_issue(
            self, *, team_key: str, title: str, description: str = ""
        ) -> dict[str, str]:
            raise AssertionError("low-confidence proposal should not be auto-filed")

    filer = LinearAcceptanceFiler(client=StubLinearClient(), team_key="SON", min_confidence=0.8)
    result = AcceptanceReviewResult.from_dict(
        {
            "status": "fail",
            "summary": "Reject this run.",
            "confidence": 0.2,
            "evaluator": "acceptance_llm",
            "issue_proposals": [
                {
                    "title": "Follow up on weak signal",
                    "summary": "This proposal came back with string confidence.",
                    "severity": "high",
                    "confidence": "low",
                }
            ],
        }
    )

    filed = filer.apply(result, mission_id="mission-1", round_id=1)

    assert filed.issue_proposals[0].filing_status == "skipped"
    assert "confidence below auto-file threshold" in filed.issue_proposals[0].filing_error


def test_linear_acceptance_filer_holds_exploratory_high_severity_ux_findings_for_review() -> None:
    from spec_orch.services.acceptance.linear_filing import LinearAcceptanceFiler

    class StubLinearClient:
        def create_issue(
            self, *, team_key: str, title: str, description: str = ""
        ) -> dict[str, str]:
            raise AssertionError("exploratory UX issues should be held for operator review")

    filer = LinearAcceptanceFiler(client=StubLinearClient(), team_key="SON", min_confidence=0.8)
    result = AcceptanceReviewResult(
        status="fail",
        summary="Operator flow feels confusing.",
        confidence=0.92,
        evaluator="acceptance_llm",
        coverage_status="complete",
        tested_routes=["/", "/?mission=mission-1&tab=transcript"],
        campaign=AcceptanceCampaign(
            mode=AcceptanceMode.EXPLORATORY,
            goal="Dogfood the operator flow.",
            primary_routes=["/"],
            related_routes=["/?mission=mission-1&tab=transcript"],
            filing_policy="hold_ux_concerns_for_operator_review",
        ),
        issue_proposals=[
            AcceptanceIssueProposal(
                title="Reduce transcript navigation confusion",
                summary="Transcript navigation is hard to understand for first-time operators.",
                severity="high",
                confidence=0.92,
                route="/?mission=mission-1&tab=transcript",
            )
        ],
    )

    filed = filer.apply(result, mission_id="mission-1", round_id=1)

    assert filed.issue_proposals[0].filing_status == "skipped"
    assert "operator review" in filed.issue_proposals[0].filing_error


def test_linear_acceptance_filer_skips_auto_filing_when_coverage_is_missing() -> None:
    from spec_orch.services.acceptance.linear_filing import LinearAcceptanceFiler

    class StubLinearClient:
        def create_issue(
            self, *, team_key: str, title: str, description: str = ""
        ) -> dict[str, str]:
            raise AssertionError("should not auto-file when coverage is missing")

    filer = LinearAcceptanceFiler(client=StubLinearClient(), team_key="SON", min_confidence=0.8)
    result = AcceptanceReviewResult(
        status="fail",
        summary="Coverage did not reach the target route.",
        confidence=0.96,
        evaluator="acceptance_llm",
        coverage_status="missing",
        untested_expected_routes=["/launcher"],
        campaign=AcceptanceCampaign(
            mode=AcceptanceMode.IMPACT_SWEEP,
            goal="Check launcher regressions.",
            primary_routes=["/launcher"],
            filing_policy="auto_file_regressions_only",
        ),
        issue_proposals=[
            AcceptanceIssueProposal(
                title="Launcher CTA missing",
                summary="The launcher CTA appears absent.",
                severity="high",
                confidence=0.96,
                route="/launcher",
            )
        ],
    )

    filed = filer.apply(result, mission_id="mission-1", round_id=1)

    assert filed.issue_proposals[0].filing_status == "skipped"
    assert "coverage" in filed.issue_proposals[0].filing_error


def test_linear_acceptance_filer_skips_in_scope_policy_for_out_of_scope_route() -> None:
    from spec_orch.services.acceptance.linear_filing import LinearAcceptanceFiler

    class StubLinearClient:
        def create_issue(
            self, *, team_key: str, title: str, description: str = ""
        ) -> dict[str, str]:
            raise AssertionError("out-of-scope routes should not be auto-filed")

    filer = LinearAcceptanceFiler(client=StubLinearClient(), team_key="SON", min_confidence=0.8)
    result = AcceptanceReviewResult(
        status="fail",
        summary="An unrelated route looks broken.",
        confidence=0.95,
        evaluator="acceptance_llm",
        coverage_status="complete",
        campaign=AcceptanceCampaign(
            mode=AcceptanceMode.FEATURE_SCOPED,
            goal="Verify launcher create draft flow.",
            primary_routes=["/launcher"],
            related_routes=["/"],
            filing_policy="in_scope_only",
        ),
        issue_proposals=[
            AcceptanceIssueProposal(
                title="Pricing page spacing regression",
                summary="Pricing page spacing shifted.",
                severity="high",
                confidence=0.95,
                route="/pricing",
            )
        ],
    )

    filed = filer.apply(result, mission_id="mission-1", round_id=1)

    assert filed.issue_proposals[0].filing_status == "skipped"
    assert "out of scope" in filed.issue_proposals[0].filing_error


def test_linear_acceptance_filer_regressions_policy_only_trusts_tested_routes() -> None:
    from spec_orch.services.acceptance.linear_filing import LinearAcceptanceFiler

    class StubLinearClient:
        def create_issue(
            self, *, team_key: str, title: str, description: str = ""
        ) -> dict[str, str]:
            raise AssertionError("untested routes should not be auto-filed as regressions")

    filer = LinearAcceptanceFiler(client=StubLinearClient(), team_key="SON", min_confidence=0.8)
    result = AcceptanceReviewResult(
        status="fail",
        summary="Launcher regression may affect transcript route.",
        confidence=0.94,
        evaluator="acceptance_llm",
        coverage_status="partial",
        tested_routes=["/launcher"],
        campaign=AcceptanceCampaign(
            mode=AcceptanceMode.IMPACT_SWEEP,
            goal="Check launcher and transcript routes for regressions.",
            primary_routes=["/launcher"],
            related_routes=["/?mission=mission-1&tab=transcript"],
            filing_policy="auto_file_regressions_only",
        ),
        issue_proposals=[
            AcceptanceIssueProposal(
                title="Transcript route regression",
                summary="Transcript route appears broken.",
                severity="high",
                confidence=0.94,
                route="/?mission=mission-1&tab=transcript",
            )
        ],
    )

    filed = filer.apply(result, mission_id="mission-1", round_id=1)

    assert filed.issue_proposals[0].filing_status == "skipped"
    assert "not covered" in filed.issue_proposals[0].filing_error


def test_linear_acceptance_filer_broken_flows_policy_holds_non_critical_proposals() -> None:
    from spec_orch.services.acceptance.linear_filing import LinearAcceptanceFiler

    class StubLinearClient:
        def create_issue(
            self, *, team_key: str, title: str, description: str = ""
        ) -> dict[str, str]:
            raise AssertionError("non-critical broken-flow proposals should be held")

    filer = LinearAcceptanceFiler(client=StubLinearClient(), team_key="SON", min_confidence=0.8)
    result = AcceptanceReviewResult(
        status="fail",
        summary="Exploratory run found a confusing flow.",
        confidence=0.9,
        evaluator="acceptance_llm",
        coverage_status="complete",
        tested_routes=["/"],
        campaign=AcceptanceCampaign(
            mode=AcceptanceMode.EXPLORATORY,
            goal="Dogfood the operator flow.",
            primary_routes=["/"],
            filing_policy="auto_file_broken_flows_only",
        ),
        issue_proposals=[
            AcceptanceIssueProposal(
                title="Clarify operator flow",
                summary="The flow is confusing but not visibly broken.",
                severity="high",
                confidence=0.9,
                route="/",
            )
        ],
    )

    filed = filer.apply(result, mission_id="mission-1", round_id=1)

    assert filed.issue_proposals[0].filing_status == "skipped"
    assert "broken-flow-only" in filed.issue_proposals[0].filing_error


def test_linear_acceptance_filer_requires_route_for_in_scope_policy() -> None:
    from spec_orch.services.acceptance.linear_filing import LinearAcceptanceFiler

    class StubLinearClient:
        def create_issue(
            self, *, team_key: str, title: str, description: str = ""
        ) -> dict[str, str]:
            raise AssertionError("route-less in-scope proposals should not be auto-filed")

    filer = LinearAcceptanceFiler(client=StubLinearClient(), team_key="SON", min_confidence=0.8)
    result = AcceptanceReviewResult(
        status="fail",
        summary="Feature-scoped launcher review found a regression.",
        confidence=0.93,
        evaluator="acceptance_llm",
        coverage_status="complete",
        campaign=AcceptanceCampaign(
            mode=AcceptanceMode.FEATURE_SCOPED,
            goal="Verify launcher create draft flow.",
            primary_routes=["/launcher"],
            related_routes=["/"],
            filing_policy="in_scope_only",
        ),
        issue_proposals=[
            AcceptanceIssueProposal(
                title="Restore launcher CTA",
                summary="Launcher CTA is missing.",
                severity="high",
                confidence=0.93,
                route="",
            )
        ],
    )

    filed = filer.apply(result, mission_id="mission-1", round_id=1)

    assert filed.issue_proposals[0].filing_status == "skipped"
    assert "required" in filed.issue_proposals[0].filing_error


def test_linear_acceptance_filer_requires_route_for_regression_only_policy() -> None:
    from spec_orch.services.acceptance.linear_filing import LinearAcceptanceFiler

    class StubLinearClient:
        def create_issue(
            self, *, team_key: str, title: str, description: str = ""
        ) -> dict[str, str]:
            raise AssertionError("route-less regression-only proposals should not be auto-filed")

    filer = LinearAcceptanceFiler(client=StubLinearClient(), team_key="SON", min_confidence=0.8)
    result = AcceptanceReviewResult(
        status="fail",
        summary="Impact sweep found a route-level regression.",
        confidence=0.93,
        evaluator="acceptance_llm",
        coverage_status="complete",
        tested_routes=["/launcher"],
        campaign=AcceptanceCampaign(
            mode=AcceptanceMode.IMPACT_SWEEP,
            goal="Check launcher regressions.",
            primary_routes=["/launcher"],
            filing_policy="auto_file_regressions_only",
        ),
        issue_proposals=[
            AcceptanceIssueProposal(
                title="Launcher regression",
                summary="Regression exists but proposal route was omitted.",
                severity="high",
                confidence=0.93,
                route="   ",
            )
        ],
    )

    filed = filer.apply(result, mission_id="mission-1", round_id=1)

    assert filed.issue_proposals[0].filing_status == "skipped"
    assert "required" in filed.issue_proposals[0].filing_error
