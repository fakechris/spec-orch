from __future__ import annotations

import json
import re
from typing import Any

from spec_orch.domain.intake_models import CanonicalIssue

_MIRROR_HEADING = "## SpecOrch Mirror"
_MIRROR_SECTION_RE = re.compile(
    rf"^{re.escape(_MIRROR_HEADING)}\s*\n(.*?)(?=^##\s|\Z)",
    re.MULTILINE | re.DOTALL,
)


def build_linear_mirror_document(
    *,
    intake_state: str,
    canonical: CanonicalIssue,
    handoff: dict[str, Any],
    plan_summary: list[str] | None = None,
) -> dict[str, Any]:
    blockers = handoff.get("blockers", [])
    handoff_state = str(handoff.get("state", "")).strip()
    return {
        "intake_state": intake_state,
        "handoff_state": handoff_state,
        "workspace_id": str(handoff.get("workspace_id", "")).strip(),
        "next_action": _derive_next_action(handoff),
        "blockers": [str(item).strip() for item in blockers if str(item).strip()],
        "plan_summary": _normalize_plan_summary(plan_summary),
        "source_refs": list(canonical.source_refs),
    }


def build_linear_mirror_document_from_workspace(
    workspace: dict[str, Any],
    *,
    plan_summary: list[str] | None = None,
) -> dict[str, Any]:
    handoff = workspace.get("handoff", {})
    readiness = workspace.get("readiness", {})
    canonical_issue = workspace.get("canonical_issue", {})
    source_refs = canonical_issue.get("source_refs", [])
    if not plan_summary:
        plan_summary = _default_plan_summary_from_workspace(workspace)
    safe_handoff = handoff if isinstance(handoff, dict) else {}
    return {
        "intake_state": str(workspace.get("state", "")).strip(),
        "handoff_state": str(safe_handoff.get("state", "")).strip(),
        "workspace_id": str(safe_handoff.get("workspace_id", "")).strip(),
        "next_action": str(
            safe_handoff.get("next_action", "") or readiness.get("recommendation", "")
        ).strip()
        or _derive_next_action(safe_handoff),
        "blockers": [
            str(item).strip() for item in safe_handoff.get("blockers", []) if str(item).strip()
        ],
        "plan_summary": _normalize_plan_summary(plan_summary),
        "source_refs": [
            item
            for item in source_refs
            if isinstance(item, dict)
            and str(item.get("kind", "")).strip()
            and str(item.get("ref", "")).strip()
        ],
    }


def render_linear_mirror_section(document: dict[str, Any]) -> str:
    payload = json.dumps(document, indent=2, sort_keys=True)
    return f"{_MIRROR_HEADING}\n\n```json\n{payload}\n```"


def parse_linear_mirror_section(text: str | None) -> dict[str, Any] | None:
    if not text:
        return None
    match = _MIRROR_SECTION_RE.search(text)
    if not match:
        return None
    body = match.group(1).strip()
    fenced = re.search(r"```json\s*(.*?)```", body, re.DOTALL)
    candidate = fenced.group(1).strip() if fenced else body
    if not candidate:
        return None
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def merge_linear_mirror_section(description: str, document: dict[str, Any]) -> str:
    rendered = render_linear_mirror_section(document).strip()
    base = description.rstrip()
    if _MIRROR_SECTION_RE.search(base):
        updated = _MIRROR_SECTION_RE.sub(f"{rendered}\n\n", base, count=1)
        return updated.rstrip() + "\n"
    if not base:
        return rendered + "\n"
    return base + "\n\n" + rendered + "\n"


def _derive_next_action(handoff: dict[str, Any]) -> str:
    explicit = str(handoff.get("next_action", "")).strip()
    if explicit:
        return explicit
    state = str(handoff.get("state", "")).strip()
    if state in {"ready_for_workspace", "workspace_created"}:
        return "create_workspace"
    if state == "blocked":
        return "resolve_blockers"
    if state:
        return state
    return "review_intake"


def _normalize_plan_summary(plan_summary: list[str] | None) -> list[str]:
    return [str(item).strip() for item in (plan_summary or []) if str(item).strip()]


def _default_plan_summary_from_workspace(workspace: dict[str, Any]) -> list[str]:
    readiness = workspace.get("readiness", {})
    handoff = workspace.get("handoff", {})
    items: list[str] = []
    if readiness.get("is_ready") is True:
        items.append("Readiness is green for workspace creation.")
    elif readiness.get("missing_fields"):
        missing = ", ".join(str(item).strip() for item in readiness.get("missing_fields", []))
        items.append(f"Readiness is waiting on: {missing}.")
    recommendation = str(readiness.get("recommendation", "")).strip()
    if recommendation:
        items.append(f"Current recommendation: {recommendation}.")
    handoff_state = str(handoff.get("state", "")).strip() if isinstance(handoff, dict) else ""
    if handoff_state:
        items.append(f"Handoff state: {handoff_state}.")
    return items
