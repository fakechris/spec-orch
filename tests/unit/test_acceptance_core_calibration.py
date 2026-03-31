from __future__ import annotations

from pathlib import Path

from spec_orch.domain.models import AcceptanceReviewResult


def test_dashboard_surface_pack_v1_uses_existing_operator_console_fixtures() -> None:
    from spec_orch.acceptance_core.calibration import dashboard_surface_pack_v1

    pack = dashboard_surface_pack_v1("operator-console")

    assert pack.pack_key == "dashboard_surface_pack_v1"
    assert pack.subject_kind == "mission"
    assert pack.subject_id == "operator-console"
    assert pack.safe_action_budget == "bounded"
    assert pack.seed_routes == [
        "/",
        "/?mission=operator-console&mode=missions&tab=overview",
    ]
    assert pack.fixture_names == [
        "feature_scoped_launcher_regression",
        "workflow_dashboard_repair_loop",
        "exploratory_dashboard_ux_hold",
        "exploratory_dashboard_orientation_hold",
        "dogfood_dashboard_regression",
    ]
    assert "evidence_discoverability" in pack.critique_axes
    assert "surface_orientation" in pack.critique_axes


def test_compare_calibration_harness_flags_mismatch_against_fixture() -> None:
    from spec_orch.acceptance_core.calibration import (
        compare_review_to_fixture,
        load_acceptance_calibration_fixture,
    )

    fixture = load_acceptance_calibration_fixture("feature_scoped_launcher_regression")
    actual = AcceptanceReviewResult(
        status="warn",
        summary="Regression exists but was under-classified.",
        confidence=0.95,
        evaluator="acceptance_llm",
        acceptance_mode="feature_scoped",
        coverage_status="complete",
        findings=[],
        issue_proposals=[],
        artifacts={},
    )

    comparison = compare_review_to_fixture(actual, fixture)

    assert comparison.fixture_name == "feature_scoped_launcher_regression"
    assert comparison.matches is False
    assert "status" in comparison.mismatches


def test_compare_calibration_harness_matches_fixture_when_semantics_align() -> None:
    from spec_orch.acceptance_core.calibration import (
        compare_review_to_fixture,
        load_acceptance_calibration_fixture,
    )

    fixture = load_acceptance_calibration_fixture("workflow_dashboard_repair_loop")
    actual = AcceptanceReviewResult.from_dict(fixture.review.to_dict())

    comparison = compare_review_to_fixture(actual, fixture)

    assert comparison.matches is True
    assert comparison.mismatches == []


def test_compare_calibration_harness_captures_field_and_step_artifact_drift() -> None:
    from spec_orch.acceptance_core.calibration import (
        AcceptanceCalibrationComparison,
        AcceptanceCalibrationFixture,
        compare_review_to_fixture,
    )

    fixture = AcceptanceCalibrationFixture(
        fixture_name="semantic-drift-demo",
        review=AcceptanceReviewResult(
            status="warn",
            summary="Expected baseline review.",
            confidence=0.82,
            evaluator="acceptance_llm",
            acceptance_mode="exploratory",
            coverage_status="complete",
            findings=[],
            issue_proposals=[],
            artifacts={},
        ),
        expected={
            "field_expectations": {
                "judgment_class": "candidate_finding",
                "graph_profile": "tuned_dashboard_compare_graph",
            },
            "step_artifacts": ["browser_evidence.json", "step:transcript-empty-state"],
        },
    )

    actual = AcceptanceReviewResult(
        status="warn",
        summary="Actual review drifted semantically.",
        confidence=0.81,
        evaluator="acceptance_llm",
        acceptance_mode="exploratory",
        coverage_status="complete",
        findings=[],
        issue_proposals=[],
        artifacts={
            "judgment_class": "observation",
            "graph_profile": "exploratory_probe_graph",
            "step_artifacts": ["browser_evidence.json"],
        },
    )

    comparison = compare_review_to_fixture(actual, fixture)

    assert isinstance(comparison, AcceptanceCalibrationComparison)
    assert comparison.matches is False
    assert comparison.field_drift["judgment_class"]["expected"] == "candidate_finding"
    assert comparison.field_drift["judgment_class"]["actual"] == "observation"
    assert comparison.step_artifact_drift["missing"] == ["step:transcript-empty-state"]


def test_candidate_to_fixture_graduation_trail_persists_audit_log(tmp_path: Path) -> None:
    from spec_orch.acceptance_core.calibration import (
        FixtureGraduationStage,
        append_fixture_graduation_event,
        load_fixture_graduation_events,
    )

    payload = append_fixture_graduation_event(
        tmp_path,
        mission_id="mission-1",
        judgment_id="judgment-1",
        stage=FixtureGraduationStage.FIXTURE_CANDIDATE,
        summary="Repeated candidate finding promoted into fixture candidate.",
        source_record_id="acceptance:judgment-1",
        evidence_refs=["docs/specs/mission-1/rounds/round-01/acceptance_review.json"],
    )

    events = load_fixture_graduation_events(tmp_path, "mission-1")

    assert payload["stage"] == "fixture_candidate"
    assert events[0]["judgment_id"] == "judgment-1"
    assert events[0]["source_record_id"] == "acceptance:judgment-1"
    assert events[0]["evidence_refs"] == [
        "docs/specs/mission-1/rounds/round-01/acceptance_review.json"
    ]


def test_build_fixture_graduation_event_includes_graph_trace_metadata() -> None:
    from spec_orch.acceptance_core.calibration import (
        FixtureGraduationStage,
        build_fixture_graduation_event,
    )
    from spec_orch.acceptance_core.models import (
        AcceptanceJudgment,
        AcceptanceJudgmentClass,
        AcceptanceRunMode,
        AcceptanceWorkflowState,
        CandidateFinding,
    )

    judgment = AcceptanceJudgment(
        judgment_id="proposal:promoted",
        judgment_class=AcceptanceJudgmentClass.CANDIDATE_FINDING,
        run_mode=AcceptanceRunMode.EXPLORE,
        workflow_state=AcceptanceWorkflowState.PROMOTED,
        summary="Transcript route needs stronger orientation.",
        candidate=CandidateFinding(
            finding_id="candidate:promoted",
            claim="Transcript route needs stronger orientation.",
            route="/?mission=mission-1&mode=missions&tab=transcript",
            evidence_refs=["docs/specs/mission-1/rounds/round-01/acceptance_review.json"],
            baseline_ref="fixture:dashboard-transcript-regression",
            origin_step="candidate_review",
            graph_profile="tuned_exploratory_graph",
            run_mode="explore",
            compare_overlay=True,
            promotion_test="Replay transcript route with orientation breadcrumbs visible.",
            recommended_next_step="Promote to fixture candidate.",
            dedupe_key="dashboard:transcript-orientation",
        ),
    )

    payload = build_fixture_graduation_event(
        mission_id="mission-1",
        judgment=judgment,
        stage=FixtureGraduationStage.FIXTURE_CANDIDATE,
        source_record_id="acceptance:proposal:promoted",
        repeat_count=3,
        review_artifacts={
            "graph_run": "docs/specs/mission-1/rounds/round-01/acceptance_graph/graph_run.json",
            "step_artifacts": [
                "docs/specs/mission-1/rounds/round-01/acceptance_graph/steps/01-surface_scan.json",
                "docs/specs/mission-1/rounds/round-01/acceptance_graph/steps/02-guided_probe.json",
            ],
            "graph_transitions": [
                "surface_scan->guided_probe",
                "guided_probe->candidate_review",
                "candidate_review->summarize_judgment",
            ],
            "final_transition": "summarize_judgment",
            "workflow_tuning_notes": ["tuned graph used transcript-specific step hints"],
        },
    )

    assert payload["stage"] == "fixture_candidate"
    assert payload["finding_id"] == "candidate:promoted"
    assert payload["dedupe_key"] == "dashboard:transcript-orientation"
    assert payload["repeat_count"] == 3
    assert payload["baseline_ref"] == "fixture:dashboard-transcript-regression"
    assert payload["graph_profile"] == "tuned_exploratory_graph"
    assert payload["graph_run"].endswith("graph_run.json")
    assert payload["step_artifacts"][0].endswith("01-surface_scan.json")
    assert payload["graph_transitions"][-1] == "candidate_review->summarize_judgment"
    assert payload["workflow_tuning_notes"] == ["tuned graph used transcript-specific step hints"]
    assert payload["evidence_refs"] == [
        "docs/specs/mission-1/rounds/round-01/acceptance_review.json",
        "docs/specs/mission-1/rounds/round-01/acceptance_graph/graph_run.json",
        "docs/specs/mission-1/rounds/round-01/acceptance_graph/steps/01-surface_scan.json",
        "docs/specs/mission-1/rounds/round-01/acceptance_graph/steps/02-guided_probe.json",
    ]


def test_calibration_harness_aggregates_fixture_comparisons() -> None:
    from spec_orch.acceptance_core.calibration import run_acceptance_calibration_harness
    from spec_orch.domain.models import AcceptanceReviewResult

    actual = {
        "feature_scoped_launcher_regression": AcceptanceReviewResult(
            status="fail",
            summary="Launcher regression still reproduces.",
            confidence=0.95,
            evaluator="acceptance_llm",
            acceptance_mode="feature_scoped",
            coverage_status="complete",
            findings=[],
            issue_proposals=[],
            artifacts={},
        ),
        "workflow_dashboard_repair_loop": AcceptanceReviewResult(
            status="warn",
            summary="Workflow issue was under-called.",
            confidence=0.96,
            evaluator="acceptance_llm",
            acceptance_mode="workflow",
            coverage_status="complete",
            findings=[],
            issue_proposals=[],
            artifacts={},
        ),
    }

    result = run_acceptance_calibration_harness(
        fixture_names=[
            "feature_scoped_launcher_regression",
            "workflow_dashboard_repair_loop",
        ],
        actual_reviews=actual,
    )

    assert result["summary"]["total"] == 2
    assert result["summary"]["matched"] == 1
    assert result["summary"]["mismatched"] == 1
    assert result["comparisons"][1]["fixture_name"] == "workflow_dashboard_repair_loop"
    assert result["comparisons"][1]["matches"] is False


def test_calibration_harness_gracefully_reports_missing_actual_review() -> None:
    from spec_orch.acceptance_core.calibration import run_acceptance_calibration_harness

    result = run_acceptance_calibration_harness(
        fixture_names=["feature_scoped_launcher_regression"],
        actual_reviews={},
    )

    assert result["summary"]["total"] == 1
    assert result["summary"]["matched"] == 0
    assert result["summary"]["mismatched"] == 1
    assert result["summary"]["missing_actual_reviews"] == 1
    assert result["comparisons"][0]["fixture_name"] == "feature_scoped_launcher_regression"
    assert "missing_review" in result["comparisons"][0]["mismatches"]


def test_calibration_harness_reports_workflow_tuning_drift() -> None:
    from spec_orch.acceptance_core.calibration import (
        AcceptanceCalibrationFixture,
        compare_review_to_fixture,
    )

    fixture = AcceptanceCalibrationFixture(
        fixture_name="workflow-drift-demo",
        review=AcceptanceReviewResult(
            status="warn",
            summary="Expected tuned graph review.",
            confidence=0.8,
            evaluator="acceptance_llm",
            acceptance_mode="exploratory",
            coverage_status="complete",
            findings=[],
            issue_proposals=[],
            artifacts={},
        ),
        expected={
            "field_expectations": {
                "graph_profile": "tuned_dashboard_compare_graph",
                "workflow_tuning_notes": ["compare overlay expected"],
            },
            "step_artifacts": ["browser_evidence.json", "step:transcript-empty-state"],
        },
    )
    actual = AcceptanceReviewResult(
        status="warn",
        summary="Actual review used a weaker graph.",
        confidence=0.8,
        evaluator="acceptance_llm",
        acceptance_mode="exploratory",
        coverage_status="complete",
        findings=[],
        issue_proposals=[],
        artifacts={
            "graph_profile": "exploratory_probe_graph",
            "workflow_tuning_notes": [],
            "step_artifacts": ["browser_evidence.json"],
        },
    )

    comparison = compare_review_to_fixture(actual, fixture)

    assert comparison.matches is False
    assert comparison.workflow_tuning_drift["graph_profile"] == "tuned_graph_mismatch"
    assert comparison.workflow_tuning_drift["step_artifacts"] == "expected_step_artifacts_missing"


def test_calibration_harness_reports_graph_transition_drift() -> None:
    from spec_orch.acceptance_core.calibration import (
        AcceptanceCalibrationFixture,
        compare_review_to_fixture,
    )

    fixture = AcceptanceCalibrationFixture(
        fixture_name="graph-transition-drift-demo",
        review=AcceptanceReviewResult(
            status="warn",
            summary="Expected graph transition shape.",
            confidence=0.8,
            evaluator="acceptance_llm",
            acceptance_mode="exploratory",
            coverage_status="complete",
            findings=[],
            issue_proposals=[],
            artifacts={},
        ),
        expected={
            "graph_transitions": [
                "surface_scan->guided_probe",
                "guided_probe->candidate_review",
                "candidate_review->summarize_judgment",
            ]
        },
    )
    actual = AcceptanceReviewResult(
        status="warn",
        summary="Actual graph skipped candidate review.",
        confidence=0.8,
        evaluator="acceptance_llm",
        acceptance_mode="exploratory",
        coverage_status="complete",
        findings=[],
        issue_proposals=[],
        artifacts={
            "graph_transitions": [
                "surface_scan->guided_probe",
                "guided_probe->summarize_judgment",
            ]
        },
    )

    comparison = compare_review_to_fixture(actual, fixture)

    assert comparison.matches is False
    assert comparison.workflow_tuning_drift["graph_transitions"] == "transition_path_mismatch"
    assert comparison.graph_transition_drift["missing"] == [
        "candidate_review->summarize_judgment",
        "guided_probe->candidate_review",
    ]


def test_candidate_finding_qualifies_for_fixture_candidate_when_reviewed_repeatedly() -> None:
    from spec_orch.acceptance_core.calibration import qualifies_for_fixture_candidate
    from spec_orch.acceptance_core.models import (
        AcceptanceJudgment,
        AcceptanceJudgmentClass,
        AcceptanceRunMode,
        AcceptanceWorkflowState,
        CandidateFinding,
    )

    judgment = AcceptanceJudgment(
        judgment_id="candidate-1",
        judgment_class=AcceptanceJudgmentClass.CANDIDATE_FINDING,
        run_mode=AcceptanceRunMode.EXPLORE,
        workflow_state=AcceptanceWorkflowState.REVIEWED,
        summary="Transcript entry point is not self-evident.",
        candidate=CandidateFinding(
            finding_id="candidate-1",
            claim="Transcript entry point is not self-evident.",
            route="/?mission=demo&mode=missions&tab=transcript",
            confidence=0.68,
            impact_if_true="Operators may miss the main evidence path.",
            repro_status="credible",
            hold_reason="Needs repeated confirmation.",
            promotion_test="Seen in multiple rounds.",
            recommended_next_step="Promote to fixture candidate when repeated.",
            dedupe_key="transcript-entrypoint",
        ),
    )

    assert qualifies_for_fixture_candidate(judgment, repeat_count=2) is False
    assert qualifies_for_fixture_candidate(judgment, repeat_count=3) is True
