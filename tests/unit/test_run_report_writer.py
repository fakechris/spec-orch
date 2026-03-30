from __future__ import annotations

import json
from pathlib import Path

from spec_orch.domain.models import BuilderResult, Issue, ReviewSummary
from spec_orch.services.run_report_writer import RunReportWriter


def test_load_persisted_run_payload_prefers_normalized_live_path(tmp_path: Path) -> None:
    workspace = tmp_path / "run-1"
    (workspace / "run_artifact").mkdir(parents=True)
    (workspace / "run_artifact" / "live.json").write_text(
        json.dumps({"state": "gate_evaluated", "run_id": "run-1", "issue_id": "SON-1"}),
        encoding="utf-8",
    )
    (workspace / "report.json").write_text(
        json.dumps({"state": "failed", "title": "legacy title"}),
        encoding="utf-8",
    )

    payload = RunReportWriter.load_persisted_run_payload(workspace)

    assert payload["state"] == "gate_evaluated"
    assert payload["run_id"] == "run-1"
    assert payload["title"] == "legacy title"


def test_write_artifact_manifest_points_to_canonical_runtime_core_manifest(tmp_path: Path) -> None:
    workspace = tmp_path / "run-2"
    workspace.mkdir()
    issue = Issue(issue_id="SON-2", title="Issue 2", summary="")
    builder = BuilderResult(
        succeeded=True,
        command=["make", "test"],
        stdout="",
        stderr="",
        report_path=workspace / "builder_report.json",
        adapter="codex_exec",
        agent="builder",
    )
    builder.report_path.write_text("{}", encoding="utf-8")
    review = ReviewSummary(verdict="approved", reviewed_by="claude", report_path=None)
    explain = workspace / "explain.md"
    explain.write_text("# explain", encoding="utf-8")
    report = workspace / "report.json"
    report.write_text("{}", encoding="utf-8")

    manifest_path = RunReportWriter.write_artifact_manifest(
        workspace=workspace,
        run_id="run-2",
        issue=issue,
        builder=builder,
        review=review,
        explain=explain,
        report=report,
    )

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["metadata"]["canonical_manifest"].endswith("run_artifact/manifest.json")
