"""Tests for Memory vNext Phase 2: ProjectProfile + Learning Views (SON-231)."""

from pathlib import Path

import pytest

from spec_orch.domain.context import LearningContext, ProjectProfile
from spec_orch.services.memory.fs_provider import FileSystemMemoryProvider
from spec_orch.services.memory.service import MemoryService
from spec_orch.services.memory.types import MemoryEntry, MemoryLayer


@pytest.fixture()
def svc(tmp_path: Path) -> MemoryService:
    p = FileSystemMemoryProvider(tmp_path / "memory")
    return MemoryService(provider=p)


class TestProjectProfileDataclass:
    def test_defaults(self):
        p = ProjectProfile()
        assert p.tech_stack == []
        assert p.common_failures == []
        assert p.recent_success_rate is None
        assert p.recent_period_days == 7

    def test_assignment(self):
        p = ProjectProfile(
            tech_stack=["python"],
            common_failures=["lint"],
            recent_success_rate=0.85,
        )
        assert p.tech_stack == ["python"]
        assert p.recent_success_rate == 0.85


class TestLearningContextNewFields:
    def test_new_fields_exist(self):
        ctx = LearningContext()
        assert ctx.project_profile is None
        assert ctx.failure_patterns == []
        assert ctx.success_recipes == []
        assert ctx.active_run_signals is None


class TestFailurePatterns:
    def test_returns_failed_entries(self, svc: MemoryService):
        svc.record_issue_completion("I1", succeeded=False, summary="lint fail")
        svc.record_issue_completion("I2", succeeded=True, summary="ok")
        svc.record_issue_completion("I3", succeeded=False, summary="test fail")

        patterns = svc.get_failure_patterns()
        assert len(patterns) == 2
        assert all("issue_id" in p for p in patterns)

    def test_excludes_superseded(self, svc: MemoryService):
        svc.store(
            MemoryEntry(
                key="issue-result-old",
                content="old fail",
                layer=MemoryLayer.EPISODIC,
                tags=["issue-result"],
                metadata={
                    "succeeded": False,
                    "entity_scope": "issue",
                    "entity_id": "X",
                    "relation_type": "superseded",
                },
            )
        )
        svc.record_issue_completion("X2", succeeded=False, summary="real fail")
        patterns = svc.get_failure_patterns()
        assert len(patterns) == 1
        assert patterns[0]["issue_id"] == "X2"

    def test_filter_by_entity_id(self, svc: MemoryService):
        svc.record_issue_completion("A", succeeded=False, summary="fail A")
        svc.record_issue_completion("B", succeeded=False, summary="fail B")
        patterns = svc.get_failure_patterns(entity_id="A")
        assert len(patterns) == 1


class TestSuccessRecipes:
    def test_returns_successful_entries(self, svc: MemoryService):
        svc.consolidate_run(run_id="r1", issue_id="I1", succeeded=True)
        svc.consolidate_run(run_id="r2", issue_id="I2", succeeded=False)
        svc.consolidate_run(run_id="r3", issue_id="I3", succeeded=True, builder_adapter="cc")

        recipes = svc.get_success_recipes()
        assert len(recipes) == 2
        assert all(r.get("key", "").startswith("run-summary-") for r in recipes)

    def test_filter_by_entity_id(self, svc: MemoryService):
        svc.consolidate_run(run_id="r1", issue_id="I1", succeeded=True)
        svc.consolidate_run(run_id="r2", issue_id="I2", succeeded=True)
        recipes = svc.get_success_recipes(entity_id="I1")
        assert len(recipes) == 1


class TestProjectProfile:
    def test_empty_memory_returns_defaults(self, svc: MemoryService):
        profile = svc.get_project_profile()
        assert isinstance(profile, dict)
        assert profile.get("recent_success_rate") == 0.0
        assert "common_failures" in profile

    def test_incorporates_trend(self, svc: MemoryService):
        svc.consolidate_run(run_id="r1", issue_id="I1", succeeded=True)
        svc.consolidate_run(run_id="r2", issue_id="I2", succeeded=True)
        svc.consolidate_run(run_id="r3", issue_id="I3", succeeded=False)
        profile = svc.get_project_profile()
        rate = profile["recent_success_rate"]
        assert 0.5 <= rate <= 1.0

    def test_includes_common_failures(self, svc: MemoryService):
        svc.record_issue_completion(
            "I1",
            succeeded=False,
            summary="lint fail",
            metadata={"failed_conditions": ["lint-check"]},
        )
        profile = svc.get_project_profile()
        assert "lint-check" in profile["common_failures"]


class TestActiveRunSignals:
    def test_returns_recent_activity(self, svc: MemoryService):
        svc.consolidate_run(run_id="r1", issue_id="I1", succeeded=True)
        svc.consolidate_run(run_id="r2", issue_id="I2", succeeded=False)

        signals = svc.get_active_run_signals()
        assert signals["total_runs"] == 2
        assert signals["succeeded"] == 1
        assert "I1" in signals["recent_issues"]
        assert "I2" in signals["recent_failure_issues"]
