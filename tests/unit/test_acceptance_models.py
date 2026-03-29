from __future__ import annotations

from spec_orch.domain.models import (
    AcceptanceCampaign,
    AcceptanceFinding,
    AcceptanceInteractionStep,
    AcceptanceIssueProposal,
    AcceptanceMode,
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
    campaign = AcceptanceCampaign(
        mode=AcceptanceMode.IMPACT_SWEEP,
        goal="Validate the updated dashboard launcher across core mission routes.",
        primary_routes=["/launcher"],
        related_routes=["/", "/?tab=missions"],
        interaction_plans={
            "/launcher": [
                AcceptanceInteractionStep(
                    action="click_text",
                    target="Transcript",
                    description="Open transcript from the launcher mission view.",
                    value="",
                    timeout_ms=12000,
                )
            ]
        },
        coverage_expectations=["Mission launcher", "Mission list", "Mission detail"],
        required_interactions=["open launcher", "confirm mission appears in list"],
        min_primary_routes=1,
        related_route_budget=2,
        interaction_budget="moderate",
        filing_policy="auto_file_regressions_only",
        exploration_budget="medium",
    )
    result = AcceptanceReviewResult(
        status="fail",
        summary="The mission output is not acceptable yet.",
        confidence=0.88,
        evaluator="acceptance_llm",
        acceptance_mode="impact_sweep",
        coverage_status="partial",
        tested_routes=["/", "/settings"],
        untested_expected_routes=["/launcher"],
        recommended_next_step="Expand route coverage before filing aesthetic-only issues.",
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
        campaign=campaign,
    )

    restored = AcceptanceReviewResult.from_dict(result.to_dict())

    assert restored == result


def test_acceptance_campaign_round_trip() -> None:
    campaign = AcceptanceCampaign(
        mode=AcceptanceMode.EXPLORATORY,
        goal="Dogfood the operator console like a first-principles operator.",
        primary_routes=["/"],
        related_routes=["/?mode=inbox"],
        interaction_plans={
            "/?mode=inbox": [
                AcceptanceInteractionStep(
                    action="click_text",
                    target="All Missions",
                    description="Switch into the mission inventory view.",
                    value="",
                    timeout_ms=8000,
                )
            ]
        },
        coverage_expectations=["Mission control", "Acceptance surface"],
        required_interactions=["switch work modes", "inspect mission detail"],
        min_primary_routes=1,
        related_route_budget=3,
        interaction_budget="wide",
        filing_policy="hold_ux_concerns_for_operator_review",
        exploration_budget="wide",
    )

    restored = AcceptanceCampaign.from_dict(campaign.to_dict())

    assert restored == campaign


def test_acceptance_campaign_from_dict_coerces_invalid_route_budgets_to_zero() -> None:
    restored = AcceptanceCampaign.from_dict(
        {
            "mode": AcceptanceMode.IMPACT_SWEEP.value,
            "goal": "Validate mission routes.",
            "primary_routes": ["/"],
            "related_routes": ["/?mission=1&tab=transcript"],
            "min_primary_routes": "abc",
            "related_route_budget": object(),
        }
    )

    assert restored.min_primary_routes == 0
    assert restored.related_route_budget == 0


def test_acceptance_campaign_round_trip_supports_workflow_mode() -> None:
    campaign = AcceptanceCampaign(
        mode=AcceptanceMode.WORKFLOW,
        goal="Complete the launcher-to-mission-control operator workflow.",
        primary_routes=["/"],
        related_routes=["/?mission=workflow-smoke&mode=missions&tab=transcript"],
        interaction_plans={
            "/": [
                AcceptanceInteractionStep(
                    action="click_selector",
                    target='[data-automation-target="mission-card"][data-mission-id="workflow-smoke"]',
                    description="Select the workflow smoke mission from the mission list.",
                    value="",
                    timeout_ms=4000,
                )
            ]
        },
        coverage_expectations=["launcher flow", "mission selection", "transcript tab"],
        required_interactions=["select mission", "switch transcript tab"],
        min_primary_routes=2,
        related_route_budget=1,
        interaction_budget="moderate",
        filing_policy="auto_file_broken_flows_only",
        exploration_budget="bounded",
    )

    restored = AcceptanceCampaign.from_dict(campaign.to_dict())

    assert restored == campaign


def test_acceptance_interaction_step_round_trip_preserves_fill_value() -> None:
    step = AcceptanceInteractionStep(
        action="fill_selector",
        target='[data-automation-target="launcher-field"][data-field-key="title"]',
        description="Fill the launcher title field.",
        value="Workflow Smoke Mission",
        timeout_ms=15000,
    )

    restored = AcceptanceInteractionStep.from_dict(step.to_dict())

    assert restored == step


def test_acceptance_interaction_step_from_dict_coerces_invalid_timeout_to_zero() -> None:
    restored = AcceptanceInteractionStep.from_dict(
        {
            "action": "wait_for_selector",
            "target": '[data-automation-target="launcher-status"][data-tone="success"]',
            "timeout_ms": "not-a-number",
        }
    )

    assert restored.timeout_ms == 0
