from __future__ import annotations

from spec_orch.services.linear_intake import LinearAcceptanceDraft, LinearIntakeDocument


def test_canonical_issue_from_linear_intake_preserves_structured_acceptance() -> None:
    from spec_orch.services.canonical_issue import canonical_issue_from_linear_intake

    issue = canonical_issue_from_linear_intake(
        issue_id="SON-410",
        title="Canonical schema",
        intake=LinearIntakeDocument(
            problem="Operators need one stable intake shape.",
            goal="Normalize Linear-native intake before execution.",
            constraints=["Keep schema readable in UI."],
            acceptance=LinearAcceptanceDraft(
                success_conditions=["Schema is shared across intake entry points."],
                verification_expectations=["Linear intake maps into canonical issue."],
                human_judgment_required=["The schema still reads like operator language."],
            ),
            evidence_expectations=["canonical issue payload"],
            open_questions=["Should source refs include dashboard drafts?"],
            current_system_understanding="SON-410 locks the shared issue shape.",
        ),
    )

    assert issue.issue_id == "SON-410"
    assert issue.origin == "linear"
    assert issue.problem == "Operators need one stable intake shape."
    assert issue.acceptance.verification_expectations == [
        "Linear intake maps into canonical issue."
    ]
    assert issue.current_plan_hint == "SON-410 locks the shared issue shape."
    assert issue.source_refs[0]["kind"] == "linear_issue"


def test_legacy_issue_from_canonical_flattens_acceptance_for_current_runtime() -> None:
    from spec_orch.services.canonical_issue import (
        canonical_issue_from_dashboard_payload,
        legacy_issue_from_canonical,
    )

    canonical = canonical_issue_from_dashboard_payload(
        issue_id="dashboard-intake",
        title="Dashboard Intake",
        payload={
            "problem": "Operators need dashboard-native intake preview.",
            "goal": "Make dashboard intake emit the canonical issue schema.",
            "constraints": ["Keep handoff deterministic."],
            "acceptance_criteria": ["Canonical preview is visible."],
            "evidence_expectations": ["preview panel"],
            "open_questions": [],
            "current_system_understanding": "Launcher owns draft state before workspace creation.",
        },
    )

    legacy = legacy_issue_from_canonical(
        canonical,
        default_verification_commands={"smoke": ["pytest", "-q"]},
    )

    assert legacy.issue_id == "dashboard-intake"
    assert legacy.summary == "Operators need dashboard-native intake preview."
    assert legacy.context.constraints == ["Keep handoff deterministic."]
    assert legacy.acceptance_criteria == [
        "success: Canonical preview is visible.",
        "verify: preview panel",
    ]
    assert "Make dashboard intake emit the canonical issue schema." in (legacy.builder_prompt or "")
