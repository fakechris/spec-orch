from __future__ import annotations

import json
from pathlib import Path

import pytest

from spec_orch.domain.models import AcceptanceReviewResult

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "acceptance"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / f"{name}.json").read_text(encoding="utf-8"))


class _StubLinearClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def create_issue(
        self,
        *,
        team_key: str,
        title: str,
        description: str = "",
    ) -> dict[str, str]:
        self.calls.append(
            {
                "team_key": team_key,
                "title": title,
                "description": description,
            }
        )
        identifier = f"SON-{900 + len(self.calls)}"
        return {"id": f"issue-{len(self.calls)}", "identifier": identifier, "title": title}


@pytest.mark.parametrize(
    ("fixture_name", "mission_id", "round_id"),
    [
        ("feature_scoped_launcher_regression", "launcher-smoke", 2),
        ("workflow_dashboard_repair_loop", "workflow-smoke", 4),
        ("exploratory_dashboard_ux_hold", "operator-console-smoke", 3),
    ],
)
def test_acceptance_calibration_fixture_round_trips_and_applies_filing_policy(
    fixture_name: str,
    mission_id: str,
    round_id: int,
) -> None:
    from spec_orch.services.acceptance.linear_filing import LinearAcceptanceFiler

    payload = _load_fixture(fixture_name)
    result = AcceptanceReviewResult.from_dict(payload["review"])

    assert result.acceptance_mode == payload["expected"]["acceptance_mode"]
    assert result.coverage_status == payload["expected"]["coverage_status"]

    restored = AcceptanceReviewResult.from_dict(result.to_dict())
    assert restored.acceptance_mode == result.acceptance_mode
    assert restored.coverage_status == result.coverage_status
    assert restored.campaign is not None

    client = _StubLinearClient()
    filer = LinearAcceptanceFiler(client=client, team_key="SON", min_confidence=0.8)
    filed = filer.apply(restored, mission_id=mission_id, round_id=round_id)

    assert [proposal.filing_status for proposal in filed.issue_proposals] == payload["expected"][
        "filed_statuses"
    ]
    assert len(client.calls) == payload["expected"]["linear_calls"]


def test_acceptance_calibration_dogfood_fixture_builds_dashboard_summary(tmp_path: Path) -> None:
    from spec_orch.dashboard.surfaces import _gather_mission_acceptance_review

    payload = _load_fixture("dogfood_dashboard_regression")
    mission_id = payload["mission_id"]
    rounds_dir = tmp_path / "docs" / "specs" / mission_id / "rounds"

    for item in payload["rounds"]:
        round_dir = rounds_dir / f"round-{item['round_id']:02d}"
        round_dir.mkdir(parents=True, exist_ok=True)
        (round_dir / "acceptance_review.json").write_text(
            json.dumps(item["review"]),
            encoding="utf-8",
        )

    data = _gather_mission_acceptance_review(tmp_path, mission_id)

    expected_summary = payload["expected"]["summary"]
    assert data["summary"]["total_reviews"] == expected_summary["total_reviews"]
    assert data["summary"]["passes"] == expected_summary["passes"]
    assert data["summary"]["warnings"] == expected_summary["warnings"]
    assert data["summary"]["failures"] == expected_summary["failures"]
    assert data["summary"]["filed_issues"] == expected_summary["filed_issues"]

    latest = data["latest_review"]
    assert latest is not None
    assert latest["round_id"] == payload["expected"]["latest_review"]["round_id"]
    assert latest["status"] == payload["expected"]["latest_review"]["status"]
    assert latest["coverage_status"] == payload["expected"]["latest_review"]["coverage_status"]
    assert latest["acceptance_mode"] == payload["expected"]["latest_review"]["acceptance_mode"]
    assert data["reviews"][0]["round_id"] == 1
    assert data["reviews"][-1]["round_id"] == 3


def test_exploratory_calibration_fixture_carries_bounded_exploration_contract() -> None:
    payload = _load_fixture("exploratory_dashboard_ux_hold")
    result = AcceptanceReviewResult.from_dict(payload["review"])

    assert result.campaign is not None
    assert result.campaign.mode.value == "exploratory"
    assert result.campaign.seed_routes == [
        "/",
        "/?mission=operator-console&mode=missions&tab=overview",
    ]
    assert result.campaign.allowed_expansions == [
        "/?mission=operator-console&mode=missions&tab=transcript",
        "/?mission=operator-console&mode=missions&tab=acceptance",
        "/?mission=operator-console&mode=missions&tab=costs",
    ]
    assert result.campaign.critique_focus == [
        "information architecture confusion",
        "ambiguous terminology",
        "discoverability gaps",
    ]
    assert result.campaign.stop_conditions == [
        "stop when the route budget is exhausted",
        "stop when no adjacent surface adds new operator evidence",
    ]
    assert result.campaign.evidence_budget == "bounded"
