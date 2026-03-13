import json
from pathlib import Path

from spec_orch.domain.models import (
    Decision,
    Issue,
    IssueContext,
    Question,
    SpecSnapshot,
)
from spec_orch.services.spec_snapshot_service import (
    create_initial_snapshot,
    read_spec_snapshot,
    write_spec_snapshot,
)


def _sample_issue() -> Issue:
    return Issue(
        issue_id="SPC-SNAP",
        title="Snapshot test",
        summary="Verify snapshot round-trip.",
        builder_prompt="Do the thing.",
        context=IssueContext(
            files_to_read=["src/a.py"],
            architecture_notes="notes",
            constraints=["fast"],
        ),
        acceptance_criteria=["tests pass"],
    )


def test_write_and_read_snapshot_round_trip(tmp_path: Path) -> None:
    issue = _sample_issue()
    snap = SpecSnapshot(
        version=1,
        approved=True,
        approved_by="chris",
        issue=issue,
        questions=[
            Question(
                id="q1",
                asked_by="orchestrator",
                target="user",
                category="requirement",
                blocking=True,
                text="Which DB?",
                answer="Postgres",
                answered_by="chris",
            ),
        ],
        decisions=[
            Decision(
                question_id="q1",
                answer="Postgres",
                decided_by="chris",
                timestamp="2026-03-11T00:00:00Z",
            ),
        ],
    )

    path = write_spec_snapshot(tmp_path, snap)
    assert path.exists()

    data = json.loads(path.read_text())
    assert data["version"] == 1
    assert data["approved"] is True
    assert data["issue"]["issue_id"] == "SPC-SNAP"
    assert len(data["questions"]) == 1
    assert data["questions"][0]["answer"] == "Postgres"

    loaded = read_spec_snapshot(tmp_path)
    assert loaded is not None
    assert loaded.version == 1
    assert loaded.approved is True
    assert loaded.approved_by == "chris"
    assert loaded.issue.issue_id == "SPC-SNAP"
    assert loaded.issue.builder_prompt == "Do the thing."
    assert loaded.issue.context.files_to_read == ["src/a.py"]
    assert len(loaded.questions) == 1
    assert loaded.questions[0].answer == "Postgres"
    assert len(loaded.decisions) == 1
    assert loaded.decisions[0].decided_by == "chris"


def test_read_spec_snapshot_returns_none_if_absent(tmp_path: Path) -> None:
    assert read_spec_snapshot(tmp_path) is None


def test_create_initial_snapshot_auto_approved() -> None:
    issue = _sample_issue()
    snap = create_initial_snapshot(issue, approved=True)
    assert snap.version == 1
    assert snap.approved is True
    assert snap.approved_by is None
    assert snap.issue.issue_id == "SPC-SNAP"
    assert snap.questions == []
    assert snap.decisions == []
    assert not snap.has_unresolved_blocking_questions()


def test_has_unresolved_blocking_questions() -> None:
    issue = _sample_issue()
    snap = SpecSnapshot(
        version=1,
        approved=False,
        approved_by=None,
        issue=issue,
        questions=[
            Question(
                id="q1",
                asked_by="orch",
                target="user",
                category="requirement",
                blocking=True,
                text="What version?",
            ),
            Question(
                id="q2",
                asked_by="orch",
                target="user",
                category="environment",
                blocking=False,
                text="Optional detail?",
            ),
        ],
    )
    assert snap.has_unresolved_blocking_questions()

    snap.decisions.append(
        Decision(
            question_id="q1",
            answer="v3",
            decided_by="chris",
            timestamp="2026-03-11T00:00:00Z",
        )
    )
    assert not snap.has_unresolved_blocking_questions()


def test_run_issue_creates_spec_snapshot(tmp_path: Path) -> None:
    from spec_orch.services.run_controller import RunController

    fixtures_dir = tmp_path / "fixtures" / "issues"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "SPC-SNAP-RUN.json").write_text(
        json.dumps(
            {
                "issue_id": "SPC-SNAP-RUN",
                "title": "Snapshot in run",
                "summary": "Verify run_issue creates snapshot.",
            }
        )
    )
    controller = RunController(repo_root=tmp_path)
    result = controller.run_issue("SPC-SNAP-RUN")

    snap_path = result.workspace / "spec_snapshot.json"
    assert snap_path.exists()

    loaded = read_spec_snapshot(result.workspace)
    assert loaded is not None
    assert loaded.approved is True
    assert loaded.issue.issue_id == "SPC-SNAP-RUN"
