"""Surface-pack and calibration helpers for acceptance_core."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from spec_orch.acceptance_core.models import AcceptanceJudgment, AcceptanceJudgmentClass
from spec_orch.domain.models import AcceptanceReviewResult


@dataclass(slots=True)
class AcceptanceSurfacePack:
    pack_key: str
    subject_kind: str
    subject_id: str
    critique_axes: list[str] = field(default_factory=list)
    seed_routes: list[str] = field(default_factory=list)
    safe_action_budget: str = "bounded"
    fixture_names: list[str] = field(default_factory=list)
    baseline_evidence_shape: list[str] = field(default_factory=list)
    gold_judgments: list[str] = field(default_factory=list)
    tuned_graph_notes: list[str] = field(default_factory=list)
    expected_step_artifacts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pack_key": self.pack_key,
            "subject_kind": self.subject_kind,
            "subject_id": self.subject_id,
            "critique_axes": list(self.critique_axes),
            "seed_routes": list(self.seed_routes),
            "safe_action_budget": self.safe_action_budget,
            "fixture_names": list(self.fixture_names),
            "baseline_evidence_shape": list(self.baseline_evidence_shape),
            "gold_judgments": list(self.gold_judgments),
            "tuned_graph_notes": list(self.tuned_graph_notes),
            "expected_step_artifacts": list(self.expected_step_artifacts),
        }


@dataclass(slots=True)
class AcceptanceCalibrationFixture:
    fixture_name: str
    review: AcceptanceReviewResult
    expected: dict[str, Any]


@dataclass(slots=True)
class AcceptanceCalibrationComparison:
    fixture_name: str
    matches: bool
    mismatches: list[str] = field(default_factory=list)
    expected_status: str = ""
    actual_status: str = ""
    expected_acceptance_mode: str = ""
    actual_acceptance_mode: str = ""
    expected_coverage_status: str = ""
    actual_coverage_status: str = ""
    field_drift: dict[str, dict[str, Any]] = field(default_factory=dict)
    step_artifact_drift: dict[str, list[str]] = field(default_factory=dict)
    graph_profile_drift: dict[str, str] = field(default_factory=dict)
    graph_transition_drift: dict[str, list[str]] = field(default_factory=dict)
    workflow_tuning_drift: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_name": self.fixture_name,
            "matches": self.matches,
            "mismatches": list(self.mismatches),
            "expected_status": self.expected_status,
            "actual_status": self.actual_status,
            "expected_acceptance_mode": self.expected_acceptance_mode,
            "actual_acceptance_mode": self.actual_acceptance_mode,
            "expected_coverage_status": self.expected_coverage_status,
            "actual_coverage_status": self.actual_coverage_status,
            "field_drift": dict(self.field_drift),
            "step_artifact_drift": {k: list(v) for k, v in self.step_artifact_drift.items()},
            "graph_profile_drift": dict(self.graph_profile_drift),
            "graph_transition_drift": {k: list(v) for k, v in self.graph_transition_drift.items()},
            "workflow_tuning_drift": dict(self.workflow_tuning_drift),
        }


class FixtureGraduationStage(StrEnum):
    FIXTURE_CANDIDATE = "fixture_candidate"
    REGRESSION_ASSET = "regression_asset"


def dashboard_surface_pack_v1(mission_id: str) -> AcceptanceSurfacePack:
    return AcceptanceSurfacePack(
        pack_key="dashboard_surface_pack_v1",
        subject_kind="mission",
        subject_id=mission_id,
        critique_axes=[
            "evidence_discoverability",
            "surface_orientation",
            "task_continuity",
            "operator_comprehension",
        ],
        seed_routes=[
            "/",
            f"/?mission={mission_id}&mode=missions&tab=overview",
        ],
        safe_action_budget="bounded",
        fixture_names=[
            "feature_scoped_launcher_regression",
            "workflow_dashboard_repair_loop",
            "exploratory_dashboard_ux_hold",
            "exploratory_dashboard_orientation_hold",
            "dogfood_dashboard_regression",
        ],
        baseline_evidence_shape=[
            "acceptance_review",
            "browser_evidence",
            "visual_gallery",
            "round_summary",
        ],
        gold_judgments=[
            "confirmed_issue",
            "candidate_finding",
            "observation",
        ],
        tuned_graph_notes=[
            "dashboard surfaces may activate tuned compare/replay graphs",
            "workflow tuning can change loop placement and evidence handoff shape",
        ],
        expected_step_artifacts=[
            "browser_evidence.json",
            "acceptance_review.json",
            "round_summary.json",
        ],
    )


def _acceptance_fixture_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "acceptance"


def load_acceptance_calibration_fixture(fixture_name: str) -> AcceptanceCalibrationFixture:
    path = _acceptance_fixture_dir() / f"{fixture_name}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if "review" in payload:
        review_payload = payload["review"]
        expected_payload = payload.get("expected", {})
    else:
        review_payload = payload["rounds"][-1]["review"]
        expected_payload = payload.get("expected", {}).get("latest_review", {})
    return AcceptanceCalibrationFixture(
        fixture_name=fixture_name,
        review=AcceptanceReviewResult.from_dict(review_payload),
        expected=expected_payload if isinstance(expected_payload, dict) else {},
    )


def compare_review_to_fixture(
    actual: AcceptanceReviewResult,
    fixture: AcceptanceCalibrationFixture,
) -> AcceptanceCalibrationComparison:
    mismatches: list[str] = []
    expected_status = str(fixture.expected.get("status") or fixture.review.status)
    expected_mode = str(
        fixture.expected.get("acceptance_mode") or fixture.review.acceptance_mode or ""
    )
    expected_coverage = str(
        fixture.expected.get("coverage_status") or fixture.review.coverage_status or ""
    )
    actual_mode = str(actual.acceptance_mode or "")
    actual_coverage = str(actual.coverage_status or "")
    field_drift: dict[str, dict[str, Any]] = {}
    step_artifact_drift: dict[str, list[str]] = {}
    graph_profile_drift: dict[str, str] = {}
    graph_transition_drift: dict[str, list[str]] = {}
    workflow_tuning_drift: dict[str, str] = {}
    if actual.status != expected_status:
        mismatches.append("status")
    if actual_mode != expected_mode:
        mismatches.append("acceptance_mode")
    if actual_coverage != expected_coverage:
        mismatches.append("coverage_status")
    expected_fields = fixture.expected.get("field_expectations")
    if isinstance(expected_fields, dict):
        actual_fields = actual.artifacts if isinstance(actual.artifacts, dict) else {}
        for key, expected_value in expected_fields.items():
            actual_value = actual_fields.get(key)
            if actual_value != expected_value:
                mismatches.append(f"field:{key}")
                field_drift[key] = {"expected": expected_value, "actual": actual_value}
        if (
            "graph_profile" in expected_fields
            and "graph_profile" in actual_fields
            and actual_fields.get("graph_profile") != expected_fields.get("graph_profile")
        ):
            graph_profile_drift = {
                "expected": str(expected_fields.get("graph_profile") or ""),
                "actual": str(actual_fields.get("graph_profile") or ""),
            }
            workflow_tuning_drift["graph_profile"] = "tuned_graph_mismatch"
        if "workflow_tuning_notes" in expected_fields and actual_fields.get(
            "workflow_tuning_notes"
        ) != expected_fields.get("workflow_tuning_notes"):
            mismatches.append("field:workflow_tuning_notes")
            field_drift["workflow_tuning_notes"] = {
                "expected": expected_fields.get("workflow_tuning_notes"),
                "actual": actual_fields.get("workflow_tuning_notes"),
            }
            workflow_tuning_drift["workflow_tuning_notes"] = "tuning_notes_mismatch"
    expected_step_artifacts = fixture.expected.get("step_artifacts")
    actual_step_artifacts = []
    actual_artifacts = actual.artifacts if isinstance(actual.artifacts, dict) else {}
    if isinstance(actual_artifacts.get("step_artifacts"), list):
        actual_step_artifacts = [str(item) for item in actual_artifacts["step_artifacts"]]
    if isinstance(expected_step_artifacts, list):
        expected_steps = [str(item) for item in expected_step_artifacts]
        missing = sorted(set(expected_steps) - set(actual_step_artifacts))
        unexpected = sorted(set(actual_step_artifacts) - set(expected_steps))
        if missing or unexpected:
            mismatches.append("step_artifacts")
            step_artifact_drift = {
                "missing": missing,
                "unexpected": unexpected,
            }
            if missing:
                workflow_tuning_drift["step_artifacts"] = "expected_step_artifacts_missing"
            elif unexpected:
                workflow_tuning_drift["step_artifacts"] = "unexpected_step_artifacts_present"
    expected_graph_transitions = fixture.expected.get("graph_transitions")
    actual_graph_transitions = []
    if isinstance(actual_artifacts.get("graph_transitions"), list):
        actual_graph_transitions = [str(item) for item in actual_artifacts["graph_transitions"]]
    if isinstance(expected_graph_transitions, list):
        expected_transitions = [str(item) for item in expected_graph_transitions]
        missing_transitions = sorted(set(expected_transitions) - set(actual_graph_transitions))
        unexpected_transitions = sorted(set(actual_graph_transitions) - set(expected_transitions))
        if missing_transitions or unexpected_transitions:
            mismatches.append("graph_transitions")
            graph_transition_drift = {
                "missing": missing_transitions,
                "unexpected": unexpected_transitions,
            }
            workflow_tuning_drift["graph_transitions"] = "transition_path_mismatch"
    return AcceptanceCalibrationComparison(
        fixture_name=fixture.fixture_name,
        matches=not mismatches,
        mismatches=mismatches,
        expected_status=expected_status,
        actual_status=actual.status,
        expected_acceptance_mode=expected_mode,
        actual_acceptance_mode=actual_mode,
        expected_coverage_status=expected_coverage,
        actual_coverage_status=actual_coverage,
        field_drift=field_drift,
        step_artifact_drift=step_artifact_drift,
        graph_profile_drift=graph_profile_drift,
        graph_transition_drift=graph_transition_drift,
        workflow_tuning_drift=workflow_tuning_drift,
    )


def fixture_graduation_history_path(repo_root: Path, mission_id: str) -> Path:
    return (
        Path(repo_root) / "docs" / "specs" / mission_id / "operator" / "fixture_graduations.jsonl"
    )


def append_fixture_graduation_event(
    repo_root: Path,
    *,
    mission_id: str,
    judgment_id: str,
    stage: FixtureGraduationStage,
    summary: str,
    source_record_id: str,
    evidence_refs: list[str],
) -> dict[str, Any]:
    payload = {
        "judgment_id": judgment_id,
        "stage": stage.value,
        "summary": summary,
        "source_record_id": source_record_id,
        "evidence_refs": list(evidence_refs),
    }
    path = fixture_graduation_history_path(repo_root, mission_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return payload


def load_fixture_graduation_events(repo_root: Path, mission_id: str) -> list[dict[str, Any]]:
    path = fixture_graduation_history_path(repo_root, mission_id)
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def run_acceptance_calibration_harness(
    *,
    fixture_names: list[str],
    actual_reviews: dict[str, AcceptanceReviewResult],
) -> dict[str, Any]:
    comparisons: list[AcceptanceCalibrationComparison] = []
    missing_actual_reviews = 0
    for name in fixture_names:
        fixture = load_acceptance_calibration_fixture(name)
        actual = actual_reviews.get(name)
        if actual is None:
            missing_actual_reviews += 1
            comparisons.append(
                AcceptanceCalibrationComparison(
                    fixture_name=name,
                    matches=False,
                    mismatches=["missing_review"],
                    expected_status=str(fixture.expected.get("status") or fixture.review.status),
                    actual_status="missing_review",
                    expected_acceptance_mode=str(
                        fixture.expected.get("acceptance_mode")
                        or fixture.review.acceptance_mode
                        or ""
                    ),
                    actual_acceptance_mode="",
                    expected_coverage_status=str(
                        fixture.expected.get("coverage_status")
                        or fixture.review.coverage_status
                        or ""
                    ),
                    actual_coverage_status="",
                    workflow_tuning_drift={"review": "missing_actual_review"},
                )
            )
            continue
        comparisons.append(compare_review_to_fixture(actual, fixture))
    mismatched = [item for item in comparisons if not item.matches]
    return {
        "summary": {
            "total": len(comparisons),
            "matched": len(comparisons) - len(mismatched),
            "mismatched": len(mismatched),
            "missing_actual_reviews": missing_actual_reviews,
        },
        "comparisons": [item.to_dict() for item in comparisons],
    }


def qualifies_for_fixture_candidate(
    judgment: AcceptanceJudgment,
    *,
    repeat_count: int,
) -> bool:
    return (
        judgment.judgment_class is AcceptanceJudgmentClass.CANDIDATE_FINDING and repeat_count >= 3
    )


__all__ = [
    "AcceptanceCalibrationComparison",
    "AcceptanceCalibrationFixture",
    "AcceptanceSurfacePack",
    "FixtureGraduationStage",
    "append_fixture_graduation_event",
    "compare_review_to_fixture",
    "dashboard_surface_pack_v1",
    "fixture_graduation_history_path",
    "load_acceptance_calibration_fixture",
    "load_fixture_graduation_events",
    "qualifies_for_fixture_candidate",
    "run_acceptance_calibration_harness",
]
