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
from spec_orch.services.linear_intake import (
    LinearAcceptanceDraft,
    LinearIntakeDocument,
    LinearIntakeState,
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


def _make_linear_intake_document() -> LinearIntakeDocument:
    return LinearIntakeDocument(
        problem="Operators cannot tell whether the issue is ready.",
        goal="Show readiness directly in Linear.",
        constraints=["Keep SON-410 schema work separate."],
        acceptance=LinearAcceptanceDraft(
            success_conditions=["The issue has an explicit intake structure."],
            verification_expectations=["Readiness accepts the new shape."],
            human_judgment_required=["The current system understanding is clear."],
        ),
        evidence_expectations=["readiness output"],
        open_questions=["[non_blocking] Dashboard copy parity?"],
        current_system_understanding="Issue is ready for workspace handoff.",
    )


def test_post_intake_summary_formats_linear_native_sections() -> None:
    client = MagicMock()
    client.add_comment.return_value = {"success": True}
    svc = LinearWriteBackService(client=client)

    svc.post_intake_summary(
        linear_id="abc-789",
        state=LinearIntakeState.READY_FOR_WORKSPACE,
        intake=_make_linear_intake_document(),
    )

    body = client.add_comment.call_args[0][1]
    assert "SpecOrch Intake Summary" in body
    assert "ready_for_workspace" in body
    assert "Current System Understanding" in body
    assert "Dashboard copy parity?" in body


def test_rewrite_issue_for_intake_updates_linear_description() -> None:
    client = MagicMock()
    client.update_issue_description.return_value = {"success": True}
    svc = LinearWriteBackService(client=client)

    svc.rewrite_issue_for_intake(
        linear_id="abc-789",
        intake=_make_linear_intake_document(),
    )

    client.update_issue_description.assert_called_once()
    description = client.update_issue_description.call_args.kwargs["description"]
    assert "## Problem" in description
    assert "## Acceptance" in description
