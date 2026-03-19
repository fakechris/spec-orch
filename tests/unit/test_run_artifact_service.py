from __future__ import annotations

import json
from pathlib import Path

from spec_orch.services.run_artifact_service import RunArtifactService


def test_write_from_run_creates_unified_artifacts(tmp_path: Path) -> None:
    workspace = tmp_path / "run-1"
    workspace.mkdir()
    (workspace / "telemetry").mkdir()
    (workspace / "telemetry" / "events.jsonl").write_text(
        json.dumps({"event_type": "run_started", "issue_id": "SON-1", "run_id": "run-1"}) + "\n"
    )
    report_path = workspace / "report.json"
    report_path.write_text(
        json.dumps(
            {
                "state": "gate_evaluated",
                "mergeable": True,
                "failed_conditions": [],
                "builder": {"adapter": "codex_exec", "succeeded": True},
            }
        )
    )
    explain_path = workspace / "explain.md"
    explain_path.write_text("# explain")

    svc = RunArtifactService()
    manifest_path = svc.write_from_run(
        workspace=workspace,
        run_id="run-1",
        issue_id="SON-1",
        report_path=report_path,
        explain_path=explain_path,
    )

    assert manifest_path.exists()
    artifact_dir = workspace / "run_artifact"
    assert (artifact_dir / "events.jsonl").exists()
    assert (artifact_dir / "live.json").exists()
    assert (artifact_dir / "retro.json").exists()
    assert (artifact_dir / "conclusion.json").exists()
    assert (artifact_dir / "manifest.json").exists()

    manifest = json.loads((artifact_dir / "manifest.json").read_text())
    assert manifest["run_id"] == "run-1"
    assert manifest["issue_id"] == "SON-1"
    assert manifest["mergeable"] is True
    assert "report" in manifest["artifacts"]
    assert "builder_events" in manifest["artifacts"]
    assert manifest["artifacts"]["report"].endswith("run_artifact/live.json")
