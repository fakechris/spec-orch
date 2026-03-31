from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from spec_orch.domain.models import Decision, Issue, IssueContext, Question, SpecSnapshot
from spec_orch.services.io import atomic_write_json


def write_spec_snapshot(workspace: Path, snapshot: SpecSnapshot) -> Path:
    """Persist a SpecSnapshot to workspace/spec_snapshot.json."""
    path = workspace / "spec_snapshot.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(snapshot)
    data["issue"]["intent"] = snapshot.issue.summary
    atomic_write_json(path, data, default=str)
    return path


def read_spec_snapshot(workspace: Path) -> SpecSnapshot | None:
    """Load a previously persisted SpecSnapshot, or None if absent."""
    path = workspace / "spec_snapshot.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())

    ctx_data = data["issue"].get("context", {})
    context = IssueContext(
        files_to_read=ctx_data.get("files_to_read", []),
        architecture_notes=ctx_data.get("architecture_notes", ""),
        constraints=ctx_data.get("constraints", []),
    )
    issue = Issue(
        issue_id=data["issue"]["issue_id"],
        title=data["issue"]["title"],
        summary=data["issue"].get("summary") or data["issue"].get("intent", ""),
        builder_prompt=data["issue"].get("builder_prompt"),
        verification_commands=data["issue"].get("verification_commands", {}),
        context=context,
        acceptance_criteria=data["issue"].get("acceptance_criteria", []),
        mission_id=data["issue"].get("mission_id"),
        spec_section=data["issue"].get("spec_section"),
        run_class=data["issue"].get("run_class"),
        labels=data["issue"].get("labels", []),
    )
    questions = [
        Question(
            id=q["id"],
            asked_by=q["asked_by"],
            target=q["target"],
            category=q["category"],
            blocking=q["blocking"],
            text=q["text"],
            answer=q.get("answer"),
            answered_by=q.get("answered_by"),
        )
        for q in data.get("questions", [])
    ]
    decisions = [
        Decision(
            question_id=d["question_id"],
            answer=d["answer"],
            decided_by=d["decided_by"],
            timestamp=d["timestamp"],
        )
        for d in data.get("decisions", [])
    ]
    return SpecSnapshot(
        version=data["version"],
        approved=data["approved"],
        approved_by=data.get("approved_by"),
        issue=issue,
        questions=questions,
        decisions=decisions,
    )


def create_initial_snapshot(issue: Issue, *, approved: bool = False) -> SpecSnapshot:
    """Create a version-1 snapshot from an Issue, optionally pre-approved."""
    return SpecSnapshot(version=1, approved=approved, approved_by=None, issue=issue)


def approve_spec_snapshot(snapshot: SpecSnapshot, *, approved_by: str) -> SpecSnapshot:
    """Approve a snapshot in place once blocking questions are resolved."""
    if snapshot.has_unresolved_blocking_questions():
        raise ValueError("cannot approve snapshot: unresolved blocking questions remain")
    snapshot.approved = True
    snapshot.approved_by = approved_by
    snapshot.version += 1
    return snapshot


def auto_approve_spec_snapshot(snapshot: SpecSnapshot) -> SpecSnapshot:
    """Auto-approve a snapshot without changing approver identity."""
    if snapshot.has_unresolved_blocking_questions():
        raise ValueError("cannot auto-approve snapshot: unresolved blocking questions remain")
    snapshot.approved = True
    snapshot.version += 1
    return snapshot
