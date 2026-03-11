from __future__ import annotations

from spec_orch.services.plan_parser import PlanData
from spec_orch.services.spec_generator import (
    _instruction_from_change,
    generate_builder_prompt,
    generate_fixture,
)


def test_generate_fixture_produces_valid_schema() -> None:
    plan = PlanData(
        title="Build plan-to-spec",
        summary="Convert markdown plans into issue fixtures.",
        file_changes=["Create `src/spec_orch/services/plan_parser.py` with parsing logic."],
        acceptance_criteria=["Fixture JSON is written."],
        constraints=["No LLM calls."],
        architecture_notes="Keep parsing deterministic.",
        files_to_read=["src/spec_orch/cli.py"],
    )

    fixture = generate_fixture(plan, "SPC-123")

    assert fixture == {
        "issue_id": "SPC-123",
        "title": "Build plan-to-spec",
        "summary": "Convert markdown plans into issue fixtures.",
        "builder_prompt": generate_builder_prompt(plan),
        "verification_commands": {
            "lint": ["{python}", "-m", "ruff", "check", "src/"],
            "typecheck": ["{python}", "-m", "mypy", "src/"],
            "test": ["{python}", "-m", "pytest", "tests/", "-q"],
            "build": ["{python}", "-c", "print('build ok')"],
        },
        "acceptance_criteria": ["Fixture JSON is written."],
        "context": {
            "files_to_read": ["src/spec_orch/cli.py"],
            "architecture_notes": "Keep parsing deterministic.",
            "constraints": ["No LLM calls."],
        },
    }


def test_generate_builder_prompt_numbers_steps() -> None:
    prompt = generate_builder_prompt(
        PlanData(file_changes=["Do the first thing.", "Do the second thing."])
    )

    assert "1. Do the first thing." in prompt
    assert "2. Do the second thing." in prompt


def test_generate_builder_prompt_appends_lint_suffix() -> None:
    prompt = generate_builder_prompt(PlanData(file_changes=["Do the thing."]))

    assert "Run ruff check src/ and fix any lint errors." in prompt
    assert "Run pytest tests/ -q to make sure nothing is broken." in prompt


def test_generate_builder_prompt_suffix_is_numbered() -> None:
    prompt = generate_builder_prompt(PlanData(file_changes=["Do the thing."]))

    assert "2. Run ruff check src/ and fix any lint errors." in prompt
    assert "3. Run pytest tests/ -q to make sure nothing is broken." in prompt


def test_generate_fixture_with_empty_plan() -> None:
    fixture = generate_fixture(PlanData(), "SPC-EMPTY")

    assert fixture["issue_id"] == "SPC-EMPTY"
    assert fixture["title"] == ""
    assert fixture["summary"] == ""
    assert fixture["acceptance_criteria"] == []
    assert fixture["context"] == {
        "files_to_read": [],
        "architecture_notes": "",
        "constraints": [],
    }


def test_generate_builder_prompt_converts_new_file_instructions() -> None:
    prompt = generate_builder_prompt(
        PlanData(
            file_changes=[
                "Create `src/spec_orch/services/plan_parser.py` with parsing logic."
            ]
        )
    )

    assert (
        "1. Create `src/spec_orch/services/plan_parser.py` with parsing logic."
        in prompt
    )


def test_generate_builder_prompt_converts_modify_instructions() -> None:
    prompt = generate_builder_prompt(
        PlanData(
            file_changes=["Modify `src/spec_orch/cli.py` to add the plan-to-spec command."]
        )
    )

    assert "1. In `src/spec_orch/cli.py`, add the plan-to-spec command." in prompt


def test_instruction_from_change_does_not_rewrite_in_bullets() -> None:
    instruction = _instruction_from_change(
        "Add unit tests in `tests/test_x.py` for the parser."
    )

    assert instruction == "Add unit tests in `tests/test_x.py` for the parser."
