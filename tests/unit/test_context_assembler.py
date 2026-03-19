from __future__ import annotations

import json
from pathlib import Path

from spec_orch.domain.context import NodeContextSpec
from spec_orch.domain.models import Issue, IssueContext
from spec_orch.services.context_assembler import ContextAssembler


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
