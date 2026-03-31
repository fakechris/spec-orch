from __future__ import annotations

import pytest

from spec_orch.contract_core.decisions import (
    add_snapshot_question,
    answer_snapshot_question,
    question_status_rows,
)
from spec_orch.contract_core.snapshots import create_initial_snapshot
from spec_orch.domain.models import Issue, IssueContext


def _sample_issue() -> Issue:
    return Issue(
        issue_id="E7-DECISION",
        title="Contract core decisions",
        summary="Extract question and decision recording.",
        context=IssueContext(),
    )


def test_add_snapshot_question_appends_question() -> None:
    snapshot = create_initial_snapshot(_sample_issue(), approved=False)

    question = add_snapshot_question(
        snapshot,
        text="Which database?",
        category="requirement",
        blocking=True,
        asked_by="planner",
        question_id="q-fixed",
    )

    assert question.id == "q-fixed"
    assert snapshot.questions[-1].text == "Which database?"
    assert snapshot.questions[-1].blocking is True


def test_answer_snapshot_question_records_decision_and_updates_question() -> None:
    snapshot = create_initial_snapshot(_sample_issue(), approved=False)
    add_snapshot_question(
        snapshot,
        text="Which database?",
        category="requirement",
        blocking=True,
        asked_by="planner",
        question_id="q-fixed",
    )

    decision = answer_snapshot_question(
        snapshot,
        question_id="q-fixed",
        answer="Postgres",
        decided_by="operator",
        timestamp="2026-03-30T12:00:00Z",
    )

    assert decision.question_id == "q-fixed"
    assert snapshot.questions[0].answer == "Postgres"
    assert snapshot.questions[0].answered_by == "operator"
    assert snapshot.decisions[-1].answer == "Postgres"


def test_answer_snapshot_question_rejects_unknown_question() -> None:
    snapshot = create_initial_snapshot(_sample_issue(), approved=False)

    with pytest.raises(ValueError, match="question not found"):
        answer_snapshot_question(
            snapshot,
            question_id="missing",
            answer="Postgres",
            decided_by="operator",
            timestamp="2026-03-30T12:00:00Z",
        )


def test_question_status_rows_marks_answered_questions() -> None:
    snapshot = create_initial_snapshot(_sample_issue(), approved=False)
    add_snapshot_question(
        snapshot,
        text="Which database?",
        category="requirement",
        blocking=True,
        asked_by="planner",
        question_id="q-fixed",
    )
    answer_snapshot_question(
        snapshot,
        question_id="q-fixed",
        answer="Postgres",
        decided_by="operator",
        timestamp="2026-03-30T12:00:00Z",
    )

    rows = question_status_rows(snapshot)

    assert rows == [("q-fixed", "requirement", True, "answered", "Which database?")]
