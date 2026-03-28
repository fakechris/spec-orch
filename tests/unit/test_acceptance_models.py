from __future__ import annotations

from spec_orch.domain.models import (
    AcceptanceFinding,
    AcceptanceIssueProposal,
    AcceptanceReviewResult,
)


def test_acceptance_finding_round_trip() -> None:
    finding = AcceptanceFinding(
        severity="high",
        summary="Primary CTA is missing from the landing page.",
        details="The hero section does not render the expected start action.",
        expected="A visible primary CTA is present above the fold.",
        actual="No primary CTA is visible in the hero section.",
        route="/",
        artifact_paths={"screenshot": "rounds/round-01/acceptance/home.png"},
    )

    restored = AcceptanceFinding.from_dict(finding.to_dict())

    assert restored == finding


def test_acceptance_issue_proposal_round_trip() -> None:
    proposal = AcceptanceIssueProposal(
        title="Restore hero CTA in landing page",
        summary="Acceptance evaluator detected a missing primary CTA on the home page.",
        severity="high",
        confidence=0.91,
        repro_steps=[
            "Open the home page.",
            "Inspect the hero section above the fold.",
            "Observe that no primary CTA is present.",
        ],
        expected="A primary CTA is visible in the hero section.",
        actual="No primary CTA is visible in the hero section.",
        route="/",
        artifact_paths={"screenshot": "rounds/round-01/acceptance/home.png"},
    )

    restored = AcceptanceIssueProposal.from_dict(proposal.to_dict())

    assert restored == proposal


def test_acceptance_review_result_round_trip() -> None:
    result = AcceptanceReviewResult(
        status="fail",
        summary="The mission output is not acceptable yet.",
        confidence=0.88,
        evaluator="acceptance_llm",
        tested_routes=["/", "/settings"],
        findings=[
            AcceptanceFinding(
                severity="high",
                summary="Settings save action fails.",
                route="/settings",
            )
        ],
        issue_proposals=[
            AcceptanceIssueProposal(
                title="Fix settings save action",
                summary="Save action fails on the settings page.",
                severity="high",
            )
        ],
        artifacts={
            "acceptance_json": "rounds/round-01/acceptance_review.json",
            "home_screenshot": "rounds/round-01/acceptance/home.png",
        },
    )

    restored = AcceptanceReviewResult.from_dict(result.to_dict())

    assert restored == result
