from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from spec_orch.domain.models import (
    BuilderResult,
    GateFlowControl,
    GateVerdict,
    Issue,
    ReviewSummary,
    RunResult,
)
from spec_orch.services.github_pr_service import GitHubPRService


def _make_run_result(tmp_path: Path) -> RunResult:
    explain = tmp_path / "explain.md"
    explain.write_text("# Explain\nAll good.")
    return RunResult(
        issue=Issue(
            issue_id="SPC-50",
            title="PR test",
            summary="Test PR",
            acceptance_criteria=["Must pass lint", "Must pass tests"],
        ),
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


def test_build_pr_body_includes_key_sections(tmp_path: Path) -> None:
    svc = GitHubPRService()
    result = _make_run_result(tmp_path)
    body = svc._build_pr_body(result)
    assert "SPC-50" in body
    assert "Mergeable" in body
    assert "Acceptance Criteria" in body
    assert "Must pass lint" in body
    assert "# Explain" in body
    assert "Closes SPC-50" in body


def test_build_pr_body_includes_flow_control_section(tmp_path: Path) -> None:
    svc = GitHubPRService()
    result = _make_run_result(tmp_path)
    result.gate = GateVerdict(
        mergeable=False,
        failed_conditions=["review"],
        flow_control=GateFlowControl(
            promotion_required=True,
            promotion_target="standard",
            backtrack_reason="recoverable",
        ),
    )

    body = svc._build_pr_body(result)

    assert "### Flow Control" in body
    assert "Promotion signal: standard" in body
    assert "Backtrack reason: recoverable" in body


def test_set_gate_status_calls_gh_api(tmp_path: Path) -> None:
    svc = GitHubPRService()
    gate = GateVerdict(mergeable=True, failed_conditions=[])

    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "abc123\n"
        svc.set_gate_status(workspace=tmp_path, sha="abc123", gate=gate)

    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert "gh" in args
    assert "statuses/abc123" in " ".join(args)


def test_create_pr_returns_none_on_main_branch(tmp_path: Path) -> None:
    svc = GitHubPRService()
    with patch.object(svc, "_current_branch", return_value="main"):
        result = svc.create_pr(workspace=tmp_path, title="test", body="body")
    assert result is None
