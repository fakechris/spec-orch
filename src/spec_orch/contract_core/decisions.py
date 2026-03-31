from __future__ import annotations

from spec_orch.domain.models import Decision, Question, SpecSnapshot


def add_snapshot_question(
    snapshot: SpecSnapshot,
    *,
    text: str,
    category: str,
    blocking: bool,
    asked_by: str,
    question_id: str,
    target: str = "user",
) -> Question:
    """Append a question to a spec snapshot and return it."""
    question = Question(
        id=question_id,
        asked_by=asked_by,
        target=target,
        category=category,
        blocking=blocking,
        text=text,
    )
    snapshot.questions.append(question)
    return question


def answer_snapshot_question(
    snapshot: SpecSnapshot,
    *,
    question_id: str,
    answer: str,
    decided_by: str,
    timestamp: str,
) -> Decision:
    """Record an answer to an existing snapshot question."""
    for question in snapshot.questions:
        if question.id == question_id:
            question.answer = answer
            question.answered_by = decided_by
            decision = Decision(
                question_id=question_id,
                answer=answer,
                decided_by=decided_by,
                timestamp=timestamp,
            )
            snapshot.decisions.append(decision)
            return decision
    raise ValueError(f"question not found: {question_id}")


def question_status_rows(
    snapshot: SpecSnapshot,
) -> list[tuple[str, str, bool, str, str]]:
    """Return a normalized question listing for surfaces."""
    answered_ids = {decision.question_id for decision in snapshot.decisions}
    return [
        (
            question.id,
            question.category,
            question.blocking,
            "answered" if question.id in answered_ids else "open",
            question.text,
        )
        for question in snapshot.questions
    ]
