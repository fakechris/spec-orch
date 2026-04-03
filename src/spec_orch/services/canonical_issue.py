from __future__ import annotations

from typing import Any

from spec_orch.domain.intake_models import CanonicalAcceptance, CanonicalIssue
from spec_orch.domain.models import Issue, IssueContext
from spec_orch.services.linear_intake import LinearIntakeDocument


def canonical_issue_from_linear_intake(
    *,
    issue_id: str,
    title: str,
    intake: LinearIntakeDocument,
) -> CanonicalIssue:
    return CanonicalIssue(
        issue_id=issue_id,
        title=title,
        problem=intake.problem,
        goal=intake.goal,
        constraints=list(intake.constraints),
        acceptance=CanonicalAcceptance(
            success_conditions=list(intake.acceptance.success_conditions),
            failure_conditions=list(intake.acceptance.failure_conditions),
            verification_expectations=list(intake.acceptance.verification_expectations),
            human_judgment_required=list(intake.acceptance.human_judgment_required),
            priority_routes_or_surfaces=list(intake.acceptance.priority_routes_or_surfaces),
        ),
        evidence_expectations=list(intake.evidence_expectations),
        open_questions=list(intake.open_questions),
        current_plan_hint=intake.current_system_understanding,
        origin="linear",
        source_refs=[{"kind": "linear_issue", "ref": issue_id}],
    )


def canonical_issue_from_dashboard_payload(
    *,
    issue_id: str,
    title: str,
    payload: dict[str, Any],
) -> CanonicalIssue:
    evidence_expectations = _normalize_lines(payload.get("evidence_expectations", []))
    verification_expectations = _normalize_lines(payload.get("verification_expectations", []))
    if not verification_expectations:
        verification_expectations = list(evidence_expectations)
    return CanonicalIssue(
        issue_id=issue_id,
        title=title,
        problem=str(payload.get("problem", "")).strip(),
        goal=str(payload.get("goal", "")).strip(),
        constraints=_normalize_lines(payload.get("constraints", [])),
        acceptance=CanonicalAcceptance(
            success_conditions=_normalize_lines(payload.get("acceptance_criteria", [])),
            failure_conditions=_normalize_lines(payload.get("failure_conditions", [])),
            verification_expectations=verification_expectations,
            human_judgment_required=_normalize_lines(payload.get("human_judgment_required", [])),
            priority_routes_or_surfaces=_normalize_lines(
                payload.get("priority_routes_or_surfaces", [])
            ),
        ),
        evidence_expectations=evidence_expectations,
        open_questions=_normalize_lines(payload.get("open_questions", [])),
        current_plan_hint=str(payload.get("current_system_understanding", "")).strip()
        or str(payload.get("intent", "")).strip(),
        origin="dashboard",
        source_refs=[{"kind": "dashboard_draft", "ref": issue_id}],
    )


def legacy_issue_from_canonical(
    canonical: CanonicalIssue,
    *,
    default_verification_commands: dict[str, list[str]] | None = None,
) -> Issue:
    builder_parts = [part for part in (canonical.goal, canonical.current_plan_hint) if part]
    acceptance_criteria: list[str] = []
    acceptance_criteria.extend(
        f"success: {item}" for item in canonical.acceptance.success_conditions
    )
    acceptance_criteria.extend(
        f"verify: {item}" for item in canonical.acceptance.verification_expectations
    )
    acceptance_criteria.extend(
        f"human: {item}" for item in canonical.acceptance.human_judgment_required
    )
    return Issue(
        issue_id=canonical.issue_id,
        title=canonical.title,
        summary=canonical.problem[:200],
        builder_prompt="\n\n".join(builder_parts) if builder_parts else None,
        verification_commands=default_verification_commands or {},
        context=IssueContext(constraints=list(canonical.constraints)),
        acceptance_criteria=acceptance_criteria,
    )


def _normalize_lines(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    return [str(item).strip() for item in items if str(item).strip()]
