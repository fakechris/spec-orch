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

    assert issue.verification_commands == {}


def test_context_parses_asterisk_bullet_files():
    """Linear converts `- ` to `* ` in Markdown; context parsing must handle both."""
    raw = {
        "id": "uuid-6",
        "identifier": "SPC-6",
        "title": "Asterisk test",
        "description": (
            "Overview\n\n"
            "## Context\n"
            "* src/spec_orch/cli.py\n"
            "* src/spec_orch/services/run_controller.py\n"
            "Architecture notes here.\n"
        ),
    }
    source, _ = _make_source(raw)
    issue = source.load("SPC-6")

    assert "src/spec_orch/cli.py" in issue.context.files_to_read
    assert "src/spec_orch/services/run_controller.py" in issue.context.files_to_read
    assert "Architecture" in issue.context.architecture_notes


def test_load_parses_linear_native_intake_shape() -> None:
    raw = {
        "id": "uuid-7",
        "identifier": "SON-408",
        "title": "Linear-native conversational intake",
        "description": (
            "## Problem\n"
            "Operators cannot tell whether intake is complete.\n\n"
            "## Goal\n"
            "Make intake status visible in Linear.\n\n"
            "## Constraints\n"
            "- Keep SON-410 schema extraction for later.\n\n"
            "## Acceptance\n\n"
            "### Success Conditions\n"
            "- Intake sections render in a stable order.\n\n"
            "### Verification Expectations\n"
            "- Readiness checker accepts the issue.\n"
            "- Writeback can post a summary comment.\n\n"
            "### Human Judgment Required\n"
            "- The current system understanding reads clearly.\n\n"
            "## Evidence Expectations\n"
            "- readiness output\n"
            "- Linear summary comment\n\n"
            "## Open Questions\n"
            "- [non_blocking] Should dashboard mirror the wording?\n\n"
            "## Current System Understanding\n"
            "Issue is ready for workspace handoff once the verification expectations are explicit.\n"
        ),
    }
    source, _ = _make_source(raw)
    issue = source.load("SON-408")

    assert issue.issue_id == "SON-408"
    assert issue.summary.startswith("Operators cannot tell")
    assert "Make intake status visible in Linear." in (issue.builder_prompt or "")
    assert "Issue is ready for workspace handoff" in (issue.builder_prompt or "")
    assert issue.context.constraints == ["Keep SON-410 schema extraction for later."]
    assert issue.acceptance_criteria == [
        "success: Intake sections render in a stable order.",
        "verify: Readiness checker accepts the issue.",
        "verify: Writeback can post a summary comment.",
        "human: The current system understanding reads clearly.",
    ]
