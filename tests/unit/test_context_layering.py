from __future__ import annotations

from pathlib import Path

from spec_orch.domain.context import ContextBundle, NodeContextSpec, TaskContext
from spec_orch.domain.models import Issue, IssueContext
from spec_orch.services.context_assembler import ContextAssembler


def _issue() -> Issue:
    return Issue(
        issue_id="SON-500",
        title="Layer context explicitly",
        summary="Keep evidence, archive, and promoted learning separate.",
        context=IssueContext(),
    )


def test_context_bundle_declares_explicit_layer_contracts() -> None:
    bundle = ContextBundle(task=TaskContext(issue=_issue()))

    contracts = bundle.context_layer_contracts()

    assert set(contracts) >= {
        "execution",
        "evidence",
        "archive_lineage",
        "promoted_learning",
    }
    assert contracts["evidence"]["payload_fields"] == ["reviewed_acceptance_findings"]
    assert contracts["archive_lineage"]["payload_fields"] == ["recent_evolution_journal"]
    assert contracts["promoted_learning"]["payload_fields"] == [
        "active_self_learnings",
        "active_delivery_learnings",
        "active_feedback_learnings",
        "reviewed_decision_failures",
        "reviewed_decision_recipes",
    ]


def test_context_assembler_preserves_layered_memory_payloads(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()

    class _Memory:
        def get_context_layer_payloads(self) -> dict[str, dict[str, object]]:
            return {
                "evidence": {
                    "reviewed_acceptance_findings": [
                        {"finding_id": "finding-1", "summary": "Transcript gap."}
                    ]
                },
                "archive_lineage": {
                    "recent_evolution_journal": [
                        {"key": "journal-1", "summary": "Promoted a safer replay flow."}
                    ]
                },
                "promoted_learning": {
                    "active_self_learnings": [
                        {"key": "self-1", "content": "Keep replay evidence concise."}
                    ],
                    "active_delivery_learnings": [],
                    "active_feedback_learnings": [],
                    "reviewed_decision_failures": [
                        {
                            "record_id": "review-1",
                            "summary": "Verifier rejected self-certifying proof.",
                        }
                    ],
                    "reviewed_decision_recipes": [
                        {
                            "record_id": "recipe-1",
                            "summary": "Independent browser evidence was enough.",
                        }
                    ],
                },
            }

    bundle = ContextAssembler().assemble(
        NodeContextSpec(node_name="supervisor"),
        _issue(),
        workspace,
        memory=_Memory(),
        repo_root=tmp_path,
    )

    assert bundle.evidence.reviewed_acceptance_findings == [
        {"finding_id": "finding-1", "summary": "Transcript gap."}
    ]
    assert bundle.archive_lineage.recent_evolution_journal == [
        {"key": "journal-1", "summary": "Promoted a safer replay flow."}
    ]
    assert bundle.promoted_learning.active_self_learnings == [
        {"key": "self-1", "content": "Keep replay evidence concise."}
    ]
    assert bundle.promoted_learning.reviewed_decision_failures == [
        {"record_id": "review-1", "summary": "Verifier rejected self-certifying proof."}
    ]
    assert bundle.promoted_learning.reviewed_decision_recipes == [
        {"record_id": "recipe-1", "summary": "Independent browser evidence was enough."}
    ]
