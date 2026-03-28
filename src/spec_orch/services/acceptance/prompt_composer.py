"""Compose mode-aware acceptance evaluator prompts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from spec_orch.domain.models import AcceptanceCampaign, AcceptanceMode, BuilderResult, WorkPacket

_MODE_GUIDANCE: dict[AcceptanceMode, str] = {
    AcceptanceMode.FEATURE_SCOPED: (
        "Verify only the declared feature and its immediately adjacent states. "
        "Do not broaden into unrelated product critique."
    ),
    AcceptanceMode.IMPACT_SWEEP: (
        "Validate the target feature and sweep neighboring routes for regressions or "
        "cross-surface breakage caused by the change."
    ),
    AcceptanceMode.EXPLORATORY: (
        "Act as an independent operator using the product to complete the intended task. "
        "Do not assume the mission framing or UI structure is correct."
    ),
}

_MODE_RUBRIC: dict[AcceptanceMode, list[str]] = {
    AcceptanceMode.FEATURE_SCOPED: [
        "Treat the declared feature boundary as the primary contract for this review.",
        "Favor concrete in-scope regressions over broad product critique.",
        "Reject the run if the declared feature flow fails, even when unrelated routes look fine.",
    ],
    AcceptanceMode.IMPACT_SWEEP: [
        "Treat the target change as suspicious and actively look for adjacent regressions.",
        (
            "Prefer findings that connect the changed flow to neighboring route "
            "breakage or state drift."
        ),
        (
            "Downgrade confidence when coverage misses routes needed to confirm or "
            "falsify a regression."
        ),
    ],
    AcceptanceMode.EXPLORATORY: [
        "Treat the current implementation and mission framing as falsifiable.",
        "Judge the product from an operator's task perspective, not from implementation intent.",
        "Separate materially broken flows from taste-level UX criticism.",
    ],
}

_FILING_POLICY_GUIDANCE: dict[str, list[str]] = {
    "in_scope_only": [
        "Only propose auto-file issues for in-scope regressions.",
        "If a route is outside the declared campaign, mention it as observation only.",
        "If coverage is missing or partial, lower confidence and explain the gap.",
    ],
    "auto_file_regressions_only": [
        "Only propose auto-file issues for evidence-backed regressions or broken task flows.",
        "Do not auto-file speculative polish concerns.",
        "If coverage is missing or partial, lower confidence and explain the gap.",
    ],
    "hold_ux_concerns_for_operator_review": [
        "Do not auto-file broad UX criticism unless the flow is materially broken.",
        "Prefer operator-review language for confusing but non-blocking UX issues.",
        (
            "Only escalate automatically when the issue is clearly broken, blocking, "
            "or safety-critical."
        ),
    ],
    "auto_file_broken_flows_only": [
        "Do not auto-file broad UX criticism unless the flow is materially broken.",
        (
            "Use issue proposals for clearly broken or blocked operator flows, not "
            "for polish-only feedback."
        ),
        "Prefer operator-review language for confusing but non-blocking UX issues.",
    ],
}


def compose_acceptance_prompt(
    *,
    mission_id: str,
    round_id: int,
    round_dir: Path,
    worker_results: list[tuple[WorkPacket, BuilderResult]],
    artifacts: dict[str, Any],
    repo_root: Path,
    campaign: AcceptanceCampaign | None = None,
) -> str:
    active_campaign = campaign or AcceptanceCampaign(
        mode=AcceptanceMode.EXPLORATORY,
        goal="Evaluate the round output from a user-facing acceptance perspective.",
    )
    payload = {
        "mission_id": mission_id,
        "round_id": round_id,
        "round_dir": str(round_dir),
        "repo_root": str(repo_root),
        "campaign": active_campaign.to_dict(),
        "worker_results": [
            {
                "packet_id": packet.packet_id,
                "title": packet.title,
                "succeeded": result.succeeded,
                "report_path": str(result.report_path),
                "adapter": result.adapter,
                "agent": result.agent,
            }
            for packet, result in worker_results
        ],
        "artifacts": artifacts,
    }
    guidance = _MODE_GUIDANCE[active_campaign.mode]
    rubric = "\n".join(f"- {line}" for line in _MODE_RUBRIC[active_campaign.mode])
    filing_policy_lines = _FILING_POLICY_GUIDANCE.get(
        active_campaign.filing_policy,
        [
            "Use evidence-backed issue proposals only.",
            "Explain when filing should be deferred because the evidence is incomplete.",
        ],
    )
    filing_policy_guidance = "\n".join(f"- {line}" for line in filing_policy_lines)
    return (
        "## Acceptance Mode\n"
        f"Mode: {active_campaign.mode.value}\n"
        f"Goal: {active_campaign.goal}\n"
        f"Guidance: {guidance}\n\n"
        "## Adversarial Rubric\n"
        f"{rubric}\n\n"
        "## Evaluation Instructions\n"
        "- Use the campaign to determine intended coverage boundaries.\n"
        "- Follow the interaction plan for each route when one is provided.\n"
        "- Prefer evidence-backed findings over speculative critique.\n"
        "- Report missing coverage explicitly when expected routes were not tested.\n"
        "- Recommend the next validation step when the current evidence is insufficient.\n\n"
        "## Coverage Budget\n"
        f"- Minimum primary routes to cover: {active_campaign.min_primary_routes}\n"
        f"- Related route budget: {active_campaign.related_route_budget}\n"
        f"- Interaction budget: {active_campaign.interaction_budget or 'none'}\n"
        f"- Required interactions: {', '.join(active_campaign.required_interactions) or 'none'}\n\n"
        "## Filing Policy\n"
        f"- Policy: {active_campaign.filing_policy or 'unspecified'}\n"
        f"{filing_policy_guidance}\n\n"
        "## Evidence Payload\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )
