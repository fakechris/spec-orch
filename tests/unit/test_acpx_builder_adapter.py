"""Tests for the AcpxBuilderAdapter."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from spec_orch.domain.models import Issue
from spec_orch.services.acpx_builder_adapter import AcpxBuilderAdapter


def _make_issue(issue_id: str = "TST-1") -> Issue:
    return Issue(
        issue_id=issue_id,
        title="Test",
        summary="Test issue",
        builder_prompt="fix the bug",
    )


class TestInit:
    def test_defaults(self) -> None:
        adapter = AcpxBuilderAdapter()
        assert adapter.ADAPTER_NAME == "acpx"
        assert adapter.AGENT_NAME == "opencode"
        assert adapter.agent == "opencode"
        assert adapter.model is None
        assert adapter.permissions == "full-auto"

    def test_custom_agent(self) -> None:
        adapter = AcpxBuilderAdapter(agent="codex", model="gpt-4o")
        assert adapter.AGENT_NAME == "codex"
        assert adapter.model == "gpt-4o"


class TestBuildCommand:
    def test_basic_command(self) -> None:
        adapter = AcpxBuilderAdapter(agent="opencode")
        cmd = adapter._build_command("fix the bug")
        assert cmd[0] == "npx"
        assert "-y" in cmd
        assert "acpx" in cmd
        assert "opencode" in cmd
        assert "--format" in cmd
        assert "json" in cmd
        assert cmd[-1] == "fix the bug"

    def test_with_session(self) -> None:
        adapter = AcpxBuilderAdapter(agent="codex", session_name="my-session")
        cmd = adapter._build_command("prompt")
        assert "-s" in cmd
        idx = cmd.index("-s")
        assert cmd[idx + 1] == "my-session"

    def test_with_permissions(self) -> None:
        adapter = AcpxBuilderAdapter(permissions="approve-reads")
        cmd = adapter._build_command("prompt")
        assert "--permissions" in cmd
        idx = cmd.index("--permissions")
        assert cmd[idx + 1] == "approve-reads"


class TestBuildEnv:
    def test_model_in_env(self) -> None:
        adapter = AcpxBuilderAdapter(model="minimax/MiniMax-M2.5")
        env = adapter._build_env()
        assert env.get("ACPX_MODEL") == "minimax/MiniMax-M2.5"

    def test_no_model(self) -> None:
        adapter = AcpxBuilderAdapter()
        env = adapter._build_env()
        assert "ACPX_MODEL" not in env


class TestMapEvents:
    def test_text_event(self) -> None:
        adapter = AcpxBuilderAdapter()
        events = adapter.map_events([{"type": "text", "params": {"text": "hello"}}])
        assert len(events) == 1
        assert events[0].kind == "message"
        assert events[0].text == "hello"

    def test_tool_call_bash(self) -> None:
        adapter = AcpxBuilderAdapter()
        events = adapter.map_events(
            [
                {
                    "type": "tool_call",
                    "params": {
                        "name": "bash",
                        "input": {"command": "ls -la"},
                    },
                }
            ]
        )
        assert len(events) == 1
        assert events[0].kind == "command_end"
        assert events[0].text == "ls -la"

    def test_tool_call_write(self) -> None:
        adapter = AcpxBuilderAdapter()
        events = adapter.map_events(
            [
                {
                    "type": "tool_call",
                    "params": {
                        "name": "write_file",
                        "input": {"path": "src/foo.py"},
                    },
                }
            ]
        )
        assert len(events) == 1
        assert events[0].kind == "file_change"
        assert events[0].file_path == "src/foo.py"

    def test_tool_call_unknown(self) -> None:
        adapter = AcpxBuilderAdapter()
        events = adapter.map_events(
            [
                {
                    "type": "tool_call",
                    "params": {"name": "search", "input": {"query": "foo"}},
                }
            ]
        )
        assert len(events) == 1
        assert events[0].kind == "message"
        assert "search" in events[0].text

    def test_result_event(self) -> None:
        adapter = AcpxBuilderAdapter()
        events = adapter.map_events([{"type": "result", "params": {"text": "done"}}])
        assert len(events) == 1
        assert events[0].kind == "turn_end"

    def test_error_event(self) -> None:
        adapter = AcpxBuilderAdapter()
        events = adapter.map_events([{"type": "error", "params": {"message": "crash"}}])
        assert len(events) == 1
        assert events[0].kind == "error"
        assert events[0].text == "crash"

    def test_jsonrpc_method_format(self) -> None:
        adapter = AcpxBuilderAdapter()
        events = adapter.map_events(
            [
                {
                    "method": "tools/call",
                    "params": {
                        "name": "Edit",
                        "input": {"path": "README.md"},
                    },
                }
            ]
        )
        assert len(events) == 1
        assert events[0].kind == "file_change"

    def test_empty_events(self) -> None:
        adapter = AcpxBuilderAdapter()
        events = adapter.map_events([])
        assert events == []


class TestRun:
    @patch("spec_orch.services.acpx_builder_adapter.subprocess.Popen")
    def test_run_success(self, mock_popen: MagicMock, tmp_path: Path) -> None:
        mock_process = MagicMock()
        mock_process.stdout = iter(
            [
                '{"type": "text", "params": {"text": "working"}}\n',
                '{"type": "result", "params": {"text": "done"}}\n',
            ]
        )
        mock_process.stderr = iter([])
        mock_process.returncode = 0
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process

        adapter = AcpxBuilderAdapter(agent="opencode")
        result = adapter.run(issue=_make_issue(), workspace=tmp_path)

        assert result.succeeded is True
        assert result.adapter == "acpx"
        assert result.agent == "opencode"
        assert (tmp_path / "builder_report.json").exists()

    @patch("spec_orch.services.acpx_builder_adapter.subprocess.Popen")
    def test_run_failure(self, mock_popen: MagicMock, tmp_path: Path) -> None:
        mock_process = MagicMock()
        mock_process.stdout = iter(['{"type": "error", "params": {"message": "crash"}}\n'])
        mock_process.stderr = iter(["error output\n"])
        mock_process.returncode = 1
        mock_process.wait.return_value = 1
        mock_popen.return_value = mock_process

        adapter = AcpxBuilderAdapter(agent="codex")
        result = adapter.run(issue=_make_issue(), workspace=tmp_path)

        assert result.succeeded is False
        assert result.agent == "codex"

    @patch(
        "spec_orch.services.acpx_builder_adapter.subprocess.Popen",
        side_effect=FileNotFoundError("npx not found"),
    )
    def test_run_executable_not_found(self, mock_popen: MagicMock, tmp_path: Path) -> None:
        adapter = AcpxBuilderAdapter()
        result = adapter.run(issue=_make_issue(), workspace=tmp_path)
        assert result.succeeded is False
        assert "not found" in result.stderr


class TestAdapterFactory:
    def test_create_acpx_builder(self, tmp_path: Path) -> None:
        from spec_orch.services.adapter_factory import create_builder

        toml = {
            "builder": {
                "adapter": "acpx",
                "agent": "opencode",
                "model": "minimax/MiniMax-M2.5",
                "timeout_seconds": 900,
            }
        }
        builder = create_builder(tmp_path, toml_override=toml)
        assert isinstance(builder, AcpxBuilderAdapter)
        assert builder.agent == "opencode"
        assert builder.model == "minimax/MiniMax-M2.5"
        assert builder.absolute_timeout_seconds == 900.0


class TestSessionManagement:
    @patch("spec_orch.services.acpx_builder_adapter.subprocess.run")
    def test_ensure_session(self, mock_run: MagicMock) -> None:
        adapter = AcpxBuilderAdapter(session_name="test-session")
        adapter._ensure_session(Path("/fake"))
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "sessions" in cmd
        assert "ensure" in cmd

    @patch("spec_orch.services.acpx_builder_adapter.subprocess.run")
    def test_cancel_session(self, mock_run: MagicMock) -> None:
        adapter = AcpxBuilderAdapter(session_name="test-session")
        adapter.cancel_session(Path("/fake"))
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "cancel" in cmd

    def test_cancel_without_session_noop(self) -> None:
        adapter = AcpxBuilderAdapter()
        adapter.cancel_session(Path("/fake"))


class TestCollectArtifacts:
    def test_collects_existing(self, tmp_path: Path) -> None:
        report = tmp_path / "builder_report.json"
        report.write_text("{}")
        adapter = AcpxBuilderAdapter()
        artifacts = adapter.collect_artifacts(tmp_path)
        assert report in artifacts

    def test_empty_when_no_artifacts(self, tmp_path: Path) -> None:
        adapter = AcpxBuilderAdapter()
        assert adapter.collect_artifacts(tmp_path) == []
