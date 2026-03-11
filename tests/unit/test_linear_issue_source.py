from __future__ import annotations

from unittest.mock import MagicMock

from spec_orch.services.linear_issue_source import LinearIssueSource


def _make_source(raw_issue: dict) -> tuple[LinearIssueSource, MagicMock]:
    client = MagicMock()
    client.get_issue.return_value = raw_issue
    return LinearIssueSource(client=client), client


def test_load_parses_full_description():
    raw = {
        "id": "uuid-1",
        "identifier": "SPC-42",
        "title": "Add feature X",
        "description": (
            "Overview of the task.\n\n"
            "## Builder Prompt\n"
            "Implement feature X by modifying src/main.py.\n\n"
            "## Acceptance Criteria\n"
            "- Feature X works\n"
            "- All tests pass\n"
            "* No lint errors\n\n"
            "## Context\n"
            "- src/main.py\n"
            "- src/utils.py\n"
            "Architecture is simple.\n"
        ),
    }
    source, client = _make_source(raw)
    issue = source.load("SPC-42")

    assert issue.issue_id == "SPC-42"
    assert issue.title == "Add feature X"
    assert issue.summary.startswith("Overview")
    assert issue.builder_prompt is not None
    assert "feature X" in issue.builder_prompt
    assert len(issue.acceptance_criteria) == 3
    assert "Feature X works" in issue.acceptance_criteria[0]
    assert "src/main.py" in issue.context.files_to_read
    assert "src/utils.py" in issue.context.files_to_read
    assert "Architecture" in issue.context.architecture_notes


def test_load_missing_sections():
    raw = {
        "id": "uuid-2",
        "identifier": "SPC-99",
        "title": "Simple task",
        "description": "Just do it.",
    }
    source, _ = _make_source(raw)
    issue = source.load("SPC-99")

    assert issue.issue_id == "SPC-99"
    assert issue.builder_prompt is None
    assert issue.acceptance_criteria == []
    assert issue.context.files_to_read == []


def test_load_empty_description():
    raw = {
        "id": "uuid-3",
        "identifier": "SPC-10",
        "title": "No desc",
        "description": None,
    }
    source, _ = _make_source(raw)
    issue = source.load("SPC-10")

    assert issue.issue_id == "SPC-10"
    assert issue.summary == ""
    assert issue.builder_prompt is None


def test_load_uses_identifier_from_response():
    raw = {
        "id": "uuid-4",
        "identifier": "SPC-77",
        "title": "From Linear",
        "description": "desc",
    }
    source, _ = _make_source(raw)
    issue = source.load("some-other-id")
    assert issue.issue_id == "SPC-77"


def test_default_verification_commands():
    raw = {
        "id": "uuid-5",
        "identifier": "SPC-5",
        "title": "Task",
        "description": "d",
    }
    source, _ = _make_source(raw)
    issue = source.load("SPC-5")

    assert "lint" in issue.verification_commands
    assert "test" in issue.verification_commands
    assert "typecheck" in issue.verification_commands
    assert "build" in issue.verification_commands
