"""Tests for MissionLifecycleManager."""

from __future__ import annotations

from pathlib import Path

import pytest

from spec_orch.services.event_bus import EventBus, EventTopic
from spec_orch.services.lifecycle_manager import (
    MissionLifecycleManager,
    MissionPhase,
    MissionState,
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / ".spec_orch_runs").mkdir()
    (tmp_path / "docs" / "specs").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def mgr(repo: Path, bus: EventBus) -> MissionLifecycleManager:
    return MissionLifecycleManager(repo_root=repo, event_bus=bus)


class TestMissionState:
    def test_roundtrip(self):
        state = MissionState(
            mission_id="test",
            phase=MissionPhase.EXECUTING,
            issue_ids=["A", "B"],
            completed_issues=["A"],
        )
        d = state.to_dict()
        restored = MissionState.from_dict(d)
        assert restored.phase == MissionPhase.EXECUTING
        assert restored.issue_ids == ["A", "B"]
        assert restored.completed_issues == ["A"]


class TestLifecycleManager:
    def test_begin_tracking(self, mgr: MissionLifecycleManager, bus: EventBus):
        events: list = []
        bus.subscribe(lambda e: events.append(e), EventTopic.MISSION_STATE)

        state = mgr.begin_tracking("m1")
        assert state.phase == MissionPhase.APPROVED
        assert len(events) == 1
        assert events[0].payload["new_state"] == "approved"

    def test_planning_flow(self, mgr: MissionLifecycleManager):
        mgr.begin_tracking("m1")
        mgr.start_planning("m1")
        s = mgr.get_state("m1")
        assert s is not None
        assert s.phase == MissionPhase.PLANNING

        mgr.plan_complete("m1", ["SON-1", "SON-2"])
        s = mgr.get_state("m1")
        assert s is not None
        assert s.phase == MissionPhase.PLANNED
        assert s.issue_ids == ["SON-1", "SON-2"]

    def test_execution_and_issue_done(self, mgr: MissionLifecycleManager):
        mgr.begin_tracking("m1")
        mgr.promotion_complete("m1", ["SON-1", "SON-2"])
        s = mgr.get_state("m1")
        assert s is not None
        assert s.phase == MissionPhase.EXECUTING

        mgr.mark_issue_done("m1", "SON-1")
        s = mgr.get_state("m1")
        assert s is not None
        assert s.phase == MissionPhase.EXECUTING

        mgr.mark_issue_done("m1", "SON-2")
        s = mgr.get_state("m1")
        assert s is not None
        assert s.phase == MissionPhase.ALL_DONE

    def test_mark_issue_done_idempotent(self, mgr: MissionLifecycleManager):
        mgr.begin_tracking("m1")
        mgr.promotion_complete("m1", ["SON-1"])
        mgr.mark_issue_done("m1", "SON-1")
        mgr.mark_issue_done("m1", "SON-1")
        s = mgr.get_state("m1")
        assert s is not None
        assert len(s.completed_issues) == 1

    def test_mark_failed(self, mgr: MissionLifecycleManager):
        mgr.begin_tracking("m1")
        mgr.mark_failed("m1", "test error")
        s = mgr.get_state("m1")
        assert s is not None
        assert s.phase == MissionPhase.FAILED
        assert s.error == "test error"

    def test_full_lifecycle(self, mgr: MissionLifecycleManager):
        mgr.begin_tracking("m1")
        mgr.start_planning("m1")
        mgr.plan_complete("m1", ["SON-1"])
        mgr.start_promoting("m1")
        mgr.promotion_complete("m1", ["SON-1"])
        mgr.mark_issue_done("m1", "SON-1")
        mgr.start_retrospective("m1")
        mgr.start_evolution("m1")
        mgr.mark_completed("m1")

        s = mgr.get_state("m1")
        assert s is not None
        assert s.phase == MissionPhase.COMPLETED

    def test_state_persistence(self, repo: Path, bus: EventBus):
        mgr1 = MissionLifecycleManager(repo_root=repo, event_bus=bus)
        mgr1.begin_tracking("m1")
        mgr1.start_planning("m1")

        mgr2 = MissionLifecycleManager(repo_root=repo, event_bus=bus)
        s = mgr2.get_state("m1")
        assert s is not None
        assert s.phase == MissionPhase.PLANNING

    def test_all_states(self, mgr: MissionLifecycleManager):
        mgr.begin_tracking("m1")
        mgr.begin_tracking("m2")
        states = mgr.all_states()
        assert len(states) == 2
        assert "m1" in states
        assert "m2" in states

    def test_btw_injection(self, mgr: MissionLifecycleManager, repo: Path):
        mgr.begin_tracking("m1")
        mgr.promotion_complete("m1", ["SON-1", "SON-2"])

        result = mgr.inject_btw("SON-1", "handle binary frames", "tui")
        assert result is True

        btw_path = repo / ".spec_orch_runs" / "SON-1" / "btw_context.md"
        assert btw_path.exists()
        content = btw_path.read_text()
        assert "handle binary frames" in content

    def test_btw_injection_unknown_issue(self, mgr: MissionLifecycleManager):
        result = mgr.inject_btw("UNKNOWN", "msg", "tui")
        assert result is False

    def test_btw_not_injected_for_completed_issue(self, mgr: MissionLifecycleManager):
        mgr.begin_tracking("m1")
        mgr.promotion_complete("m1", ["SON-1"])
        mgr.mark_issue_done("m1", "SON-1")

        result = mgr.inject_btw("SON-1", "msg", "tui")
        assert result is False


class TestAutoAdvance:
    def test_auto_advance_no_state(self, mgr: MissionLifecycleManager):
        result = mgr.auto_advance("nonexistent")
        assert result is None

    def test_auto_advance_plan_failure(self, mgr: MissionLifecycleManager, repo: Path):
        mgr.begin_tracking("m1")
        state = mgr.auto_advance("m1")
        assert state is not None
        assert state.phase == MissionPhase.FAILED
        assert "Planning failed" in (state.error or "")
