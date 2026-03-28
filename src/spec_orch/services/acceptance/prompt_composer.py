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
    return (
        "## Acceptance Mode\n"
        f"Mode: {active_campaign.mode.value}\n"
        f"Goal: {active_campaign.goal}\n"
        f"Guidance: {guidance}\n\n"
        "## Evaluation Instructions\n"
        "- Use the campaign to determine intended coverage boundaries.\n"
        "- Prefer evidence-backed findings over speculative critique.\n"
        "- Report missing coverage explicitly when expected routes were not tested.\n"
        "- Recommend the next validation step when the current evidence is insufficient.\n\n"
        "## Evidence Payload\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )
