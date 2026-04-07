"""Pure-data plan-patch operations extracted from RoundOrchestrator."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from spec_orch.domain.models import (
    ExecutionPlan,
    PlanPatch,
    RoundAction,
    RoundSummary,
    WorkPacket,
)


class PlanPatchApplier:
    """Applies plan patches to an ExecutionPlan.

    All methods are stateless data transformations with no side effects.
    """

    def apply(
        self,
        plan: ExecutionPlan,
        *,
        current_wave_idx: int,
        patch: PlanPatch,
    ) -> ExecutionPlan:
        """Apply a single plan patch starting from *current_wave_idx*."""
        updated_waves = list(plan.waves)
        for wave_idx in range(current_wave_idx, len(updated_waves)):
            wave = updated_waves[wave_idx]
            packets: list[WorkPacket] = []
            for packet in wave.work_packets:
                if packet.packet_id in patch.removed_packet_ids:
                    continue
                patch_data = patch.modified_packets.get(packet.packet_id)
                if patch_data:
                    packet = replace(
                        packet,
                        title=patch_data.get("title", packet.title),
                        spec_section=patch_data.get("spec_section", packet.spec_section),
                        run_class=patch_data.get("run_class", packet.run_class),
                        files_in_scope=patch_data.get("files_in_scope", packet.files_in_scope),
                        files_out_of_scope=patch_data.get(
                            "files_out_of_scope", packet.files_out_of_scope
                        ),
                        depends_on=patch_data.get("depends_on", packet.depends_on),
                        acceptance_criteria=patch_data.get(
                            "acceptance_criteria", packet.acceptance_criteria
                        ),
                        verification_commands=patch_data.get(
                            "verification_commands", packet.verification_commands
                        ),
                        builder_prompt=patch_data.get("builder_prompt", packet.builder_prompt),
                    )
                packets.append(packet)
            updated_waves[wave_idx] = replace(wave, work_packets=packets)

        if patch.added_packets:
            target_wave_idx = min(current_wave_idx, len(updated_waves) - 1)
            if target_wave_idx >= 0:
                target_wave = updated_waves[target_wave_idx]
                added_packets = [
                    self.packet_from_patch(packet_data) for packet_data in patch.added_packets
                ]
                updated_waves[target_wave_idx] = replace(
                    target_wave,
                    work_packets=[*target_wave.work_packets, *added_packets],
                )

        return replace(plan, waves=updated_waves)

    @staticmethod
    def packet_from_patch(packet_data: dict[str, Any]) -> WorkPacket:
        """Build a WorkPacket from a patch dictionary."""
        return WorkPacket(
            packet_id=str(packet_data["packet_id"]),
            title=packet_data.get("title", str(packet_data["packet_id"])),
            spec_section=packet_data.get("spec_section", ""),
            run_class=packet_data.get("run_class", "feature"),
            files_in_scope=packet_data.get("files_in_scope", []),
            files_out_of_scope=packet_data.get("files_out_of_scope", []),
            depends_on=packet_data.get("depends_on", []),
            acceptance_criteria=packet_data.get("acceptance_criteria", []),
            verification_commands=packet_data.get("verification_commands", {}),
            builder_prompt=packet_data.get("builder_prompt", ""),
            linear_issue_id=packet_data.get("linear_issue_id"),
        )

    def replay_patches(
        self,
        plan: ExecutionPlan,
        round_history: list[RoundSummary],
    ) -> ExecutionPlan:
        """Replay all plan patches recorded in *round_history*."""
        updated_plan = plan
        for summary in round_history:
            decision = summary.decision
            if decision is None or decision.plan_patch is None:
                continue
            updated_plan = self.apply(
                updated_plan,
                current_wave_idx=summary.wave_id,
                patch=decision.plan_patch,
            )
        return updated_plan

    @staticmethod
    def determine_start_wave(plan: ExecutionPlan, round_history: list[RoundSummary]) -> int:
        """Return the wave index to resume from given prior history."""
        if not round_history:
            return 0
        last_round = round_history[-1]
        last_action = last_round.decision.action if last_round.decision else None
        if last_action is RoundAction.CONTINUE:
            return min(last_round.wave_id + 1, len(plan.waves))
        return min(last_round.wave_id, max(len(plan.waves) - 1, 0))
