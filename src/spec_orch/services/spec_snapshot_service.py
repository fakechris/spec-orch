from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from spec_orch.domain.models import (
    Decision,
    Issue,
    IssueContext,
    Question,
    SpecSnapshot,
)


def write_spec_snapshot(workspace: Path, snapshot: SpecSnapshot) -> Path:
    """Persist a SpecSnapshot to workspace/spec_snapshot.json."""
    path = workspace / "spec_snapshot.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(snapshot)
    data["issue"]["context"] = asdict(snapshot.issue.context)
    # IAC migration: "intent" is the canonical name; keep "summary" for compatibility.
    data["issue"]["intent"] = snapshot.issue.summary
    path.write_text(json.dumps(data, indent=2, default=str) + "\n")
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
    return SpecSnapshot(
        version=1,
        approved=approved,
        approved_by=None,
        issue=issue,
    )
