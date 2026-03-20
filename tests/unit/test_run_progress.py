"""Tests for RunProgressSnapshot (R2)."""

from __future__ import annotations

import time
from pathlib import Path

from spec_orch.services.run_progress import RunProgressSnapshot


def test_create_and_mark_stages() -> None:
    snap = RunProgressSnapshot.create("run-1", "ISSUE-1")
    assert snap.run_id == "run-1"
    assert snap.issue_id == "ISSUE-1"
    assert not snap.stages

    snap.mark_stage_start("spec_drafting")
    assert snap.current_stage == "spec_drafting"

    snap.mark_stage_complete("spec_drafting")
    assert snap.is_stage_completed("spec_drafting")
    assert not snap.is_stage_completed("building")


def test_completed_stage_names() -> None:
    snap = RunProgressSnapshot.create("run-2", "ISSUE-2")
    snap.mark_stage_complete("plan", success=True)
    snap.mark_stage_complete("scope", success=True)
    snap.mark_stage_complete("build", success=False, detail="timeout")
    assert snap.completed_stage_names() == {"plan", "scope"}


def test_save_and_load(tmp_path: Path) -> None:
    snap = RunProgressSnapshot.create("run-3", "ISSUE-3")
    snap.mark_stage_complete("plan")
    snap.mark_stage_complete("scope")
    snap.mark_stage_start("build")
    snap.save(tmp_path)

    loaded = RunProgressSnapshot.load(tmp_path)
    assert loaded is not None
    assert loaded.run_id == "run-3"
    assert loaded.issue_id == "ISSUE-3"
    assert len(loaded.stages) == 2
    assert loaded.current_stage == "build"
    assert loaded.is_stage_completed("plan")


def test_load_missing_file(tmp_path: Path) -> None:
    assert RunProgressSnapshot.load(tmp_path) is None


def test_load_corrupt_file(tmp_path: Path) -> None:
    (tmp_path / "progress.json").write_text("not json")
    assert RunProgressSnapshot.load(tmp_path) is None


def test_is_stalled() -> None:
    snap = RunProgressSnapshot.create("run-4", "ISSUE-4")
    snap.mark_stage_start("build")
    snap.last_updated = time.time() - 7200
    assert snap.is_stalled(timeout_seconds=3600)
    assert not snap.is_stalled(timeout_seconds=10000)


def test_not_stalled_when_no_stage() -> None:
    snap = RunProgressSnapshot.create("run-5", "ISSUE-5")
    snap.last_updated = time.time() - 7200
    assert not snap.is_stalled()
