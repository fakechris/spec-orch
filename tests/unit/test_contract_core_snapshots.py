from __future__ import annotations

import pytest

from spec_orch.contract_core.snapshots import (
    approve_spec_snapshot,
    auto_approve_spec_snapshot,
    create_initial_snapshot,
)
from spec_orch.domain.models import Issue, IssueContext, Question


def _sample_issue() -> Issue:
    return Issue(
        issue_id="E7-SNAP",
        title="Contract core snapshot",
        summary="Check snapshot helpers.",
        context=IssueContext(),
    )


def test_approve_spec_snapshot_bumps_version_and_sets_approver() -> None:
    snapshot = create_initial_snapshot(_sample_issue(), approved=False)

    updated = approve_spec_snapshot(snapshot, approved_by="operator")

    assert updated.approved is True
    assert updated.approved_by == "operator"
    assert updated.version == 2


def test_approve_spec_snapshot_rejects_unresolved_blocking_questions() -> None:
    snapshot = create_initial_snapshot(_sample_issue(), approved=False)
    snapshot.questions.append(
        Question(
            id="q-blocking",
            asked_by="planner",
            target="user",
            category="requirement",
            blocking=True,
            text="Need answer",
        )
    )

    with pytest.raises(ValueError, match="unresolved blocking"):
        approve_spec_snapshot(snapshot, approved_by="operator")


def test_auto_approve_spec_snapshot_bumps_version_without_approver() -> None:
    snapshot = create_initial_snapshot(_sample_issue(), approved=False)

    updated = auto_approve_spec_snapshot(snapshot)

    assert updated.approved is True
    assert updated.approved_by is None
    assert updated.version == 2
