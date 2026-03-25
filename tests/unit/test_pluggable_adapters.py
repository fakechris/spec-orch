"""Tests for pluggable adapter factory and new builder/reviewer adapters."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from spec_orch.domain.models import (
    BuilderResult,
    ExecutionPlan,
    Issue,
    RoundAction,
    RoundArtifacts,
    RoundDecision,
    RoundSummary,
)
from spec_orch.domain.protocols import (
    BuilderAdapter,
    ReviewAdapter,
    SupervisorAdapter,
    WorkerHandle,
    WorkerHandleFactory,
)
from spec_orch.services.adapter_factory import create_builder, create_reviewer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_issue(prompt: str | None = "Fix the bug") -> Issue:
    return Issue(
        issue_id="TEST-1",
        title="Test issue",
        summary="Test summary",
        builder_prompt=prompt,
    )


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_stub_worker_handle_is_worker_protocol(self, tmp_path: Path):
        class StubWorkerHandle:
            def __init__(self) -> None:
                self._session_id = "worker-1"

            @property
            def session_id(self) -> str:
                return self._session_id

            def send(self, *, prompt: str, workspace: Path, event_logger=None) -> BuilderResult:
                return BuilderResult(
                    succeeded=True,
                    command=["echo", prompt],
                    stdout="ok",
                    stderr="",
                    report_path=workspace / "builder_report.json",
                    adapter="stub",
                    agent="stub",
                )

            def cancel(self, workspace: Path) -> None:
                return None

            def close(self, workspace: Path) -> None:
                return None

        assert isinstance(StubWorkerHandle(), WorkerHandle)

    def test_stub_supervisor_adapter_is_supervisor_protocol(self):
        class StubSupervisorAdapter:
            ADAPTER_NAME = "stub"

            def review_round(
                self,
                *,
                round_artifacts: RoundArtifacts,
                plan: ExecutionPlan,
                round_history: list[RoundSummary],
                context=None,
            ) -> RoundDecision:
                return RoundDecision(action=RoundAction.CONTINUE)

        assert isinstance(StubSupervisorAdapter(), SupervisorAdapter)

    def test_stub_worker_factory_is_factory_protocol(self, tmp_path: Path):
        class StubWorkerHandle:
            def __init__(self, session_id: str) -> None:
                self._session_id = session_id

            @property
            def session_id(self) -> str:
                return self._session_id

            def send(self, *, prompt: str, workspace: Path, event_logger=None) -> BuilderResult:
                return BuilderResult(
                    succeeded=True,
                    command=["echo", prompt],
                    stdout="ok",
                    stderr="",
                    report_path=workspace / "builder_report.json",
                    adapter="stub",
                    agent="stub",
                )

            def cancel(self, workspace: Path) -> None:
                return None

            def close(self, workspace: Path) -> None:
                return None

        class StubWorkerFactory:
            def create(self, *, session_id: str, workspace: Path) -> StubWorkerHandle:
                return StubWorkerHandle(session_id)

            def get(self, session_id: str) -> StubWorkerHandle | None:
                return StubWorkerHandle(session_id)

            def close_all(self, workspace: Path) -> None:
                return None

        assert isinstance(StubWorkerFactory(), WorkerHandleFactory)

    def test_local_review_adapter_is_review_adapter(self):
        from spec_orch.services.review_adapter import LocalReviewAdapter

        adapter = LocalReviewAdapter()
        assert isinstance(adapter, ReviewAdapter)

    def test_codex_is_builder_adapter(self):
        from spec_orch.services.codex_exec_builder_adapter import CodexExecBuilderAdapter

        adapter = CodexExecBuilderAdapter()
        assert isinstance(adapter, BuilderAdapter)

    def test_opencode_is_builder_adapter(self):
        from spec_orch.services.opencode_builder_adapter import OpenCodeBuilderAdapter

        adapter = OpenCodeBuilderAdapter()
        assert isinstance(adapter, BuilderAdapter)

    def test_droid_is_builder_adapter(self):
        from spec_orch.services.droid_builder_adapter import DroidBuilderAdapter

        adapter = DroidBuilderAdapter()
        assert isinstance(adapter, BuilderAdapter)

    def test_claude_code_is_builder_adapter(self):
        from spec_orch.services.claude_code_builder_adapter import ClaudeCodeBuilderAdapter

        adapter = ClaudeCodeBuilderAdapter()
        assert isinstance(adapter, BuilderAdapter)

    def test_llm_review_is_review_adapter(self):
        from spec_orch.services.llm_review_adapter import LLMReviewAdapter

        adapter = LLMReviewAdapter()
        assert isinstance(adapter, ReviewAdapter)


# ---------------------------------------------------------------------------
# Adapter factory
# ---------------------------------------------------------------------------


class TestAdapterFactory:
    def test_default_builder_is_codex(self, tmp_path: Path):
        builder = create_builder(tmp_path)
        assert builder.ADAPTER_NAME == "codex_exec"

    def test_codex_builder_from_toml(self, tmp_path: Path):
        toml = {"builder": {"adapter": "codex_exec", "executable": "/usr/local/bin/codex"}}
        builder = create_builder(tmp_path, toml_override=toml)
        assert builder.ADAPTER_NAME == "codex_exec"

    def test_opencode_builder_from_toml(self, tmp_path: Path):
        toml = {"builder": {"adapter": "opencode", "model": "minimax/MiniMax-M2.5"}}
        builder = create_builder(tmp_path, toml_override=toml)
        assert builder.ADAPTER_NAME == "opencode"
        assert builder.model == "minimax/MiniMax-M2.5"

    def test_droid_builder_from_toml(self, tmp_path: Path):
        toml = {"builder": {"adapter": "droid", "model": "gpt-4o"}}
        builder = create_builder(tmp_path, toml_override=toml)
        assert builder.ADAPTER_NAME == "droid"

    def test_claude_code_builder_from_toml(self, tmp_path: Path):
        toml = {"builder": {"adapter": "claude_code"}}
        builder = create_builder(tmp_path, toml_override=toml)
        assert builder.ADAPTER_NAME == "claude_code"

    def test_unknown_builder_raises(self, tmp_path: Path):
        toml = {"builder": {"adapter": "nonexistent"}}
        with pytest.raises(ValueError, match="Unknown builder adapter"):
            create_builder(tmp_path, toml_override=toml)

    def test_default_reviewer_is_local(self, tmp_path: Path):
        reviewer = create_reviewer(tmp_path)
        assert reviewer.ADAPTER_NAME == "local"

    def test_llm_reviewer_from_toml(self, tmp_path: Path):
        toml = {"reviewer": {"adapter": "llm", "model": "minimax/MiniMax-M2.5"}}
        reviewer = create_reviewer(tmp_path, toml_override=toml)
        assert reviewer.ADAPTER_NAME == "llm"

    def test_unknown_reviewer_raises(self, tmp_path: Path):
        toml = {"reviewer": {"adapter": "nonexistent"}}
        with pytest.raises(ValueError, match="Unknown reviewer adapter"):
            create_reviewer(tmp_path, toml_override=toml)

    def test_factory_reads_toml_file(self, tmp_path: Path):
        toml_content = b'[builder]\nadapter = "opencode"\nmodel = "test/model"\n'
        (tmp_path / "spec-orch.toml").write_bytes(toml_content)
        builder = create_builder(tmp_path)
        assert builder.ADAPTER_NAME == "opencode"

    def test_timeout_from_toml(self, tmp_path: Path):
        toml = {"builder": {"adapter": "opencode", "timeout_seconds": 300}}
        builder = create_builder(tmp_path, toml_override=toml)
        assert builder.absolute_timeout_seconds == 300.0


# ---------------------------------------------------------------------------
# OpenCode Builder Adapter
# ---------------------------------------------------------------------------


class TestOpenCodeBuilderAdapter:
    def test_skip_when_no_prompt(self, tmp_path: Path):
        from spec_orch.services.opencode_builder_adapter import OpenCodeBuilderAdapter

        adapter = OpenCodeBuilderAdapter()
        issue = _make_issue(prompt=None)
        result = adapter.run(issue=issue, workspace=tmp_path)
        assert result.succeeded is True
        assert result.skipped is True
        assert result.adapter == "opencode"

    def test_map_events_step_start(self):
        from spec_orch.services.opencode_builder_adapter import OpenCodeBuilderAdapter

        adapter = OpenCodeBuilderAdapter()
        raw = [{"type": "step_start", "timestamp": "123"}]
        events = adapter.map_events(raw)
        assert len(events) == 1
        assert events[0].kind == "message"

    def test_map_events_tool_use_bash(self):
        from spec_orch.services.opencode_builder_adapter import OpenCodeBuilderAdapter

        adapter = OpenCodeBuilderAdapter()
        raw = [
            {
                "type": "tool_use",
                "timestamp": "123",
                "part": {
                    "tool": "bash",
                    "state": {
                        "status": "completed",
                        "input": {"command": "ls -la"},
                        "metadata": {"exit_code": 0},
                    },
                },
            }
        ]
        events = adapter.map_events(raw)
        assert events[0].kind == "command_end"
        assert events[0].exit_code == 0
        assert "ls -la" in events[0].text

    def test_map_events_tool_use_write(self):
        from spec_orch.services.opencode_builder_adapter import OpenCodeBuilderAdapter

        adapter = OpenCodeBuilderAdapter()
        raw = [
            {
                "type": "tool_use",
                "timestamp": "123",
                "part": {
                    "tool": "write",
                    "state": {
                        "status": "completed",
                        "input": {"filePath": "src/main.py"},
                    },
                },
            }
        ]
        events = adapter.map_events(raw)
        assert events[0].kind == "file_change"
        assert events[0].file_path == "src/main.py"

    def test_map_events_non_completed_tool_use_skipped(self):
        from spec_orch.services.opencode_builder_adapter import OpenCodeBuilderAdapter

        adapter = OpenCodeBuilderAdapter()
        raw = [
            {
                "type": "tool_use",
                "timestamp": "123",
                "part": {
                    "tool": "bash",
                    "state": {"status": "running", "input": {"command": "ls"}},
                },
            }
        ]
        events = adapter.map_events(raw)
        assert len(events) == 0

    def test_map_events_step_finish(self):
        from spec_orch.services.opencode_builder_adapter import OpenCodeBuilderAdapter

        adapter = OpenCodeBuilderAdapter()
        raw = [
            {
                "type": "step_finish",
                "timestamp": "123",
                "part": {
                    "cost": 0.01,
                    "tokens": {"input": 100, "output": 50},
                    "reason": "stop",
                },
            }
        ]
        events = adapter.map_events(raw)
        assert events[0].kind == "turn_end"
        assert events[0].metadata["cost_usd"] == 0.01
        assert events[0].metadata["input_tokens"] == 100

    def test_model_passed_to_command(self, tmp_path: Path):
        from spec_orch.services.opencode_builder_adapter import OpenCodeBuilderAdapter

        adapter = OpenCodeBuilderAdapter(model="minimax/MiniMax-M2.5")
        issue = _make_issue(prompt=None)
        result = adapter.run(issue=issue, workspace=tmp_path)
        assert result.skipped is True

    def test_collect_artifacts(self, tmp_path: Path):
        from spec_orch.services.opencode_builder_adapter import OpenCodeBuilderAdapter

        adapter = OpenCodeBuilderAdapter()
        (tmp_path / "builder_report.json").write_text("{}")
        (tmp_path / "telemetry").mkdir()
        (tmp_path / "telemetry" / "incoming_events.jsonl").write_text("")
        artifacts = adapter.collect_artifacts(tmp_path)
        assert len(artifacts) == 2


# ---------------------------------------------------------------------------
# Droid Builder Adapter
# ---------------------------------------------------------------------------


class TestDroidBuilderAdapter:
    def test_skip_when_no_prompt(self, tmp_path: Path):
        from spec_orch.services.droid_builder_adapter import DroidBuilderAdapter

        adapter = DroidBuilderAdapter()
        issue = _make_issue(prompt=None)
        result = adapter.run(issue=issue, workspace=tmp_path)
        assert result.succeeded is True
        assert result.skipped is True
        assert result.adapter == "droid"

    def test_map_events_message(self):
        from spec_orch.services.droid_builder_adapter import DroidBuilderAdapter

        adapter = DroidBuilderAdapter()
        raw = [{"type": "message", "content": "Hello", "timestamp": "123"}]
        events = adapter.map_events(raw)
        assert events[0].kind == "message"
        assert events[0].text == "Hello"

    def test_map_events_tool_call(self):
        from spec_orch.services.droid_builder_adapter import DroidBuilderAdapter

        adapter = DroidBuilderAdapter()
        raw = [
            {
                "type": "tool_call",
                "name": "bash",
                "input": "echo hi",
                "exit_code": 0,
                "timestamp": "123",
            }
        ]
        events = adapter.map_events(raw)
        assert events[0].kind == "command_end"

    def test_map_events_result(self):
        from spec_orch.services.droid_builder_adapter import DroidBuilderAdapter

        adapter = DroidBuilderAdapter()
        raw = [
            {
                "type": "result",
                "subtype": "success",
                "total_cost_usd": 0.05,
                "timestamp": "123",
            }
        ]
        events = adapter.map_events(raw)
        assert events[0].kind == "turn_end"


# ---------------------------------------------------------------------------
# Claude Code Builder Adapter
# ---------------------------------------------------------------------------


class TestClaudeCodeBuilderAdapter:
    def test_skip_when_no_prompt(self, tmp_path: Path):
        from spec_orch.services.claude_code_builder_adapter import ClaudeCodeBuilderAdapter

        adapter = ClaudeCodeBuilderAdapter()
        issue = _make_issue(prompt=None)
        result = adapter.run(issue=issue, workspace=tmp_path)
        assert result.succeeded is True
        assert result.skipped is True
        assert result.adapter == "claude_code"

    def test_map_events_assistant_text(self):
        from spec_orch.services.claude_code_builder_adapter import ClaudeCodeBuilderAdapter

        adapter = ClaudeCodeBuilderAdapter()
        raw = [
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "Working on it"}]},
                "timestamp": "123",
            }
        ]
        events = adapter.map_events(raw)
        assert events[0].kind == "message"
        assert events[0].text == "Working on it"

    def test_map_events_assistant_tool_use(self):
        from spec_orch.services.claude_code_builder_adapter import ClaudeCodeBuilderAdapter

        adapter = ClaudeCodeBuilderAdapter()
        raw = [
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Bash",
                            "input": {"command": "npm test"},
                        }
                    ]
                },
                "timestamp": "123",
            }
        ]
        events = adapter.map_events(raw)
        assert events[0].kind == "command_end"
        assert "npm test" in events[0].text

    def test_map_events_result(self):
        from spec_orch.services.claude_code_builder_adapter import ClaudeCodeBuilderAdapter

        adapter = ClaudeCodeBuilderAdapter()
        raw = [
            {
                "type": "result",
                "subtype": "success",
                "total_cost_usd": 0.02,
                "session_id": "abc123",
                "timestamp": "123",
            }
        ]
        events = adapter.map_events(raw)
        assert events[0].kind == "turn_end"
        assert events[0].metadata["session_id"] == "abc123"


# ---------------------------------------------------------------------------
# LLM Review Adapter
# ---------------------------------------------------------------------------


class TestLLMReviewAdapter:
    def test_initialize_empty_diff(self, tmp_path: Path):
        from spec_orch.services.llm_review_adapter import LLMReviewAdapter

        adapter = LLMReviewAdapter()
        summary = adapter.initialize(issue_id="TEST-1", workspace=tmp_path)
        assert summary.verdict == "pass"
        assert summary.reviewed_by == "llm-reviewer"

    def test_review_manual_override(self, tmp_path: Path):
        from spec_orch.services.llm_review_adapter import LLMReviewAdapter

        adapter = LLMReviewAdapter()
        summary = adapter.review(
            issue_id="TEST-1",
            workspace=tmp_path,
            verdict="changes_requested",
            reviewed_by="human",
        )
        assert summary.verdict == "changes_requested"
        assert summary.reviewed_by == "human"

    @patch("spec_orch.services.llm_review_adapter.LLMReviewAdapter._get_diff")
    @patch("spec_orch.services.llm_review_adapter.LLMReviewAdapter._call_llm")
    def test_initialize_calls_llm(self, mock_llm, mock_diff, tmp_path: Path):
        from spec_orch.services.llm_review_adapter import LLMReviewAdapter

        mock_diff.return_value = "diff --git a/foo.py b/foo.py\n+hello"
        mock_llm.return_value = {
            "verdict": "pass",
            "summary": "Looks good",
            "issues": [],
        }

        adapter = LLMReviewAdapter()
        summary = adapter.initialize(issue_id="TEST-1", workspace=tmp_path)
        assert summary.verdict == "pass"
        mock_llm.assert_called_once()
        report = json.loads((tmp_path / "review_report.json").read_text())
        assert report["llm_review"]["summary"] == "Looks good"

    @patch("spec_orch.services.llm_review_adapter.LLMReviewAdapter._get_diff")
    @patch("spec_orch.services.llm_review_adapter.LLMReviewAdapter._call_llm")
    def test_initialize_prefers_context_bundle_when_available(
        self, mock_llm, mock_diff, tmp_path: Path
    ):
        from spec_orch.domain.context import (
            ContextBundle,
            ExecutionContext,
            LearningContext,
            TaskContext,
        )
        from spec_orch.services.llm_review_adapter import LLMReviewAdapter

        mock_diff.return_value = "diff --git a/foo.py b/foo.py\n+hello"
        mock_llm.return_value = {"verdict": "pass", "summary": "ok", "issues": []}

        adapter = LLMReviewAdapter()
        fake_ctx = ContextBundle(
            task=TaskContext(
                issue=_make_issue(), acceptance_criteria=["AC-1"], constraints=["C-1"]
            ),
            execution=ExecutionContext(),
            learning=LearningContext(),
        )
        with patch.object(adapter, "_build_context_bundle", return_value=fake_ctx):
            adapter.initialize(issue_id="TEST-1", workspace=tmp_path)

        _, kwargs = mock_llm.call_args
        assert "Acceptance Criteria" in kwargs["extra_context"]
        assert "Constraints" in kwargs["extra_context"]

    @patch("spec_orch.services.llm_review_adapter.LLMReviewAdapter._get_diff")
    @patch("spec_orch.services.llm_review_adapter.LLMReviewAdapter._call_llm")
    def test_invalid_verdict_falls_back_to_uncertain(self, mock_llm, mock_diff, tmp_path: Path):
        from spec_orch.services.llm_review_adapter import LLMReviewAdapter

        mock_diff.return_value = "some diff"
        mock_llm.return_value = {"verdict": "invalid", "summary": "", "issues": []}

        adapter = LLMReviewAdapter()
        summary = adapter.initialize(issue_id="TEST-1", workspace=tmp_path)
        assert summary.verdict == "uncertain"

    def test_issue_from_workspace_falls_back_to_legacy_intent(self, tmp_path: Path):
        from spec_orch.services.llm_review_adapter import LLMReviewAdapter

        (tmp_path / "spec_snapshot.json").write_text(
            json.dumps({"issue": {"intent": "Legacy intent summary"}})
        )

        issue = LLMReviewAdapter._issue_from_workspace(issue_id="TEST-1", workspace=tmp_path)
        assert issue.summary == "Legacy intent summary"

    def test_issue_from_workspace_handles_null_issue_block(self, tmp_path: Path):
        from spec_orch.services.llm_review_adapter import LLMReviewAdapter

        (tmp_path / "spec_snapshot.json").write_text(json.dumps({"issue": None}))
        issue = LLMReviewAdapter._issue_from_workspace(issue_id="TEST-2", workspace=tmp_path)
        assert issue.issue_id == "TEST-2"
        assert issue.summary == ""


# ---------------------------------------------------------------------------
# RunController injection
# ---------------------------------------------------------------------------


class TestRunControllerInjection:
    def test_default_review_adapter(self, tmp_path: Path):
        from spec_orch.services.run_controller import RunController

        rc = RunController(repo_root=tmp_path)
        assert rc.review_adapter.ADAPTER_NAME == "local"

    def test_custom_review_adapter(self, tmp_path: Path):
        from spec_orch.services.llm_review_adapter import LLMReviewAdapter
        from spec_orch.services.run_controller import RunController

        reviewer = LLMReviewAdapter()
        rc = RunController(repo_root=tmp_path, review_adapter=reviewer)
        assert rc.review_adapter.ADAPTER_NAME == "llm"


# ---------------------------------------------------------------------------
# End-to-end: toml config -> controller with correct adapters
# ---------------------------------------------------------------------------


class TestEndToEndConfig:
    def test_opencode_config_creates_correct_controller(self, tmp_path: Path):
        from spec_orch.services.run_controller import RunController

        toml_content = (
            b'[builder]\nadapter = "opencode"\n'
            b'executable = "opencode"\n'
            b'model = "minimax/MiniMax-M2.5"\n'
            b"timeout_seconds = 300\n\n"
            b'[reviewer]\nadapter = "local"\n'
        )
        (tmp_path / "spec-orch.toml").write_bytes(toml_content)

        builder = create_builder(tmp_path)
        reviewer = create_reviewer(tmp_path)

        assert builder.ADAPTER_NAME == "opencode"
        assert builder.model == "minimax/MiniMax-M2.5"
        assert builder.absolute_timeout_seconds == 300.0
        assert reviewer.ADAPTER_NAME == "local"

        rc = RunController(
            repo_root=tmp_path,
            builder_adapter=builder,
            review_adapter=reviewer,
        )
        assert rc.builder_adapter.ADAPTER_NAME == "opencode"
        assert rc.review_adapter.ADAPTER_NAME == "local"

    def test_droid_with_llm_reviewer(self, tmp_path: Path):
        toml_content = (
            b'[builder]\nadapter = "droid"\nmodel = "gpt-4o"\n\n'
            b'[reviewer]\nadapter = "llm"\nmodel = "minimax/MiniMax-M2.5"\n'
        )
        (tmp_path / "spec-orch.toml").write_bytes(toml_content)

        builder = create_builder(tmp_path)
        reviewer = create_reviewer(tmp_path)

        assert builder.ADAPTER_NAME == "droid"
        assert reviewer.ADAPTER_NAME == "llm"

    def test_claude_code_config(self, tmp_path: Path):
        toml_content = b'[builder]\nadapter = "claude_code"\n'
        (tmp_path / "spec-orch.toml").write_bytes(toml_content)

        builder = create_builder(tmp_path)
        assert builder.ADAPTER_NAME == "claude_code"

    def test_backward_compatible_codex_executable(self, tmp_path: Path):
        """Old config key codex_executable still works."""
        toml_content = b'[builder]\nadapter = "codex_exec"\ncodex_executable = "/usr/bin/codex"\n'
        (tmp_path / "spec-orch.toml").write_bytes(toml_content)

        builder = create_builder(tmp_path)
        assert builder.ADAPTER_NAME == "codex_exec"
        assert builder.executable == "/usr/bin/codex"

    def test_skip_run_for_all_adapters(self, tmp_path: Path):
        """All adapters handle skip (no prompt) consistently."""
        from spec_orch.services.claude_code_builder_adapter import (
            ClaudeCodeBuilderAdapter,
        )
        from spec_orch.services.droid_builder_adapter import DroidBuilderAdapter
        from spec_orch.services.opencode_builder_adapter import OpenCodeBuilderAdapter

        issue = _make_issue(prompt=None)
        for adapter_cls in (OpenCodeBuilderAdapter, DroidBuilderAdapter, ClaudeCodeBuilderAdapter):
            adapter = adapter_cls()
            result = adapter.run(issue=issue, workspace=tmp_path)
            assert result.succeeded is True
            assert result.skipped is True
            assert (tmp_path / "builder_report.json").exists()
            report = json.loads((tmp_path / "builder_report.json").read_text())
            assert report["adapter"] == adapter.ADAPTER_NAME
