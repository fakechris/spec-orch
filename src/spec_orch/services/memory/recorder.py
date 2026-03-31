"""MemoryRecorder — structured write helpers for lifecycle events.

Extracted from MemoryService.  Provides convenience methods that
build well-formed :class:`MemoryEntry` objects and store them via
the provider.
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any

from spec_orch.acceptance_core.models import AcceptanceJudgment, AcceptanceWorkflowState
from spec_orch.decision_core.models import DecisionRecord, DecisionReview
from spec_orch.domain.execution_semantics import ExecutionAttempt
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

    def record_execution_outcome(self, *, attempt: ExecutionAttempt) -> str:
        """Store one normalized execution attempt outcome in episodic memory."""
        provenance = (
            "reviewed"
            if attempt.outcome.review is not None or attempt.outcome.gate is not None
            else "unreviewed"
        )
        unit_kind = attempt.unit_kind.value
        owner_kind = attempt.owner_kind.value
        issue_id = attempt.unit_id if unit_kind == "issue" else ""
        mission_id = ""
        round_id: int | None = None
        if unit_kind == "work_packet" and attempt.workspace_root:
            workspace = str(attempt.workspace_root)
            if "/docs/specs/" in workspace and "/rounds/round-" in workspace:
                try:
                    mission_id = workspace.split("/docs/specs/", 1)[1].split("/", 1)[0]
                    round_str = workspace.rsplit("/round-", 1)[1].split("/", 1)[0]
                    round_id = int(round_str)
                except (IndexError, ValueError):
                    mission_id = ""
                    round_id = None

        summary = {
            "attempt_id": attempt.attempt_id,
            "unit_kind": unit_kind,
            "unit_id": attempt.unit_id,
            "owner_kind": owner_kind,
            "status": attempt.outcome.status.value,
            "provenance": provenance,
        }
        entry = MemoryEntry(
            key=f"execution-outcome-{attempt.attempt_id}",
            content=json.dumps(summary, ensure_ascii=False),
            layer=MemoryLayer.EPISODIC,
            tags=[
                "execution-outcome",
                f"unit:{unit_kind}",
                f"owner:{owner_kind}",
                f"status:{attempt.outcome.status.value}",
                f"provenance:{provenance}",
            ],
            metadata={
                "attempt_id": attempt.attempt_id,
                "unit_kind": unit_kind,
                "unit_id": attempt.unit_id,
                "owner_kind": owner_kind,
                "status": attempt.outcome.status.value,
                "provenance": provenance,
                "issue_id": issue_id,
                "mission_id": mission_id,
                "round_id": round_id,
                "entity_scope": "issue" if issue_id else "mission" if mission_id else unit_kind,
                "entity_id": issue_id or mission_id or attempt.unit_id,
                "relation_type": "observed",
            },
        )
        return self._provider.store(entry)

    def record_decision_record(
        self,
        *,
        record: DecisionRecord,
        mission_id: str,
        round_id: int | None = None,
    ) -> str:
        """Store one decision record in episodic memory."""
        entry = MemoryEntry(
            key=f"decision-record-{record.record_id}",
            content=record.summary,
            layer=MemoryLayer.EPISODIC,
            tags=[
                "decision-record",
                f"decision-point:{record.point_key}",
                f"owner:{record.owner}",
                "provenance:unreviewed",
            ],
            metadata={
                "record_id": record.record_id,
                "point_key": record.point_key,
                "authority": record.authority.value,
                "owner": record.owner,
                "selected_action": record.selected_action,
                "confidence": record.confidence,
                "provenance": "unreviewed",
                "mission_id": mission_id,
                "round_id": round_id,
                "entity_scope": "mission",
                "entity_id": mission_id,
                "relation_type": "observed",
            },
            created_at=record.created_at,
            updated_at=record.created_at,
        )
        return self._provider.store(entry)

    def record_decision_review(
        self,
        *,
        review: DecisionReview,
        mission_id: str,
        round_id: int | None = None,
        point_key: str = "",
        owner: str = "",
        selected_action: str = "",
    ) -> str:
        """Store one reviewed decision outcome in episodic memory."""
        entry = MemoryEntry(
            key=f"decision-review-{review.record_id}-{review.review_id}",
            content=review.summary,
            layer=MemoryLayer.EPISODIC,
            tags=[
                "decision-review",
                f"reviewer:{review.reviewer_kind}",
                f"verdict:{review.verdict}",
                "provenance:reviewed",
            ],
            metadata={
                "record_id": review.record_id,
                "review_id": review.review_id,
                "reviewer_kind": review.reviewer_kind,
                "verdict": review.verdict,
                "recommended_authority": (
                    review.recommended_authority.value
                    if review.recommended_authority is not None
                    else None
                ),
                "escalate_to_human": review.escalate_to_human,
                "reflection": review.reflection,
                "point_key": point_key,
                "owner": owner,
                "selected_action": selected_action,
                "provenance": "reviewed",
                "mission_id": mission_id,
                "round_id": round_id,
                "entity_scope": "mission",
                "entity_id": mission_id,
                "relation_type": "observed",
            },
            created_at=review.created_at,
            updated_at=review.created_at,
        )
        return self._provider.store(entry)

    def record_acceptance_judgments(
        self,
        *,
        mission_id: str,
        round_id: int,
        judgments: list[AcceptanceJudgment],
    ) -> list[str]:
        """Store acceptance judgments in episodic memory."""
        keys: list[str] = []
        for judgment in judgments:
            reviewed = judgment.workflow_state is not AcceptanceWorkflowState.QUEUED
            provenance = "reviewed" if reviewed else "unreviewed"
            entry = MemoryEntry(
                key=f"acceptance-judgment-{mission_id}-round-{round_id}-{judgment.judgment_id}",
                content=judgment.summary,
                layer=MemoryLayer.EPISODIC,
                tags=[
                    "acceptance-judgment",
                    f"judgment-class:{judgment.judgment_class.value}",
                    f"workflow-state:{judgment.workflow_state.value}",
                    f"run-mode:{judgment.run_mode.value}",
                    f"provenance:{provenance}",
                ],
                metadata={
                    "mission_id": mission_id,
                    "round_id": round_id,
                    "judgment_id": judgment.judgment_id,
                    "judgment_class": judgment.judgment_class.value,
                    "workflow_state": judgment.workflow_state.value,
                    "run_mode": judgment.run_mode.value,
                    "confidence": judgment.confidence,
                    "finding_id": judgment.candidate.finding_id if judgment.candidate else "",
                    "route": judgment.candidate.route if judgment.candidate else "",
                    "evidence_refs": (
                        list(judgment.candidate.evidence_refs) if judgment.candidate else []
                    ),
                    "baseline_ref": judgment.candidate.baseline_ref if judgment.candidate else "",
                    "origin_step": judgment.candidate.origin_step if judgment.candidate else "",
                    "graph_profile": judgment.candidate.graph_profile if judgment.candidate else "",
                    "compare_overlay": (
                        judgment.candidate.compare_overlay if judgment.candidate else False
                    ),
                    "promotion_test": (
                        judgment.candidate.promotion_test if judgment.candidate else ""
                    ),
                    "dedupe_key": judgment.candidate.dedupe_key if judgment.candidate else "",
                    "provenance": provenance,
                    "entity_scope": "mission",
                    "entity_id": mission_id,
                    "relation_type": "observed",
                },
            )
            keys.append(self._provider.store(entry))
        return keys

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

    def record_evolution_journal(
        self,
        *,
        evolver_name: str,
        stage: str,
        summary: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Write a detailed evolution-journal event to episodic memory."""
        entry_metadata = {
            "evolver_name": evolver_name,
            "stage": stage,
            "entity_scope": "evolution",
            "entity_id": evolver_name,
            "relation_type": "observed",
            **(metadata or {}),
        }
        content = f"# Evolution {evolver_name} — {stage}"
        if summary:
            content += f"\n\n{summary}"
        return self._provider.store(
            MemoryEntry(
                key=f"evolution-journal-{evolver_name}-{stage}",
                content=content,
                layer=MemoryLayer.EPISODIC,
                tags=[
                    "evolution-journal",
                    f"evolver:{evolver_name}",
                    f"stage:{stage}",
                ],
                metadata=entry_metadata,
            )
        )
