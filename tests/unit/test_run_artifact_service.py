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


def test_write_from_run_delegates_normalized_issue_payloads(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "run-2"
    workspace.mkdir()
    report_path = workspace / "report.json"
    report_path.write_text(
        json.dumps(
            {
                "state": "gate_evaluated",
                "mergeable": False,
                "failed_conditions": ["tests"],
                "builder": {"adapter": "codex_exec", "succeeded": False},
            }
        ),
        encoding="utf-8",
    )

    delegated: dict[str, object] = {}

    def fake_write_issue_execution_payloads(
        workspace_arg: Path,
        *,
        live: dict,
        conclusion: dict,
        manifest: dict,
    ) -> dict[str, Path]:
        delegated["workspace"] = workspace_arg
        delegated["live"] = live
        delegated["conclusion"] = conclusion
        delegated["manifest"] = manifest
        artifact_dir = workspace_arg / "run_artifact"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        return {
            "live": artifact_dir / "live.json",
            "conclusion": artifact_dir / "conclusion.json",
            "manifest": artifact_dir / "manifest.json",
        }

    monkeypatch.setattr(
        "spec_orch.services.run_artifact_service.write_issue_execution_payloads",
        fake_write_issue_execution_payloads,
    )

    manifest_path = RunArtifactService().write_from_run(
        workspace=workspace,
        run_id="run-2",
        issue_id="SON-2",
        report_path=report_path,
        explain_path=None,
    )

    assert manifest_path == workspace / "run_artifact" / "manifest.json"
    assert delegated["workspace"] == workspace
    assert isinstance(delegated["live"], dict)
    assert isinstance(delegated["conclusion"], dict)
    assert isinstance(delegated["manifest"], dict)


def test_write_from_run_projects_flow_control_into_live_and_conclusion(tmp_path: Path) -> None:
    workspace = tmp_path / "run-3"
    workspace.mkdir()
    report_path = workspace / "report.json"
    report_path.write_text(
        json.dumps(
            {
                "state": "gate_evaluated",
                "mergeable": True,
                "failed_conditions": [],
                "flow_control": {
                    "retry_recommended": False,
                    "escalation_required": False,
                    "promotion_required": True,
                    "promotion_target": "standard",
                    "demotion_suggested": False,
                    "demotion_target": None,
                    "backtrack_reason": "recoverable",
                },
                "builder": {"adapter": "codex_exec", "succeeded": True},
            }
        ),
        encoding="utf-8",
    )

    RunArtifactService().write_from_run(
        workspace=workspace,
        run_id="run-3",
        issue_id="SON-3",
        report_path=report_path,
        explain_path=None,
    )

    live = json.loads((workspace / "run_artifact" / "live.json").read_text(encoding="utf-8"))
    conclusion = json.loads(
        (workspace / "run_artifact" / "conclusion.json").read_text(encoding="utf-8")
    )

    assert live["flow_control"]["promotion_required"] is True
    assert conclusion["flow_control"]["promotion_target"] == "standard"
