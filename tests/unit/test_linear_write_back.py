from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from spec_orch.domain.models import (
    BuilderResult,
    GateFlowControl,
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
from spec_orch.services.linear_mirror import build_linear_mirror_document
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


def test_post_run_summary_includes_gate_flow_control_signals(tmp_path: Path) -> None:
    client = MagicMock()
    client.add_comment.return_value = {"success": True}
    svc = LinearWriteBackService(client=client)

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

    svc.post_run_summary(linear_id="abc-flow", result=result)

    body = client.add_comment.call_args[0][1]
    assert "Promotion signal" in body
    assert "standard" in body
    assert "Backtrack reason" in body


def test_post_gate_update_includes_gate_flow_control_signals(tmp_path: Path) -> None:
    client = MagicMock()
    client.add_comment.return_value = {"success": True}
    svc = LinearWriteBackService(client=client)

    gate = GateVerdict(
        mergeable=False,
        failed_conditions=["review"],
        flow_control=GateFlowControl(
            retry_recommended=True,
            escalation_required=True,
            backtrack_reason="human_acceptance",
        ),
    )

    svc.post_gate_update(linear_id="abc-456", gate=gate, explain_path=None)

    body = client.add_comment.call_args[0][1]
    assert "Retry recommended" in body
    assert "Escalation required" in body
    assert "human_acceptance" in body


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
    from spec_orch.services.canonical_issue import canonical_issue_from_linear_intake
    from spec_orch.services.intake_handoff import build_workspace_handoff

    client = MagicMock()
    client.update_issue_description.return_value = {"success": True}
    svc = LinearWriteBackService(client=client)
    intake = _make_linear_intake_document()
    canonical = canonical_issue_from_linear_intake(
        issue_id="SON-789",
        title="Structured mirror",
        intake=intake,
    )
    handoff = build_workspace_handoff(canonical)

    svc.rewrite_issue_for_intake(
        linear_id="abc-789",
        intake=intake,
        mirror=build_linear_mirror_document(
            intake_state=LinearIntakeState.READY_FOR_WORKSPACE.value,
            canonical=canonical,
            handoff=handoff,
            plan_summary=["Mirror current plan state into Linear."],
        ),
    )

    client.update_issue_description.assert_called_once()
    description = client.update_issue_description.call_args.kwargs["description"]
    assert "## Problem" in description
    assert "## Acceptance" in description
    assert "## SpecOrch Mirror" in description
    assert '"next_action": "create_workspace"' in description


def test_post_intake_summary_includes_mirror_summary() -> None:
    from spec_orch.services.canonical_issue import canonical_issue_from_linear_intake
    from spec_orch.services.intake_handoff import build_workspace_handoff

    client = MagicMock()
    client.add_comment.return_value = {"success": True}
    svc = LinearWriteBackService(client=client)
    intake = _make_linear_intake_document()
    canonical = canonical_issue_from_linear_intake(
        issue_id="SON-790",
        title="Mirror summary",
        intake=intake,
    )
    handoff = build_workspace_handoff(canonical)

    svc.post_intake_summary(
        linear_id="abc-790",
        state=LinearIntakeState.READY_FOR_WORKSPACE,
        intake=intake,
        mirror=build_linear_mirror_document(
            intake_state=LinearIntakeState.READY_FOR_WORKSPACE.value,
            canonical=canonical,
            handoff=handoff,
            plan_summary=["Sync prior Linear status drift."],
        ),
    )

    body = client.add_comment.call_args[0][1]
    assert "SpecOrch Mirror" in body
    assert "create_workspace" in body
    assert "Sync prior Linear status drift." in body


def test_sync_issue_mirror_from_mission_updates_description_with_plan_sync(tmp_path: Path) -> None:
    from spec_orch.dashboard.launcher import _create_mission_draft

    client = MagicMock()
    client.update_issue_description.return_value = {"success": True}
    svc = LinearWriteBackService(client=client)

    _create_mission_draft(
        tmp_path,
        {
            "title": "Plan Sync",
            "mission_id": "plan-sync",
            "problem": "Linear drifts from local execution state.",
            "goal": "Mirror compact plan state into Linear.",
            "intent": "Sync plan state.",
            "acceptance_criteria": ["Linear shows a compact plan snapshot."],
            "constraints": [],
            "evidence_expectations": ["plan snapshot"],
        },
    )
    (tmp_path / "docs" / "specs" / "plan-sync" / "plan.json").write_text(
        """{
  "plan_id": "plan-1",
  "mission_id": "plan-sync",
  "status": "draft",
  "waves": [
    {
      "wave_number": 0,
      "description": "Scaffold contracts",
      "work_packets": []
    }
  ]
}
""",
        encoding="utf-8",
    )
    (tmp_path / ".spec_orch" / "acceptance").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".spec_orch" / "acceptance" / "stability_acceptance_status.json").write_text(
        """{
  "summary": {
    "overall_status": "pass"
  }
}
""",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "acceptance-history").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "acceptance-history" / "index.json").write_text(
        """{
  "releases": [
    {
      "release_id": "bundle-1",
      "bundle_path": "docs/acceptance-history/releases/bundle-1",
      "overall_status": "pass"
    }
  ]
}
""",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "specs" / "plan-sync" / "operator" / "launch.json").write_text(
        """{
  "metadata": {
    "next_bottleneck": "Lifecycle"
  }
}
""",
        encoding="utf-8",
    )

    mirror = svc.sync_issue_mirror_from_mission(
        repo_root=tmp_path,
        mission_id="plan-sync",
        linear_id="issue-1",
        current_description="mission: plan-sync",
    )

    assert mirror is not None
    assert mirror["plan_sync"]["plan_state"] == "draft"
    assert mirror["next_action"] == "review_plan"
    description = client.update_issue_description.call_args.kwargs["description"]
    assert '"plan_state": "draft"' in description
    assert '"next_action": "review_plan"' in description
    assert '"latest_acceptance_status": "pass"' in description
    assert '"next_bottleneck": "Lifecycle"' in description


def test_preview_issue_mirror_drift_from_mission_does_not_mutate_linear(tmp_path: Path) -> None:
    from spec_orch.dashboard.launcher import _create_mission_draft

    client = MagicMock()
    client.query.return_value = {"issue": {"id": "issue-1", "description": "mission: preview"}}
    svc = LinearWriteBackService(client=client)

    _create_mission_draft(
        tmp_path,
        {
            "title": "Preview",
            "mission_id": "preview",
            "problem": "Linear has drifted.",
            "goal": "Report drift before writing.",
            "intent": "Preview mirror drift.",
            "acceptance_criteria": ["Drift is visible before mutation."],
            "constraints": [],
            "evidence_expectations": ["drift report"],
        },
    )
    (tmp_path / "docs" / "specs" / "preview" / "plan.json").write_text(
        """{
  "plan_id": "plan-1",
  "mission_id": "preview",
  "status": "draft",
  "waves": []
}
""",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "specs" / "preview" / "operator" / "launch.json").write_text(
        """{
  "linear_issue": {
    "id": "issue-1",
    "identifier": "SON-1",
    "title": "Preview"
  }
}
""",
        encoding="utf-8",
    )

    report = svc.preview_issue_mirror_drift_from_mission(
        repo_root=tmp_path,
        mission_id="preview",
        linear_id="issue-1",
    )

    assert report is not None
    assert report["status"] == "missing_mirror"
    client.update_issue_description.assert_not_called()


def test_preview_issue_mirror_drift_normalizes_linear_id_whitespace(tmp_path: Path) -> None:
    from spec_orch.dashboard.launcher import _create_mission_draft

    client = MagicMock()
    client.query.return_value = {"issue": {"id": "issue-1", "description": "mission: preview"}}
    svc = LinearWriteBackService(client=client)

    _create_mission_draft(
        tmp_path,
        {
            "title": "Preview",
            "mission_id": "preview",
            "problem": "Linear has drifted.",
            "goal": "Report drift before writing.",
            "intent": "Preview mirror drift.",
            "acceptance_criteria": ["Drift is visible before mutation."],
            "constraints": [],
            "evidence_expectations": ["drift report"],
        },
    )
    (tmp_path / "docs" / "specs" / "preview" / "plan.json").write_text(
        '{"plan_id":"plan-1","mission_id":"preview","status":"draft","waves":[]}\n',
        encoding="utf-8",
    )
    (tmp_path / "docs" / "specs" / "preview" / "operator" / "launch.json").write_text(
        '{"linear_issue":{"id":"issue-1","identifier":"SON-1","title":"Preview"}}\n',
        encoding="utf-8",
    )

    report = svc.preview_issue_mirror_drift_from_mission(
        repo_root=tmp_path,
        mission_id="preview",
        linear_id=" issue-1 ",
    )

    assert report is not None
    assert report["status"] == "missing_mirror"
