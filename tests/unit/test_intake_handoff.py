from __future__ import annotations

from spec_orch.domain.intake_models import CanonicalAcceptance, CanonicalIssue


def test_build_workspace_handoff_marks_ready_issue_as_ready_for_workspace() -> None:
    from spec_orch.services.intake_handoff import build_workspace_handoff

    handoff = build_workspace_handoff(
        CanonicalIssue(
            issue_id="SON-411",
            title="Intake handoff",
            problem="Operators need a deterministic handoff payload.",
            goal="Expose stable workspace placeholders before execution starts.",
            constraints=["Keep runtime creation out of SON-411."],
            acceptance=CanonicalAcceptance(
                success_conditions=["Handoff payload is deterministic."],
                verification_expectations=["Dashboard preview shows workspace contract."],
            ),
            evidence_expectations=["workspace handoff preview"],
            open_questions=[],
            current_plan_hint="Use placeholders until runtime substrate owns the real objects.",
            origin="dashboard",
            source_refs=[{"kind": "dashboard_draft", "ref": "SON-411"}],
        ),
        subject_kind="mission",
    )

    assert handoff["state"] == "ready_for_workspace"
    assert handoff["workspace_id"] == "SON-411"
    assert handoff["subject_ref"] == "mission:SON-411"
    assert handoff["workspace"]["workspace_id"] == "SON-411"
    assert handoff["workspace"]["workspace_kind"] == "mission"
    assert handoff["active_execution"]["status"] == "pending"
    assert handoff["initial_judgment"]["status"] == "pending"
    assert handoff["learning_lineage"]["status"] == "pending"


def test_build_workspace_handoff_keeps_incomplete_issue_in_draft_only() -> None:
    from spec_orch.services.intake_handoff import build_workspace_handoff

    handoff = build_workspace_handoff(
        CanonicalIssue(
            issue_id="draft-only",
            title="Draft Only",
            problem="",
            goal="",
            acceptance=CanonicalAcceptance(),
            evidence_expectations=[],
            open_questions=["[blocking] What outcome is required?"],
            origin="linear",
            source_refs=[{"kind": "linear_issue", "ref": "draft-only"}],
        ),
    )

    assert handoff["state"] == "draft_only"
    assert handoff["workspace"]["state_summary"] == "draft_only"
    assert handoff["blockers"] == [
        "problem",
        "goal",
        "acceptance",
        "verification_expectations",
        "blocking_open_questions",
    ]
