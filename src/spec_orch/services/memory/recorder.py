"""MemoryRecorder — structured write helpers for lifecycle events.

Extracted from MemoryService.  Provides convenience methods that
build well-formed :class:`MemoryEntry` objects and store them via
the provider.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from spec_orch.services.memory.types import MemoryEntry, MemoryLayer

if TYPE_CHECKING:
    from spec_orch.services.memory.protocol import MemoryProvider


class MemoryRecorder:
    """Write-side helpers that create domain-specific memory entries."""

    def __init__(self, provider: MemoryProvider) -> None:
        self._provider = provider

    def consolidate_run(
        self,
        *,
        run_id: str,
        issue_id: str,
        succeeded: bool,
        failed_conditions: list[str] | None = None,
        key_learnings: str = "",
        builder_adapter: str | None = None,
        verification_passed: bool | None = None,
    ) -> str | None:
        """Store a run outcome summary in semantic memory for cross-run learning."""
        outcome = "succeeded" if succeeded else "failed"
        content = f"Run {run_id} for {issue_id}: {outcome}"
        if builder_adapter:
            content += f"\nBuilder: {builder_adapter}"
        if verification_passed is not None:
            content += f"\nVerification: {'passed' if verification_passed else 'failed'}"
        if key_learnings:
            content += f"\n{key_learnings}"

        meta: dict[str, Any] = {
            "run_id": run_id,
            "issue_id": issue_id,
            "succeeded": succeeded,
            "failed_conditions": failed_conditions or [],
            "entity_scope": "issue",
            "entity_id": issue_id,
            "relation_type": "summarize",
            "source_run_id": run_id,
        }
        if builder_adapter:
            meta["builder_adapter"] = builder_adapter
        if verification_passed is not None:
            meta["verification_passed"] = verification_passed

        entry = MemoryEntry(
            key=f"run-summary-{run_id}",
            content=content,
            layer=MemoryLayer.SEMANTIC,
            tags=["run-summary", "auto-consolidated"],
            metadata=meta,
        )
        return self._provider.store(entry)

    def record_builder_telemetry(
        self,
        *,
        run_id: str,
        issue_id: str,
        tool_sequence: list[str],
        lines_scanned: int = 0,
        source_path: str = "",
    ) -> str | None:
        """Store builder tool-call telemetry in episodic memory."""
        if not tool_sequence:
            return None
        content = (
            f"Builder telemetry for run {run_id} (issue {issue_id}):\n"
            f"Tool sequence ({len(tool_sequence)} calls): " + " → ".join(tool_sequence[:50])
        )
        entry = MemoryEntry(
            key=f"builder-telemetry-{run_id}",
            content=content,
            layer=MemoryLayer.EPISODIC,
            tags=["builder-telemetry", f"issue:{issue_id}", f"run:{run_id}"],
            metadata={
                "run_id": run_id,
                "issue_id": issue_id,
                "tool_sequence": tool_sequence[:100],
                "tool_count": len(tool_sequence),
                "lines_scanned": lines_scanned,
                "source_path": source_path,
                "entity_scope": "issue",
                "entity_id": issue_id,
                "relation_type": "observed",
                "source_run_id": run_id,
            },
        )
        return self._provider.store(entry)

    def record_acceptance(
        self,
        *,
        issue_id: str,
        accepted_by: str,
        run_id: str = "",
    ) -> str:
        """Store human acceptance feedback in episodic memory."""
        content = f"Issue {issue_id} accepted by {accepted_by}." + (
            f" Run: {run_id}" if run_id else ""
        )
        entry = MemoryEntry(
            key=f"acceptance-{issue_id}",
            content=content,
            layer=MemoryLayer.EPISODIC,
            tags=["acceptance", f"issue:{issue_id}", "human-feedback"],
            metadata={
                "issue_id": issue_id,
                "accepted_by": accepted_by,
                "run_id": run_id,
                "entity_scope": "issue",
                "entity_id": issue_id,
                "relation_type": "observed",
                "source_run_id": run_id,
            },
        )
        return self._provider.store(entry)

    def record_mission_event(
        self,
        mission_id: str,
        phase: str,
        *,
        detail: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Write a mission lifecycle event to episodic memory."""
        content = f"# Mission {mission_id} — {phase}"
        if detail:
            content += f"\n\n{detail}"
        entry = MemoryEntry(
            key=f"mission-event-{mission_id}-{phase}",
            content=content,
            layer=MemoryLayer.EPISODIC,
            tags=["mission-event", f"mission:{mission_id}", phase],
            metadata={
                "mission_id": mission_id,
                "phase": phase,
                "entity_scope": "mission",
                "entity_id": mission_id,
                "relation_type": "observed",
                **(metadata or {}),
            },
        )
        return self._provider.store(entry)

    def record_issue_completion(
        self,
        issue_id: str,
        *,
        succeeded: bool,
        summary: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Write an issue completion event to episodic memory."""
        status = "succeeded" if succeeded else "failed"
        content = f"# Issue {issue_id} — {status}"
        if summary:
            content += f"\n\n{summary}"
        entry = MemoryEntry(
            key=f"issue-result-{issue_id}",
            content=content,
            layer=MemoryLayer.EPISODIC,
            tags=["issue-result", f"issue:{issue_id}", status],
            metadata={
                "issue_id": issue_id,
                "succeeded": succeeded,
                "entity_scope": "issue",
                "entity_id": issue_id,
                "relation_type": "observed",
                **(metadata or {}),
            },
        )
        return self._provider.store(entry)

    def record_gate_result(self, payload: dict[str, Any]) -> str:
        """Write a gate verdict to episodic memory."""
        issue_id = payload.get("issue_id", "unknown")
        passed = payload.get("passed", False)
        return self._provider.store(
            MemoryEntry(
                key=f"gate-verdict-{issue_id}-{int(time.time() * 1000)}",
                content=f"Gate {'passed' if passed else 'failed'}",
                layer=MemoryLayer.EPISODIC,
                tags=[
                    "gate-verdict",
                    f"issue:{issue_id}",
                    "gate-passed" if passed else "gate-failed",
                ],
                metadata=payload,
            )
        )

    def record_conductor_event(self, payload: dict[str, Any]) -> str:
        """Write a conductor fork/intent event to episodic memory."""
        action = payload.get("action", "")
        thread_id = payload.get("thread_id", "unknown")

        if action == "fork":
            return self._provider.store(
                MemoryEntry(
                    key=f"conductor-fork-{thread_id}-{payload.get('linear_issue_id', '')}",
                    content=f"Fork: {payload.get('title', '')}",
                    layer=MemoryLayer.EPISODIC,
                    tags=["conductor-fork", f"thread:{thread_id}"],
                    metadata=payload,
                )
            )
        intent_cat = payload.get("intent_category", "")
        return self._provider.store(
            MemoryEntry(
                key=f"intent-classified-{thread_id}-{payload.get('message_id', '')}",
                content=payload.get("summary", ""),
                layer=MemoryLayer.EPISODIC,
                tags=["intent-classified", f"thread:{thread_id}", f"intent:{intent_cat}"],
                metadata=payload,
            )
        )
