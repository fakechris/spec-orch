from __future__ import annotations

from spec_orch.domain.intake_models import CanonicalIssue
from spec_orch.services.operator_semantics import (
    handoff_blockers_for_canonical_issue,
    handoff_state_for_canonical_issue,
    workspace_from_canonical_issue,
)


def build_workspace_handoff(
    canonical: CanonicalIssue,
    *,
    subject_kind: str = "issue",
) -> dict[str, object]:
    blockers = handoff_blockers_for_canonical_issue(canonical)
    state = handoff_state_for_canonical_issue(canonical)
    workspace = workspace_from_canonical_issue(canonical, subject_kind=subject_kind)
    workspace_id = workspace.workspace_id
    subject_ref = f"{subject_kind}:{canonical.issue_id}"
    return {
        "state": state,
        "workspace_id": workspace_id,
        "subject_ref": subject_ref,
        "blockers": blockers,
        "workspace": workspace.to_dict(),
        "active_execution": {
            "status": workspace.active_execution.health,
            "subject_ref": subject_ref,
            "phase": workspace.active_execution.phase,
            "execution_session_id": workspace.active_execution.execution_session_id,
        },
        "initial_judgment": {
            "status": workspace.active_judgment.review_state,
            "subject_ref": subject_ref,
            "judgment_id": workspace.active_judgment.judgment_id,
        },
        "learning_lineage": {
            "status": workspace.learning_lineage.status,
            "subject_ref": subject_ref,
            "learning_lineage_id": workspace.learning_lineage.learning_lineage_id,
        },
        "operator_summary": canonical.title or canonical.problem or canonical.issue_id,
        "source_refs": list(canonical.source_refs),
    }
