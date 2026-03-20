"""Tests for Epics E, F, G."""

from __future__ import annotations

from pathlib import Path

from spec_orch.domain.context import CompactRetentionPriority, NodeContextSpec
from spec_orch.services.context_assembler import ContextAssembler
from spec_orch.services.skill_degradation import (
    RoutingDecision,
    SkillBaseline,
    SkillDegradationDetector,
)


class TestCompactRetentionPriority:
    def test_priority_order(self) -> None:
        assert (
            CompactRetentionPriority.ARCHITECTURE_DECISIONS < CompactRetentionPriority.TOOL_OUTPUT
        )

    def test_retention_instructions_nonempty(self) -> None:
        instructions = CompactRetentionPriority.retention_instructions()
        assert "Architecture decisions" in instructions
        assert "identifiers" in instructions.lower()


class TestNodeContextSpecExcludeFramework:
    def test_default_exclude_framework(self) -> None:
        spec = NodeContextSpec(node_name="test")
        assert spec.exclude_framework_events is True

    def test_disable_exclude_framework(self) -> None:
        spec = NodeContextSpec(node_name="test", exclude_framework_events=False)
        assert spec.exclude_framework_events is False


class TestFilterFrameworkEvents:
    def test_filters_system_events(self) -> None:
        events = (
            '{"topic": "system", "payload": {}}\n'
            '{"topic": "issue.state", "payload": {"issue_id": "1"}}\n'
            '{"topic": "tool.start", "payload": {"tool_name": "git"}}\n'
            '{"topic": "builder.output", "payload": {"line": "ok"}}\n'
        )
        filtered = ContextAssembler._filter_framework_events(events)
        lines = [ln for ln in filtered.strip().split("\n") if ln.strip()]
        assert len(lines) == 2
        assert "issue.state" in lines[0]
        assert "builder.output" in lines[1]

    def test_preserves_non_json_lines(self) -> None:
        events = 'plain text\n{"topic": "system"}\n'
        filtered = ContextAssembler._filter_framework_events(events)
        assert "plain text" in filtered


class TestSkillDegradation:
    def test_save_and_load_baselines(self, tmp_path: Path) -> None:
        detector = SkillDegradationDetector(repo_root=tmp_path)
        baseline = SkillBaseline(
            skill_name="planner",
            success_rate=0.85,
            sample_count=20,
            model_version="claude-3.5",
            measured_at="2026-03-18",
        )
        detector.record_baseline(baseline)
        assert detector._baselines_path().exists()

        detector2 = SkillDegradationDetector(repo_root=tmp_path)
        assert "planner" in detector2.get_baselines()
        assert detector2.get_baselines()["planner"].success_rate == 0.85

    def test_detect_degradation(self, tmp_path: Path) -> None:
        detector = SkillDegradationDetector(repo_root=tmp_path)
        detector.record_baseline(SkillBaseline("planner", 0.90, 30, "v1", "2026-03-01"))
        is_degraded, reason = detector.check_degradation("planner", 0.70, 10)
        assert is_degraded
        assert "dropped" in reason

    def test_no_degradation_when_within_range(self, tmp_path: Path) -> None:
        detector = SkillDegradationDetector(repo_root=tmp_path)
        detector.record_baseline(SkillBaseline("planner", 0.90, 30, "v1", "2026-03-01"))
        is_degraded, _ = detector.check_degradation("planner", 0.80, 10)
        assert not is_degraded

    def test_routing_audit_log(self, tmp_path: Path) -> None:
        detector = SkillDegradationDetector(repo_root=tmp_path)
        decision = RoutingDecision(
            timestamp=1710000000.0,
            skill_name="builder",
            selected=True,
            reason="highest confidence",
        )
        detector.log_routing_decision(decision)
        decisions = detector.recent_routing_decisions()
        assert len(decisions) == 1
        assert decisions[0].skill_name == "builder"
