"""Tests for integration gaps: ContextRanker→Assembler, RunProgress→Controller, TraceSampler→_finalize."""

from __future__ import annotations

from pathlib import Path

from spec_orch.domain.context import CompactRetentionPriority, NodeContextSpec
from spec_orch.domain.models import Issue
from spec_orch.services.context_assembler import ContextAssembler, _detect_chars_per_token
from spec_orch.services.context_ranker import _detect_chars_per_token as cr_detect
from spec_orch.services.event_bus import Event, EventBus, EventTopic
from spec_orch.services.run_progress import RunProgressSnapshot
from spec_orch.services.trace_sampler import TraceSampler

# --------------------------------------------------------------------------
# CJK-aware token estimation
# --------------------------------------------------------------------------


class TestCJKDetection:
    def test_english_text_uses_default(self) -> None:
        assert _detect_chars_per_token("hello world") == 4

    def test_chinese_text_uses_cjk_factor(self) -> None:
        text = "这是一段中文文本测试" * 30
        assert _detect_chars_per_token(text) == 2

    def test_mixed_text_below_threshold(self) -> None:
        text = "hello " * 100 + "中文" * 10
        assert _detect_chars_per_token(text) == 4

    def test_empty_text(self) -> None:
        assert _detect_chars_per_token("") == 4

    def test_context_ranker_uses_same_logic(self) -> None:
        assert cr_detect("这是中文" * 50) == 2


class TestTruncateEdgeCases:
    def test_truncate_tiny_budget_no_negative_slice(self) -> None:
        from spec_orch.services.context_assembler import _truncate

        text = "A" * 10000
        result = _truncate(text, max_tokens=1)
        assert len(result) < 100

    def test_truncate_zero_budget(self) -> None:
        from spec_orch.services.context_assembler import _truncate

        result = _truncate("hello world", max_tokens=0)
        assert result == ""

    def test_truncate_normal(self) -> None:
        from spec_orch.services.context_assembler import _truncate

        text = "X" * 500
        result = _truncate(text, max_tokens=50)
        assert "[truncated]" in result
        assert len(result) <= 50 * 4 + 5


# --------------------------------------------------------------------------
# ContextRanker integration with ContextAssembler
# --------------------------------------------------------------------------


class TestContextRankerIntegration:
    def _make_issue(self) -> Issue:
        return Issue(
            issue_id="test-1",
            title="Test issue",
            summary="A test",
            labels=[],
        )

    def test_assembler_uses_ranked_allocation(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        (workspace / "task.spec.md").write_text("A" * 500)

        spec = NodeContextSpec(
            node_name="test",
            required_task_fields=["spec_snapshot_text"],
            required_execution_fields=[],
            required_learning_fields=[],
            max_tokens_budget=200,
        )

        asm = ContextAssembler()
        bundle = asm.assemble(spec, self._make_issue(), workspace)
        assert bundle.task.spec_snapshot_text

    def test_ranked_sections_built_correctly(self) -> None:
        from spec_orch.domain.context import ExecutionContext, TaskContext

        task = TaskContext(
            issue=self._make_issue(),
            spec_snapshot_text="spec text",
            architecture_notes="arch notes",
        )
        exec_ctx = ExecutionContext(
            file_tree="file list",
            git_diff="diff output",
            builder_events_summary="events",
        )
        contexts = {"task": task, "execution": exec_ctx}

        sections = ContextAssembler._collect_ranked_sections(contexts)
        names = {s.name for s in sections}
        assert names == {
            "spec_snapshot_text",
            "architecture_notes",
            "file_tree",
            "git_diff",
            "builder_events_summary",
        }

        priorities = {s.name: s.priority for s in sections}
        assert priorities["spec_snapshot_text"] == CompactRetentionPriority.ARCHITECTURE_DECISIONS
        assert priorities["file_tree"] == CompactRetentionPriority.MODIFIED_FILES
        assert priorities["builder_events_summary"] == CompactRetentionPriority.TOOL_OUTPUT


# --------------------------------------------------------------------------
# RunProgressSnapshot integration
# --------------------------------------------------------------------------


class TestRunProgressIntegration:
    def test_snapshot_records_pipeline_stages(self, tmp_path: Path) -> None:
        snap = RunProgressSnapshot.create(run_id="r1", issue_id="i1")
        snap.mark_stage_start("builder")
        snap.mark_stage_complete("builder", success=True)
        snap.mark_stage_start("verification")
        snap.mark_stage_complete("verification", success=True, detail="5/5")
        snap.mark_stage_start("review")
        snap.mark_stage_complete("review", success=True)
        snap.mark_stage_start("gate")
        snap.mark_stage_complete("gate", success=True)

        snap.save(tmp_path)

        loaded = RunProgressSnapshot.load(tmp_path)
        assert loaded is not None
        assert loaded.completed_stage_names() == {"builder", "verification", "review", "gate"}

    def test_snapshot_records_failure(self) -> None:
        snap = RunProgressSnapshot.create(run_id="r2", issue_id="i2")
        snap.mark_stage_complete("builder", success=False)
        assert not snap.is_stage_completed("builder")
        completed = {s.stage for s in snap.stages if s.success}
        assert "builder" not in completed


# --------------------------------------------------------------------------
# TraceSampler integration
# --------------------------------------------------------------------------


class TestTraceSamplerIntegration:
    def test_failed_gate_triggers_sample(self) -> None:
        sampler = TraceSampler()
        should, reason = sampler.should_sample(
            run_id="r1",
            has_negative_feedback=True,
        )
        assert should
        assert reason == "negative_feedback"

    def test_normal_run_may_not_sample(self) -> None:
        sampler = TraceSampler(rules=[])
        should, _ = sampler.should_sample(run_id="r1")
        assert not should


# --------------------------------------------------------------------------
# Fallback observability (EventBus)
# --------------------------------------------------------------------------


class TestFallbackObservability:
    def test_emit_fallback_publishes_event(self) -> None:
        bus = EventBus()
        events: list[Event] = []
        bus.subscribe(events.append, EventTopic.FALLBACK)

        bus.emit_fallback(
            component="TestComponent",
            primary="llm",
            fallback="rules",
            reason="LLM unavailable",
            issue_id="i1",
        )

        assert len(events) == 1
        assert events[0].payload["component"] == "TestComponent"
        assert events[0].payload["primary"] == "llm"
        assert events[0].payload["fallback"] == "rules"
        assert events[0].payload["reason"] == "LLM unavailable"

    def test_fallback_event_in_history(self) -> None:
        bus = EventBus()
        bus.emit_fallback(
            component="Router",
            primary="hybrid",
            fallback="static",
            reason="test",
        )

        history = bus.query_history(topic=EventTopic.FALLBACK)
        assert len(history) == 1
        assert history[0].payload["component"] == "Router"


# --------------------------------------------------------------------------
# pathlib-based file tree (cross-platform)
# --------------------------------------------------------------------------


class TestPathLibFileTree:
    def test_read_file_tree_uses_pathlib(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("pass")
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/main")
        (tmp_path / "README.md").write_text("hello")

        result = ContextAssembler._read_file_tree(tmp_path)
        assert "src/main.py" in result or "src\\main.py" in result
        assert "README.md" in result
        assert "HEAD" not in result

    def test_file_tree_respects_max_entries(self, tmp_path: Path) -> None:
        for i in range(10):
            (tmp_path / f"file_{i}.txt").write_text(f"{i}")

        result = ContextAssembler._read_file_tree(tmp_path, max_entries=5)
        assert "truncated" in result
