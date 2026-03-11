"""Tests for PlannerAdapter protocol, LiteLLMPlannerAdapter, questions/spec CLI,
and RunController.advance() for plan stage transitions."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from spec_orch.cli import app
from spec_orch.domain.models import (
    Issue,
    IssueContext,
    PlannerResult,
    Question,
    RunState,
)
from spec_orch.services.run_controller import RunController
from spec_orch.services.spec_snapshot_service import (
    create_initial_snapshot,
    read_spec_snapshot,
    write_spec_snapshot,
)


def _make_issue(issue_id: str = "SPC-TEST-1") -> Issue:
    return Issue(
        issue_id=issue_id,
        title="Test Issue",
        summary="A test issue for planning.",
        builder_prompt="Implement the feature.",
        acceptance_criteria=["Tests pass"],
        context=IssueContext(),
    )


def _make_fixture(tmp_path: Path, issue_id: str = "SPC-TEST-1") -> Path:
    fixtures_dir = tmp_path / "fixtures" / "issues"
    fixtures_dir.mkdir(parents=True)
    issue = _make_issue(issue_id)
    fixture = {
        "issue_id": issue.issue_id,
        "title": issue.title,
        "summary": issue.summary,
        "builder_prompt": issue.builder_prompt,
        "acceptance_criteria": issue.acceptance_criteria,
        "verification_commands": {},
        "context": {"files_to_read": [], "architecture_notes": "", "constraints": []},
    }
    path = fixtures_dir / f"{issue_id}.json"
    path.write_text(json.dumps(fixture, indent=2))
    return tmp_path


# ──────────────────────── PlannerResult model ────────────────────────


def test_planner_result_defaults():
    pr = PlannerResult(questions=[])
    assert pr.questions == []
    assert pr.spec_draft is None
    assert pr.raw_response == ""


def test_planner_result_with_questions():
    q = Question(
        id="q-1", asked_by="planner", target="user",
        category="requirement", blocking=True, text="What API?",
    )
    pr = PlannerResult(questions=[q], raw_response='{"questions": []}')
    assert len(pr.questions) == 1
    assert pr.questions[0].blocking is True


# ───────────────────── RunController.advance() ─────────────────────


class FakePlannerAdapter:
    ADAPTER_NAME = "fake_planner"

    def plan(self, *, issue, workspace, existing_snapshot=None):
        return PlannerResult(
            questions=[
                Question(
                    id="q-auto-1", asked_by="planner", target="user",
                    category="requirement", blocking=True,
                    text="Which database should we use?",
                ),
            ],
        )


def test_advance_draft_with_planner(tmp_path):
    repo = _make_fixture(tmp_path)
    controller = RunController(
        repo_root=repo,
        planner_adapter=FakePlannerAdapter(),
    )
    result = controller.advance("SPC-TEST-1")
    assert result.state == RunState.SPEC_DRAFTING

    snapshot = read_spec_snapshot(result.workspace)
    assert snapshot is not None
    assert len(snapshot.questions) == 1
    assert snapshot.questions[0].id == "q-auto-1"


def test_advance_draft_without_planner_goes_to_spec_drafting(tmp_path):
    repo = _make_fixture(tmp_path)
    controller = RunController(repo_root=repo)
    result = controller.advance("SPC-TEST-1")
    assert result.state == RunState.SPEC_DRAFTING


def test_advance_spec_drafting_rejects_unresolved_blocking(tmp_path):
    repo = _make_fixture(tmp_path)
    issue = _make_issue()
    workspace = tmp_path / ".spec_orch_runs" / "SPC-TEST-1"
    workspace.mkdir(parents=True)

    snapshot = create_initial_snapshot(issue)
    snapshot.questions.append(
        Question(
            id="q-block", asked_by="planner", target="user",
            category="requirement", blocking=True, text="Blocking Q",
        )
    )
    write_spec_snapshot(workspace, snapshot)
    (workspace / "report.json").write_text(
        json.dumps({"state": "spec_drafting", "run_id": "r-1",
                     "issue_id": "SPC-TEST-1", "title": "Test"})
    )

    controller = RunController(repo_root=repo)
    with pytest.raises(ValueError, match="unresolved blocking"):
        controller.advance("SPC-TEST-1")


def test_advance_spec_drafting_approves_when_all_answered(tmp_path):
    repo = _make_fixture(tmp_path)
    issue = _make_issue()
    workspace = tmp_path / ".spec_orch_runs" / "SPC-TEST-1"
    workspace.mkdir(parents=True)

    snapshot = create_initial_snapshot(issue)
    write_spec_snapshot(workspace, snapshot)
    (workspace / "report.json").write_text(
        json.dumps({"state": "spec_drafting", "run_id": "r-1",
                     "issue_id": "SPC-TEST-1", "title": "Test"})
    )

    controller = RunController(repo_root=repo)
    result = controller.advance("SPC-TEST-1")
    assert result.state == RunState.SPEC_APPROVED

    updated_snapshot = read_spec_snapshot(workspace)
    assert updated_snapshot is not None
    assert updated_snapshot.approved is True


# ───────────────────── questions CLI ─────────────────────


def test_questions_add_and_list(tmp_path):
    repo = _make_fixture(tmp_path)
    workspace = tmp_path / ".spec_orch_runs" / "SPC-TEST-1"
    workspace.mkdir(parents=True)
    issue = _make_issue()
    snapshot = create_initial_snapshot(issue)
    write_spec_snapshot(workspace, snapshot)

    runner = CliRunner()
    result = runner.invoke(app, [
        "questions", "add", "SPC-TEST-1",
        "--text", "What framework?",
        "--category", "architecture",
        "--blocking",
        "--repo-root", str(repo),
    ])
    assert result.exit_code == 0
    assert "added question" in result.stdout

    result = runner.invoke(app, [
        "questions", "list", "SPC-TEST-1",
        "--repo-root", str(repo),
    ])
    assert result.exit_code == 0
    assert "What framework?" in result.stdout
    assert "[architecture]" in result.stdout
    assert "[blocking]" in result.stdout


def test_questions_answer(tmp_path):
    repo = _make_fixture(tmp_path)
    workspace = tmp_path / ".spec_orch_runs" / "SPC-TEST-1"
    workspace.mkdir(parents=True)
    issue = _make_issue()
    snapshot = create_initial_snapshot(issue)
    snapshot.questions.append(
        Question(
            id="q-1", asked_by="user", target="user",
            category="requirement", blocking=True, text="Question?",
        )
    )
    write_spec_snapshot(workspace, snapshot)

    runner = CliRunner()
    result = runner.invoke(app, [
        "questions", "answer", "SPC-TEST-1", "q-1",
        "--answer", "Use React",
        "--decided-by", "chris",
        "--repo-root", str(repo),
    ])
    assert result.exit_code == 0
    assert "answered q-1" in result.stdout

    updated = read_spec_snapshot(workspace)
    assert len(updated.decisions) == 1
    assert updated.decisions[0].answer == "Use React"


# ───────────────────── spec CLI ─────────────────────


def test_spec_draft_and_show(tmp_path):
    repo = _make_fixture(tmp_path)
    workspace = tmp_path / ".spec_orch_runs" / "SPC-TEST-1"
    workspace.mkdir(parents=True)

    runner = CliRunner()
    result = runner.invoke(app, [
        "spec", "draft", "SPC-TEST-1",
        "--repo-root", str(repo),
    ])
    assert result.exit_code == 0
    assert "created draft spec v1" in result.stdout

    result = runner.invoke(app, [
        "spec", "show", "SPC-TEST-1",
        "--repo-root", str(repo),
    ])
    assert result.exit_code == 0
    assert "version=1" in result.stdout
    assert "approved=False" in result.stdout


def test_spec_approve(tmp_path):
    repo = _make_fixture(tmp_path)
    workspace = tmp_path / ".spec_orch_runs" / "SPC-TEST-1"
    workspace.mkdir(parents=True)
    issue = _make_issue()
    snapshot = create_initial_snapshot(issue)
    write_spec_snapshot(workspace, snapshot)

    runner = CliRunner()
    result = runner.invoke(app, [
        "spec", "approve", "SPC-TEST-1",
        "--approved-by", "chris",
        "--repo-root", str(repo),
    ])
    assert result.exit_code == 0
    assert "spec approved" in result.stdout

    updated = read_spec_snapshot(workspace)
    assert updated.approved is True
    assert updated.approved_by == "chris"


def test_spec_approve_blocked_by_unresolved_questions(tmp_path):
    repo = _make_fixture(tmp_path)
    workspace = tmp_path / ".spec_orch_runs" / "SPC-TEST-1"
    workspace.mkdir(parents=True)
    issue = _make_issue()
    snapshot = create_initial_snapshot(issue)
    snapshot.questions.append(
        Question(
            id="q-b", asked_by="planner", target="user",
            category="risk", blocking=True, text="Risk?",
        )
    )
    write_spec_snapshot(workspace, snapshot)

    runner = CliRunner()
    result = runner.invoke(app, [
        "spec", "approve", "SPC-TEST-1",
        "--repo-root", str(repo),
    ])
    assert result.exit_code == 1
    assert "unresolved blocking" in result.stdout


# ───────────────────── advance CLI ─────────────────────


def test_advance_cli_command(tmp_path):
    repo = _make_fixture(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, [
        "advance", "SPC-TEST-1",
        "--repo-root", str(repo),
    ])
    assert result.exit_code == 0
    assert "state=spec_drafting" in result.stdout


# ───────────────────── LiteLLMPlannerAdapter ─────────────────────


def test_litellm_planner_adapter_parse_response():
    from spec_orch.services.litellm_planner_adapter import LiteLLMPlannerAdapter

    adapter = LiteLLMPlannerAdapter(model="test/model")
    issue = _make_issue()

    mock_tool_call = MagicMock()
    mock_tool_call.function.arguments = json.dumps({
        "questions": [
            {"id": "q-1", "category": "requirement", "blocking": True, "text": "Which DB?"},
            {"id": "q-2", "category": "architecture", "blocking": False, "text": "Scaling?"},
        ],
        "spec_summary": None,
    })

    mock_message = MagicMock()
    mock_message.tool_calls = [mock_tool_call]
    mock_message.content = None

    mock_choice = MagicMock()
    mock_choice.message = mock_message

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    result = adapter._parse_response(mock_response, issue)
    assert len(result.questions) == 2
    assert result.questions[0].text == "Which DB?"
    assert result.questions[0].blocking is True
    assert result.questions[1].blocking is False


def test_litellm_planner_adapter_build_user_message():
    from spec_orch.services.litellm_planner_adapter import LiteLLMPlannerAdapter

    adapter = LiteLLMPlannerAdapter(model="test/model")
    issue = _make_issue()
    msg = adapter._build_user_message(issue, None)
    assert "SPC-TEST-1" in msg
    assert "Test Issue" in msg
    assert "Implement the feature" in msg


def test_litellm_planner_adapter_raises_without_litellm():
    from spec_orch.services.litellm_planner_adapter import LiteLLMPlannerAdapter

    adapter = LiteLLMPlannerAdapter(model="test/model")
    issue = _make_issue()

    with patch.dict("sys.modules", {"litellm": None}), pytest.raises(
        ImportError, match="litellm is required"
    ):
        adapter.plan(issue=issue, workspace=Path("/tmp"))
