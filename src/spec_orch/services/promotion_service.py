"""Promote an ExecutionPlan to Linear — create issues from WorkPackets."""

from __future__ import annotations

import json
from pathlib import Path

from spec_orch.domain.models import ExecutionPlan, PlanStatus, Wave, WorkPacket


class PromotionService:
    """Creates Linear issues from an approved ExecutionPlan."""

    def __init__(self, *, linear_client: object | None = None) -> None:
        self._client = linear_client

    def promote(
        self,
        plan: ExecutionPlan,
        *,
        team_key: str = "SON",
    ) -> ExecutionPlan:
        """Create a Linear issue for each WorkPacket in the plan.

        If no Linear client is configured, issues are stubbed locally.
        Returns the plan with ``linear_issue_id`` filled in on each packet.
        """
        if self._client is None:
            return self._promote_local(plan)

        return self._promote_to_linear(plan, team_key=team_key)

    def _promote_local(self, plan: ExecutionPlan) -> ExecutionPlan:
        """Stub promotion without Linear — assign local issue IDs."""
        counter = 1
        for wave in plan.waves:
            for packet in wave.work_packets:
                packet.linear_issue_id = (
                    f"LOCAL-{plan.mission_id.upper()}-{counter}"
                )
                counter += 1
        plan.status = PlanStatus.EXECUTING
        return plan

    def _promote_to_linear(
        self, plan: ExecutionPlan, *, team_key: str,
    ) -> ExecutionPlan:
        """Create real Linear issues via the API."""
        from spec_orch.services.linear_client import LinearClient

        client: LinearClient = self._client  # type: ignore[assignment]

        for wave in plan.waves:
            for packet in wave.work_packets:
                description = self._build_issue_description(
                    packet, plan.mission_id, wave,
                )
                issue_data = client.create_issue(
                    team_key=team_key,
                    title=f"[W{wave.wave_number}] {packet.title}",
                    description=description,
                )
                packet.linear_issue_id = issue_data.get(
                    "identifier", issue_data.get("id", ""),
                )

        plan.status = PlanStatus.EXECUTING
        return plan

    @staticmethod
    def _build_issue_description(
        packet: WorkPacket,
        mission_id: str,
        wave: Wave,
    ) -> str:
        lines = [
            f"**Mission**: `{mission_id}`",
            f"**Wave**: {wave.wave_number} — {wave.description}",
            f"**Run Class**: {packet.run_class}",
            f"**Spec Section**: {packet.spec_section}",
            "",
            "## Builder Prompt",
            "",
            packet.builder_prompt,
            "",
            "## Acceptance Criteria",
            "",
        ]
        for c in packet.acceptance_criteria:
            lines.append(f"- {c}")
        if packet.files_in_scope:
            lines.extend(["", "## Context", "", "Files in scope:"])
            for f in packet.files_in_scope:
                lines.append(f"- {f}")
        if packet.files_out_of_scope:
            lines.append("\nFiles out of scope:")
            for f in packet.files_out_of_scope:
                lines.append(f"- {f}")
        if packet.depends_on:
            lines.extend([
                "",
                f"**Depends on**: {', '.join(packet.depends_on)}",
            ])
        return "\n".join(lines)


def save_plan(plan: ExecutionPlan, path: Path) -> None:
    """Persist an ExecutionPlan as JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)

    def _packet_dict(p: WorkPacket) -> dict:
        return {
            "packet_id": p.packet_id,
            "title": p.title,
            "spec_section": p.spec_section,
            "run_class": p.run_class,
            "files_in_scope": p.files_in_scope,
            "files_out_of_scope": p.files_out_of_scope,
            "depends_on": p.depends_on,
            "acceptance_criteria": p.acceptance_criteria,
            "builder_prompt": p.builder_prompt,
            "linear_issue_id": p.linear_issue_id,
        }

    data = {
        "plan_id": plan.plan_id,
        "mission_id": plan.mission_id,
        "status": plan.status.value,
        "waves": [
            {
                "wave_number": w.wave_number,
                "description": w.description,
                "work_packets": [_packet_dict(p) for p in w.work_packets],
            }
            for w in plan.waves
        ],
    }
    path.write_text(json.dumps(data, indent=2) + "\n")


def load_plan(path: Path) -> ExecutionPlan:
    """Load an ExecutionPlan from JSON."""
    data = json.loads(path.read_text())
    waves = []
    for w in data["waves"]:
        packets = [WorkPacket(**p) for p in w["work_packets"]]
        waves.append(Wave(
            wave_number=w["wave_number"],
            description=w.get("description", ""),
            work_packets=packets,
        ))
    return ExecutionPlan(
        plan_id=data["plan_id"],
        mission_id=data["mission_id"],
        waves=waves,
        status=PlanStatus(data.get("status", "draft")),
    )
