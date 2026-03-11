from __future__ import annotations

from pathlib import Path

from spec_orch.services.plan_parser import _heading_matches, parse_plan


def _write_plan(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "plan.md"
    path.write_text(content.strip() + "\n", encoding="utf-8")
    return path


def test_parse_extracts_title_from_h1(tmp_path: Path) -> None:
    plan_path = _write_plan(
        tmp_path,
        """
        # Build plan-to-spec

        Intro paragraph.
        """,
    )

    plan = parse_plan(plan_path)

    assert plan.title == "Build plan-to-spec"


def test_parse_extracts_summary_from_background_section(tmp_path: Path) -> None:
    plan_path = _write_plan(
        tmp_path,
        """
        # Build plan-to-spec

        ## Background

        This summary should win.

        Another paragraph should not.
        """,
    )

    plan = parse_plan(plan_path)

    assert plan.summary == "This summary should win."


def test_parse_extracts_summary_from_overview_section(tmp_path: Path) -> None:
    plan_path = _write_plan(
        tmp_path,
        """
        # Build plan-to-spec

        ## Overview

        This overview becomes the summary.
        """,
    )

    plan = parse_plan(plan_path)

    assert plan.summary == "This overview becomes the summary."


def test_parse_falls_back_to_first_paragraph_for_summary(tmp_path: Path) -> None:
    plan_path = _write_plan(
        tmp_path,
        """
        # Build plan-to-spec

        This first paragraph becomes the fallback summary.

        ## Implementation
        - Create `src/spec_orch/services/plan_parser.py` for parsing.
        """,
    )

    plan = parse_plan(plan_path)

    assert plan.summary == "This first paragraph becomes the fallback summary."


def test_parse_extracts_file_changes_bullets(tmp_path: Path) -> None:
    plan_path = _write_plan(
        tmp_path,
        """
        # Build plan-to-spec

        ## Files to Create/Modify
        - Create `src/spec_orch/services/plan_parser.py` with parsing logic.
        * Modify `src/spec_orch/cli.py` to expose the command.
        """,
    )

    plan = parse_plan(plan_path)

    assert plan.file_changes == [
        "Create `src/spec_orch/services/plan_parser.py` with parsing logic.",
        "Modify `src/spec_orch/cli.py` to expose the command.",
    ]


def test_parse_extracts_acceptance_criteria(tmp_path: Path) -> None:
    plan_path = _write_plan(
        tmp_path,
        """
        # Build plan-to-spec

        ## Acceptance Criteria
        - Command writes a fixture JSON file.
        - Output contains acceptance criteria.
        """,
    )

    plan = parse_plan(plan_path)

    assert plan.acceptance_criteria == [
        "Command writes a fixture JSON file.",
        "Output contains acceptance criteria.",
    ]


def test_parse_extracts_constraints_from_not_doing(tmp_path: Path) -> None:
    plan_path = _write_plan(
        tmp_path,
        """
        # Build plan-to-spec

        ## Not Doing
        - No LLM calls.
        - No extra CLI flags.
        """,
    )

    plan = parse_plan(plan_path)

    assert plan.constraints == ["No LLM calls.", "No extra CLI flags."]


def test_parse_extracts_architecture_notes(tmp_path: Path) -> None:
    plan_path = _write_plan(
        tmp_path,
        """
        # Build plan-to-spec

        ## Design
        Keep parsing template-based.

        Prefer lazy imports in the CLI.

        ## Acceptance Criteria
        - It works.
        """,
    )

    plan = parse_plan(plan_path)

    assert plan.architecture_notes == (
        "Keep parsing template-based.\n\nPrefer lazy imports in the CLI."
    )


def test_parse_extracts_file_paths_from_backticks(tmp_path: Path) -> None:
    plan_path = _write_plan(
        tmp_path,
        """
        # Build plan-to-spec

        Read `src/spec_orch/cli.py`, `src/spec_orch/services/plan_parser.py`,
        `docs/plans/example.md`, and `config/spec-orch.toml`.
        Ignore `README` and `folder/without_extension`.
        Mention `src/spec_orch/cli.py` again for dedupe.
        """,
    )

    plan = parse_plan(plan_path)

    assert plan.files_to_read == [
        "config/spec-orch.toml",
        "docs/plans/example.md",
        "src/spec_orch/cli.py",
        "src/spec_orch/services/plan_parser.py",
    ]


def test_parse_handles_empty_document(tmp_path: Path) -> None:
    plan = parse_plan(_write_plan(tmp_path, ""))

    assert plan.title == ""
    assert plan.summary == ""
    assert plan.file_changes == []
    assert plan.acceptance_criteria == []
    assert plan.constraints == []
    assert plan.architecture_notes == ""
    assert plan.files_to_read == []


def test_parse_summary_stops_at_next_heading_for_empty_section(tmp_path: Path) -> None:
    plan_path = _write_plan(
        tmp_path,
        """
        # Build plan-to-spec

        ## Background

        ## File Changes
        - Create `src/spec_orch/services/plan_parser.py` with parsing logic.
        """,
    )

    plan = parse_plan(plan_path)

    assert plan.summary == ""


def test_heading_match_does_not_false_positive_on_substring() -> None:
    assert _heading_matches("Redesigned", ["design"]) is False
