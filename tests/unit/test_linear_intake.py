from __future__ import annotations

from spec_orch.services.linear_intake import (
    LinearAcceptanceDraft,
    LinearIntakeDocument,
    LinearIntakeState,
    derive_linear_intake_state,
    parse_linear_intake_description,
    render_linear_intake_description,
)

FULL_DESCRIPTION = """\
## Problem

Operators cannot tell whether a Linear-native intake item is ready to execute.

## Goal

Make readiness and acceptance authoring visible inside the Linear issue itself.

## Constraints

- Keep the final shared schema work for SON-410.
- Do not depend on dashboard-only state.

## Acceptance

### Success Conditions

- The issue exposes problem, goal, and acceptance clearly.

### Failure Conditions

- Operators still need a hidden planning document to understand readiness.

### Verification Expectations

- Readiness checks accept the intake shape.
- Linear writeback can render the current intake summary.

### Human Judgment Required

- The current system understanding reads clearly to operators.

### Priority Routes or Surfaces

- linear
- daemon triage

## Evidence Expectations

- latest intake summary comment
- readiness decision

## Open Questions

- [non_blocking] Should the dashboard mirror the same wording?

## Current System Understanding

Issue is ready for workspace handoff once acceptance and verification expectations are explicit.
"""


def test_parse_linear_intake_description_extracts_sections() -> None:
    document = parse_linear_intake_description(FULL_DESCRIPTION)

    assert document.problem.startswith("Operators cannot tell")
    assert document.goal.startswith("Make readiness")
    assert document.constraints == [
        "Keep the final shared schema work for SON-410.",
        "Do not depend on dashboard-only state.",
    ]
    assert document.acceptance.success_conditions == [
        "The issue exposes problem, goal, and acceptance clearly."
    ]
    assert document.acceptance.failure_conditions == [
        "Operators still need a hidden planning document to understand readiness."
    ]
    assert document.acceptance.verification_expectations == [
        "Readiness checks accept the intake shape.",
        "Linear writeback can render the current intake summary.",
    ]
    assert document.acceptance.human_judgment_required == [
        "The current system understanding reads clearly to operators."
    ]
    assert document.acceptance.priority_routes_or_surfaces == ["linear", "daemon triage"]
    assert document.evidence_expectations == ["latest intake summary comment", "readiness decision"]
    assert document.open_questions == [
        "[non_blocking] Should the dashboard mirror the same wording?"
    ]
    assert "workspace handoff" in document.current_system_understanding


def test_render_linear_intake_description_round_trips() -> None:
    original = LinearIntakeDocument(
        problem="Problem text",
        goal="Goal text",
        constraints=["Keep scope tiny."],
        acceptance=LinearAcceptanceDraft(
            success_conditions=["Visible success state."],
            failure_conditions=["Still ambiguous."],
            verification_expectations=["Run readiness checker."],
            human_judgment_required=["Operator confirms wording."],
            priority_routes_or_surfaces=["linear"],
        ),
        evidence_expectations=["summary comment"],
        open_questions=["[non_blocking] Future dashboard parity?"],
        current_system_understanding="Acceptance is explicit.",
    )

    rendered = render_linear_intake_description(original)
    reparsed = parse_linear_intake_description(rendered)

    assert reparsed == original


def test_derive_linear_intake_state_ready_for_workspace_when_acceptance_is_complete() -> None:
    document = parse_linear_intake_description(FULL_DESCRIPTION)

    assert derive_linear_intake_state(document) is LinearIntakeState.READY_FOR_WORKSPACE


def test_derive_linear_intake_state_clarifying_when_blocking_question_remains() -> None:
    document = parse_linear_intake_description(FULL_DESCRIPTION)
    document.open_questions = ["[blocking] Should this create a workspace or only rewrite Linear?"]

    assert derive_linear_intake_state(document) is LinearIntakeState.CLARIFYING


def test_derive_linear_intake_state_acceptance_drafting_when_acceptance_is_partial() -> None:
    document = LinearIntakeDocument(
        problem="Problem text",
        goal="Goal text",
        acceptance=LinearAcceptanceDraft(success_conditions=["State the intended result."]),
    )

    assert derive_linear_intake_state(document) is LinearIntakeState.ACCEPTANCE_DRAFTING
