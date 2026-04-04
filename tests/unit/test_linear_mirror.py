from __future__ import annotations

from spec_orch.domain.intake_models import CanonicalAcceptance, CanonicalIssue
from spec_orch.services.intake_handoff import build_workspace_handoff
from spec_orch.services.linear_mirror import (
    build_linear_mirror_document,
    build_linear_mirror_document_from_workspace,
    merge_linear_mirror_section,
    parse_linear_mirror_section,
    render_linear_mirror_section,
)


def _canonical_issue() -> CanonicalIssue:
    return CanonicalIssue(
        issue_id="SON-999",
        title="Self-hosting Linear sync",
        problem="Linear should reflect real spec-orch state.",
        goal="Mirror intake, handoff, and plan summary into the issue.",
        constraints=["Keep the current intake contract readable."],
        acceptance=CanonicalAcceptance(
            success_conditions=["Linear shows the current next action."],
            verification_expectations=["Mirror block stays parse-safe."],
        ),
        evidence_expectations=["structured mirror block"],
        open_questions=[],
        current_plan_hint="Mirror tranche 1 focuses on status and plan summary.",
        origin="linear",
        source_refs=[{"kind": "linear_issue", "ref": "SON-999"}],
    )


def test_render_linear_mirror_section_round_trips_json_payload() -> None:
    canonical = _canonical_issue()
    handoff = build_workspace_handoff(canonical)
    mirror = build_linear_mirror_document(
        intake_state="ready_for_workspace",
        canonical=canonical,
        handoff=handoff,
        plan_summary=[
            "Phase 1 complete: context and governance hardened.",
            "Phase 2 in progress: sync Linear and chat-to-issue.",
        ],
    )

    rendered = render_linear_mirror_section(mirror)
    reparsed = parse_linear_mirror_section(rendered)

    assert "## SpecOrch Mirror" in rendered
    assert reparsed is not None
    assert reparsed["intake_state"] == "ready_for_workspace"
    assert reparsed["workspace_id"] == handoff["workspace_id"]
    assert reparsed["plan_summary"] == [
        "Phase 1 complete: context and governance hardened.",
        "Phase 2 in progress: sync Linear and chat-to-issue.",
    ]


def test_merge_linear_mirror_section_replaces_existing_payload() -> None:
    canonical = _canonical_issue()
    handoff = build_workspace_handoff(canonical)
    old = build_linear_mirror_document(
        intake_state="clarifying",
        canonical=canonical,
        handoff=handoff,
        plan_summary=["Old summary"],
    )
    new = build_linear_mirror_document(
        intake_state="ready_for_workspace",
        canonical=canonical,
        handoff=handoff,
        plan_summary=["New summary"],
    )
    description = "## Problem\n\nNeed a mirror.\n\n" + render_linear_mirror_section(old) + "\n"

    merged = merge_linear_mirror_section(description, new)

    assert merged.count("## SpecOrch Mirror") == 1
    reparsed = parse_linear_mirror_section(merged)
    assert reparsed is not None
    assert reparsed["intake_state"] == "ready_for_workspace"
    assert reparsed["plan_summary"] == ["New summary"]


def test_merge_linear_mirror_section_preserves_backslashes_in_json_payload() -> None:
    description = render_linear_mirror_section(
        {
            "launcher_path": r"C:\repo\spec-orch",
            "pattern": r"\d+\w+",
        }
    )

    merged = merge_linear_mirror_section(
        description,
        {
            "launcher_path": r"C:\repo\spec-orch",
            "pattern": r"\d+\w+",
        },
    )

    assert r"C:\\repo\\spec-orch" in merged
    assert r"\\d+\\w+" in merged


def test_build_linear_mirror_document_from_workspace_derives_compact_plan_summary() -> None:
    workspace = {
        "state": "ready_for_workspace",
        "readiness": {
            "is_ready": True,
            "recommendation": "create_workspace",
            "missing_fields": [],
        },
        "handoff": {
            "state": "ready_for_workspace",
            "workspace_id": "workspace:SON-999",
            "next_action": "create_workspace",
            "blockers": [],
        },
        "canonical_issue": {
            "source_refs": [{"kind": "linear_issue", "ref": "SON-999"}],
        },
    }

    mirror = build_linear_mirror_document_from_workspace(workspace)

    assert mirror["next_action"] == "create_workspace"
    assert mirror["workspace_id"] == "workspace:SON-999"
    assert mirror["plan_summary"] == [
        "Readiness is green for workspace creation.",
        "Current recommendation: create_workspace.",
        "Handoff state: ready_for_workspace.",
    ]


def test_build_linear_mirror_document_from_workspace_tolerates_malformed_sections() -> None:
    mirror = build_linear_mirror_document_from_workspace(
        {
            "state": "clarifying",
            "readiness": [],
            "handoff": {"state": "blocked", "blockers": ["missing details"]},
            "canonical_issue": [],
        }
    )

    assert mirror["intake_state"] == "clarifying"
    assert mirror["next_action"] == "resolve_blockers"
    assert mirror["source_refs"] == []
    assert mirror["blockers"] == ["missing details"]
