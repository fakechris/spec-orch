from __future__ import annotations

import json
from pathlib import Path

from spec_orch.domain.context import NodeContextSpec
from spec_orch.domain.execution_semantics import (
    ArtifactCarrierKind,
    ArtifactRef,
    ArtifactScope,
    ContinuityKind,
    ExecutionAttempt,
    ExecutionAttemptState,
    ExecutionOutcome,
    ExecutionOwnerKind,
    ExecutionStatus,
    ExecutionUnitKind,
    SubjectKind,
)
from spec_orch.domain.models import Issue, IssueContext
from spec_orch.services.context_assembler import ContextAssembler
from spec_orch.services.node_context_registry import get_node_context_spec


def test_context_assembler_supports_unified_manifest_keys(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    (ws / "run_artifact").mkdir(parents=True)
    (ws / "run_artifact" / "live.json").write_text(
        json.dumps(
            {
                "mergeable": False,
                "failed_conditions": ["verification"],
                "verification": {"test": {"exit_code": 1, "command": ["pytest"]}},
            }
        )
    )
    (ws / "run_artifact" / "events.jsonl").write_text('{"event":"x"}\n')
    (ws / "run_artifact" / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": "run-1",
                "issue_id": "SON-1",
                "artifacts": {
                    "live": str(ws / "run_artifact" / "live.json"),
                    "events": str(ws / "run_artifact" / "events.jsonl"),
                },
            }
        )
    )

    assembler = ContextAssembler()
    spec = NodeContextSpec(
        node_name="x",
        required_task_fields=[],
        required_execution_fields=["git_diff"],
        required_learning_fields=[],
        max_tokens_budget=600,
    )
    issue = Issue(issue_id="SON-1", title="t", summary="s", context=IssueContext())
    ctx = assembler.assemble(spec, issue, ws)

    assert ctx.execution.gate_report is not None
    assert ctx.execution.gate_report.mergeable is False
    assert ctx.execution.verification_results is not None
    assert ctx.execution.builder_events_summary is not None


def test_supervisor_node_context_spec_is_registered() -> None:
    spec = get_node_context_spec("supervisor")

    assert spec.node_name == "supervisor"
    assert "constraints" in spec.required_task_fields
    assert "git_diff" in spec.required_execution_fields
    assert "verification_results" in spec.required_execution_fields
    assert "gate_report" in spec.required_execution_fields
    assert "builder_events_summary" in spec.required_execution_fields
    assert "review_summary" in spec.required_execution_fields
    assert "similar_failure_samples" in spec.required_learning_fields
    assert "active_delivery_learnings" in spec.required_learning_fields
    assert "active_feedback_learnings" in spec.required_learning_fields
    assert "reviewed_decision_failures" in spec.required_learning_fields
    assert "reviewed_acceptance_findings" in spec.required_learning_fields


def test_context_assembler_injects_role_scoped_learning_slices(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    issue = Issue(
        issue_id="SON-1", title="launcher", summary="tighten launcher UX", context=IssueContext()
    )

    class _Memory:
        def get_active_learning_slice(self, kind: str) -> list[dict]:
            return [{"key": f"{kind}-1", "content": f"{kind} learning"}]

        def get_recent_evolution_journal(self) -> list[dict]:
            return [{"evolver_name": "prompt_evolver", "stage": "validate"}]

    spec = get_node_context_spec("prompt_evolver")
    ctx = ContextAssembler().assemble(spec, issue, ws, memory=_Memory(), repo_root=tmp_path)

    assert ctx.learning.active_self_learnings == [{"key": "self-1", "content": "self learning"}]
    assert ctx.learning.recent_evolution_journal == [
        {"evolver_name": "prompt_evolver", "stage": "validate"}
    ]
    assert ctx.learning.active_delivery_learnings == []
    assert ctx.learning.active_feedback_learnings == []


def test_context_assembler_injects_reviewed_decision_learning_views(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    issue = Issue(
        issue_id="SON-7",
        title="review routing",
        summary="stabilize approval routing",
        context=IssueContext(),
    )

    class _Memory:
        def get_reviewed_decision_failures(self) -> list[dict]:
            return [{"record_id": "r-fail", "summary": "Needed human escalation."}]

        def get_reviewed_decision_recipes(self) -> list[dict]:
            return [{"record_id": "r-pass", "summary": "Transcript evidence was sufficient."}]

        def get_reviewed_acceptance_findings(self) -> list[dict]:
            return [
                {
                    "judgment_id": "j-1",
                    "summary": "Launcher confusion held for review.",
                    "finding_id": "candidate-1",
                    "origin_step": "launcher_scan",
                    "graph_profile": "tuned_dashboard_compare_graph",
                    "run_mode": "explore",
                    "compare_overlay": True,
                }
            ]

    spec = get_node_context_spec("supervisor")
    ctx = ContextAssembler().assemble(spec, issue, ws, memory=_Memory(), repo_root=tmp_path)

    assert ctx.learning.reviewed_decision_failures == [
        {"record_id": "r-fail", "summary": "Needed human escalation."}
    ]
    assert ctx.learning.reviewed_decision_recipes == [
        {"record_id": "r-pass", "summary": "Transcript evidence was sufficient."}
    ]
    assert ctx.learning.reviewed_acceptance_findings == [
        {
            "judgment_id": "j-1",
            "summary": "Launcher confusion held for review.",
            "finding_id": "candidate-1",
            "origin_step": "launcher_scan",
            "graph_profile": "tuned_dashboard_compare_graph",
            "run_mode": "explore",
            "compare_overlay": True,
        }
    ]


def test_context_assembler_prefers_normalized_issue_attempt(tmp_path: Path, monkeypatch) -> None:
    ws = tmp_path / "ws"
    ws.mkdir(parents=True)
    events_path = ws / "run_artifact" / "events.jsonl"
    events_path.parent.mkdir(parents=True)
    events_path.write_text('{"event":"normalized"}\n', encoding="utf-8")

    normalized = ExecutionAttempt(
        attempt_id="run-ctx",
        unit_kind=ExecutionUnitKind.ISSUE,
        unit_id="SON-2",
        owner_kind=ExecutionOwnerKind.RUN_CONTROLLER,
        continuity_kind=ContinuityKind.FILE_BACKED_RUN,
        continuity_id="run-ctx",
        workspace_root=str(ws),
        attempt_state=ExecutionAttemptState.COMPLETED,
        outcome=ExecutionOutcome(
            unit_kind=ExecutionUnitKind.ISSUE,
            owner_kind=ExecutionOwnerKind.RUN_CONTROLLER,
            status=ExecutionStatus.FAILED,
            build={"adapter": "codex"},
            verification={"pytest": {"exit_code": 1, "command": ["pytest"]}},
            review={"verdict": "pending"},
            gate={"mergeable": False, "failed_conditions": ["verification"]},
            artifacts={
                "event_log": ArtifactRef(
                    key="event_log",
                    scope=ArtifactScope.LEAF,
                    producer_kind="activity_logger",
                    subject_kind=SubjectKind.ISSUE,
                    carrier_kind=ArtifactCarrierKind.JSONL,
                    path=str(events_path),
                )
            },
        ),
    )
    monkeypatch.setattr(
        "spec_orch.services.context.context_assembler.read_issue_execution_attempt",
        lambda _: normalized,
    )

    assembler = ContextAssembler()
    spec = NodeContextSpec(
        node_name="x",
        required_task_fields=[],
        required_execution_fields=["builder_events_summary", "verification_results", "gate_report"],
        required_learning_fields=[],
        max_tokens_budget=600,
    )
    issue = Issue(issue_id="SON-2", title="t", summary="s", context=IssueContext())
    ctx = assembler.assemble(spec, issue, ws)

    assert ctx.execution.gate_report is not None
    assert ctx.execution.gate_report.mergeable is False
    assert ctx.execution.verification_results is not None
    assert ctx.execution.builder_events_summary is not None
