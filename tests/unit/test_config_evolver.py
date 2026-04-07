from __future__ import annotations

import json
from pathlib import Path

from spec_orch.services.evolution.config_evolver import ConfigEvolver


def test_load_reports_prefers_unified_artifacts(tmp_path: Path) -> None:
    run_dir = tmp_path / ".spec_orch_runs" / "R1"
    (run_dir / "run_artifact").mkdir(parents=True)
    (run_dir / "report.json").write_text(
        json.dumps({"issue_id": "legacy", "mergeable": False, "failed_conditions": ["legacy"]})
    )
    (run_dir / "run_artifact" / "conclusion.json").write_text(
        json.dumps({"issue_id": "unified", "mergeable": True, "failed_conditions": []})
    )
    (run_dir / "run_artifact" / "live.json").write_text(
        json.dumps({"verification": {"test": {"exit_code": 0, "command": "pytest"}}})
    )

    evolver = ConfigEvolver(tmp_path)
    reports = evolver._load_reports()
    assert len(reports) == 1
    assert reports[0]["issue_id"] == "unified"
    assert reports[0]["mergeable"] is True
    assert "verification" in reports[0]
