from __future__ import annotations


def test_build_structural_judgment_surfaces_deterministic_channel() -> None:
    from spec_orch.services.structural_judgment import build_structural_judgment

    payload = build_structural_judgment(
        workspace_id="mission-judgment",
        review_status="warn",
        coverage_status="partial",
        untested_expected_routes=["/settings"],
        candidate_queue=[
            {
                "candidate_finding_id": "finding-1",
                "repro_status": "needs_repro",
            }
        ],
        compare_view={
            "compare_state": "active",
            "baseline_ref": "fixture:dashboard-transcript-baseline",
            "artifact_drift_count": 2,
        },
        evidence_panel={
            "route_count": 3,
            "artifact_count": 4,
        },
        overview={
            "candidate_finding_count": 1,
            "confirmed_issue_count": 0,
            "observation_count": 0,
        },
    )

    assert payload == {
        "structural_judgment_id": "mission-judgment:structural",
        "workspace_id": "mission-judgment",
        "quality_signal": "watch",
        "bottleneck": "candidate_repro_pending",
        "rule_violations": [
            {
                "rule_id": "coverage_incomplete",
                "severity": "medium",
                "summary": "Expected routes remain untested.",
                "details": {
                    "coverage_status": "partial",
                    "untested_route_count": 1,
                },
            },
            {
                "rule_id": "candidate_repro_pending",
                "severity": "medium",
                "summary": "Candidate findings still need repro before promotion.",
                "details": {
                    "pending_candidate_count": 1,
                },
            },
            {
                "rule_id": "baseline_drift_detected",
                "severity": "medium",
                "summary": "Compare overlay detected baseline drift artifacts.",
                "details": {
                    "artifact_drift_count": 2,
                    "baseline_ref": "fixture:dashboard-transcript-baseline",
                },
            },
        ],
        "baseline_diff": {
            "compare_state": "active",
            "baseline_ref": "fixture:dashboard-transcript-baseline",
            "artifact_drift_count": 2,
            "drift_status": "drift_detected",
        },
        "current_state": {
            "review_status": "warn",
            "coverage_status": "partial",
            "candidate_finding_count": 1,
            "confirmed_issue_count": 0,
            "observation_count": 0,
            "route_count": 3,
            "artifact_count": 4,
        },
    }


def test_build_structural_judgment_marks_regression_when_review_fails() -> None:
    from spec_orch.services.structural_judgment import build_structural_judgment

    payload = build_structural_judgment(
        workspace_id="mission-regression",
        review_status="fail",
        coverage_status="complete",
        untested_expected_routes=[],
        candidate_queue=[],
        compare_view={
            "compare_state": "inactive",
            "baseline_ref": "",
            "artifact_drift_count": 0,
        },
        evidence_panel={
            "route_count": 2,
            "artifact_count": 2,
        },
        overview={
            "candidate_finding_count": 0,
            "confirmed_issue_count": 1,
            "observation_count": 0,
        },
    )

    assert payload["quality_signal"] == "regression"
    assert payload["bottleneck"] == "confirmed_issue"
    assert payload["rule_violations"][0] == {
        "rule_id": "review_failed",
        "severity": "high",
        "summary": "Semantic review already marked this workspace as failing.",
        "details": {
            "review_status": "fail",
            "confirmed_issue_count": 1,
        },
    }
    assert payload["baseline_diff"]["drift_status"] == "not_compared"
