"""Tests for SpecDeviation, deviation tracking, and retrospective."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from spec_orch.cli import app
from spec_orch.domain.models import (
    Issue,
    IssueContext,
    SpecDeviation,
    SpecSnapshot,
)
from spec_orch.services.deviation_service import (
    detect_deviations,
    load_deviations,
    write_deviations,
)


def _make_snapshot(
    files_to_read: list[str] | None = None,
    acceptance_criteria: list[str] | None = None,
) -> SpecSnapshot:
    issue = Issue(
        issue_id="TEST-1",
        title="Test Issue",
        summary="Test",
        context=IssueContext(files_to_read=files_to_read or []),
        acceptance_criteria=acceptance_criteria or ["Tests pass"],
    )
    return SpecSnapshot(
        version=1,
        approved=True,
        approved_by="test",
        issue=issue,
    )


def test_spec_deviation_defaults():
    d = SpecDeviation(
        deviation_id="d-1",
        issue_id="TEST-1",
    )
    assert d.severity == "minor"
    assert d.resolution == "pending"
    assert d.detected_by == "gate"


def test_write_and_load_deviations(tmp_path: Path):
    deviations = [
        SpecDeviation(
            deviation_id="d-1",
            issue_id="TEST-1",
            mission_id="m-1",
            description="Changed file outside scope",
            severity="minor",
        ),
        SpecDeviation(
            deviation_id="d-2",
            issue_id="TEST-1",
            mission_id="m-1",
            description="Missing acceptance criterion",
            severity="major",
        ),
    ]
    write_deviations(tmp_path, deviations)
    loaded = load_deviations(tmp_path)
    assert len(loaded) == 2
    assert loaded[0].deviation_id == "d-1"
    assert loaded[1].severity == "major"


def test_load_deviations_empty(tmp_path: Path):
    assert load_deviations(tmp_path) == []


def test_detect_deviations_no_snapshot(tmp_path: Path):
    result = detect_deviations(workspace=tmp_path, snapshot=None)
    assert result == []


def test_detect_deviations_no_scope(tmp_path: Path):
    snapshot = _make_snapshot(files_to_read=[])
    result = detect_deviations(workspace=tmp_path, snapshot=snapshot)
    assert result == []


def test_retro_cli(tmp_path: Path):
    from spec_orch.services.mission_service import MissionService

    svc = MissionService(repo_root=tmp_path)
    svc.create_mission("Test Feature", mission_id="test-feat")

    runs_dir = tmp_path / ".spec_orch_runs" / "TEST-1"
    runs_dir.mkdir(parents=True)
    (runs_dir / "report.json").write_text(
        json.dumps(
            {
                "issue_id": "TEST-1",
                "title": "Test Issue",
                "state": "gate_evaluated",
                "mergeable": True,
            }
        )
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["retro", "test-feat", "--repo-root", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert "Retrospective" in result.output
    assert "TEST-1" in result.output

    retro_path = tmp_path / "docs/specs/test-feat/retrospective.md"
    assert retro_path.exists()


def test_retro_cli_with_deviations(tmp_path: Path):
    from spec_orch.services.mission_service import MissionService

    svc = MissionService(repo_root=tmp_path)
    svc.create_mission("Test", mission_id="test-dev")

    runs_dir = tmp_path / ".spec_orch_runs" / "TEST-2"
    runs_dir.mkdir(parents=True)
    (runs_dir / "report.json").write_text(
        json.dumps(
            {
                "issue_id": "TEST-2",
                "title": "Deviated",
                "state": "gate_evaluated",
                "mergeable": False,
            }
        )
    )
    write_deviations(
        runs_dir,
        [
            SpecDeviation(
                deviation_id="d-1",
                issue_id="TEST-2",
                description="Out of scope file changed",
                severity="major",
            ),
        ],
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["retro", "test-dev", "--repo-root", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert "major" in result.output
    assert "Total deviations: 1" in result.output
