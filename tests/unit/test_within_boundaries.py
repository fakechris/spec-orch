from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from spec_orch.domain.models import (
    GateInput,
    ReviewSummary,
    SpecDeviation,
    SpecSnapshot,
    VerificationSummary,
)
from spec_orch.services.deviation_service import load_deviations, write_deviations
from spec_orch.services.gate_service import GateService


def _make_snapshot(*, issue_id: str = "SPC-1") -> SpecSnapshot:
    from spec_orch.domain.models import Issue

    issue = Issue(issue_id=issue_id, title="test issue", summary="test")
    return SpecSnapshot(version=1, approved=True, approved_by="test", issue=issue)


def _make_deviation(*, file_path: str = "rogue.txt") -> SpecDeviation:
    return SpecDeviation(
        deviation_id="dev-abc12345",
        issue_id="SPC-1",
        description=f"File changed outside scope: {file_path}",
        severity="minor",
        detected_by="gate/scope_check",
        file_path=file_path,
    )


class TestWithinBoundariesGateEvaluation:
    """Gate evaluation respects within_boundaries flag."""

    def test_within_boundaries_true_passes_gate(self) -> None:
        svc = GateService()
        result = svc.evaluate(
            GateInput(
                spec_exists=True,
                spec_approved=True,
                within_boundaries=True,
                builder_succeeded=True,
                verification=VerificationSummary(
                    lint_passed=True, typecheck_passed=True, test_passed=True, build_passed=True
                ),
                review=ReviewSummary(verdict="pass", reviewed_by="alice"),
                human_acceptance=True,
            )
        )
        assert result.mergeable
        assert "within_boundaries" not in result.failed_conditions

    def test_within_boundaries_false_fails_gate(self) -> None:
        svc = GateService()
        result = svc.evaluate(
            GateInput(
                spec_exists=True,
                spec_approved=True,
                within_boundaries=False,
                builder_succeeded=True,
                verification=VerificationSummary(
                    lint_passed=True, typecheck_passed=True, test_passed=True, build_passed=True
                ),
                review=ReviewSummary(verdict="pass", reviewed_by="alice"),
                human_acceptance=True,
            )
        )
        assert not result.mergeable
        assert "within_boundaries" in result.failed_conditions


class TestDeviationDetection:
    """detect_deviations correctly drives within_boundaries."""

    @patch("spec_orch.services.deviation_service._get_changed_files", return_value=[])
    def test_no_deviations_means_within_boundaries(self, _mock_changed: object) -> None:
        from spec_orch.services.deviation_service import detect_deviations

        snapshot = _make_snapshot()
        deviations = detect_deviations(workspace=Path("/fake"), snapshot=snapshot)
        assert len(deviations) == 0
        assert (len(deviations) == 0) is True

    @patch(
        "spec_orch.services.deviation_service._get_changed_files",
        return_value=["outside/rogue.py"],
    )
    def test_deviations_means_outside_boundaries(self, _mock_changed: object) -> None:
        from spec_orch.domain.models import Issue, IssueContext
        from spec_orch.services.deviation_service import detect_deviations

        issue = Issue(
            issue_id="SPC-2",
            title="scoped issue",
            summary="test",
            context=IssueContext(files_to_read=["src/"]),
        )
        snapshot = SpecSnapshot(version=1, approved=True, approved_by="test", issue=issue)
        deviations = detect_deviations(workspace=Path("/fake"), snapshot=snapshot)
        assert len(deviations) > 0
        within_boundaries = len(deviations) == 0
        assert within_boundaries is False

    def test_no_snapshot_means_within_boundaries(self) -> None:
        from spec_orch.services.deviation_service import detect_deviations

        deviations = detect_deviations(workspace=Path("/fake"), snapshot=None)
        assert len(deviations) == 0


class TestDeviationsWrittenToDisk:
    """write_deviations persists to deviations.jsonl."""

    def test_write_and_load_round_trip(self, tmp_path: Path) -> None:
        devs = [_make_deviation(file_path="a.py"), _make_deviation(file_path="b.py")]
        path = write_deviations(tmp_path, devs)
        assert path.exists()
        assert path.name == "deviations.jsonl"

        loaded = load_deviations(tmp_path)
        assert len(loaded) == 2
        assert loaded[0].file_path == "a.py"
        assert loaded[1].file_path == "b.py"

    def test_no_deviations_file_returns_empty(self, tmp_path: Path) -> None:
        loaded = load_deviations(tmp_path)
        assert loaded == []
