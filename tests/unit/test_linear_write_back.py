from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from spec_orch.domain.models import (
    BuilderResult,
    GateVerdict,
    Issue,
    ReviewSummary,
    RunResult,
)
from spec_orch.services.linear_write_back import LinearWriteBackService


def _make_run_result(tmp_path: Path) -> RunResult:
    explain = tmp_path / "explain.md"
    explain.write_text("# Explain\nAll good.")
    return RunResult(
        issue=Issue(issue_id="SPC-42", title="Test issue", summary="A test"),
        workspace=tmp_path,
        task_spec=tmp_path / "spec.md",
        progress=tmp_path / "progress.md",
        explain=explain,
        report=tmp_path / "report.json",
        builder=BuilderResult(
            succeeded=True,
            command=["codex", "exec"],
            stdout="ok",
            stderr="",
            report_path=tmp_path / "report.json",
            adapter="codex_exec",
            agent="codex",
        ),
        review=ReviewSummary(verdict="pass", reviewed_by="alice"),
        gate=GateVerdict(mergeable=True, failed_conditions=[]),
    )


def test_post_run_summary_calls_add_comment(tmp_path: Path) -> None:
    client = MagicMock()
    client.add_comment.return_value = {"success": True}
    svc = LinearWriteBackService(client=client)

    result = _make_run_result(tmp_path)
    svc.post_run_summary(linear_id="abc-123", result=result)

    client.add_comment.assert_called_once()
    args = client.add_comment.call_args
    assert args[0][0] == "abc-123"
    body = args[0][1]
    assert "SPC-42" in body
    assert "Mergeable" in body
    assert "All conditions passed" in body
    assert "# Explain" in body


def test_post_run_summary_truncates_long_explain(tmp_path: Path) -> None:
    client = MagicMock()
    client.add_comment.return_value = {"success": True}
    svc = LinearWriteBackService(client=client)

    result = _make_run_result(tmp_path)
    result.explain.write_text("x" * 5000)
    svc.post_run_summary(linear_id="abc-123", result=result)

    body = client.add_comment.call_args[0][1]
    assert "*(truncated)*" in body
    assert len(body) < 5500


def test_update_state_on_merge(tmp_path: Path) -> None:
    client = MagicMock()
    client.update_issue_state.return_value = {"success": True}
    svc = LinearWriteBackService(client=client)

    svc.update_state_on_merge(linear_id="abc-123", target_state="Done")
    client.update_issue_state.assert_called_once_with("abc-123", "Done")


def test_post_gate_update(tmp_path: Path) -> None:
    client = MagicMock()
    client.add_comment.return_value = {"success": True}
    svc = LinearWriteBackService(client=client)

    gate = GateVerdict(mergeable=False, failed_conditions=["review"])
    explain = tmp_path / "explain.md"
    explain.write_text("# Updated\nStill blocked")

    svc.post_gate_update(linear_id="abc-456", gate=gate, explain_path=explain)

    body = client.add_comment.call_args[0][1]
    assert "Gate Re-evaluation" in body
    assert "review" in body
    assert "# Updated" in body
