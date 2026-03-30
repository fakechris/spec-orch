from __future__ import annotations

import json
from pathlib import Path

from spec_orch.domain.models import BuilderResult
from spec_orch.runtime_core.adapters import write_worker_attempt_payloads
from spec_orch.runtime_core.paths import (
    normalized_issue_conclusion_path,
    normalized_issue_live_path,
    normalized_issue_manifest_path,
    normalized_round_decision_path,
    normalized_round_summary_path,
    normalized_worker_builder_report_path,
)
from spec_orch.runtime_core.writers import (
    write_issue_execution_payloads,
    write_round_supervision_payloads,
    write_worker_execution_payloads,
)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_write_issue_execution_payloads_writes_canonical_files(tmp_path: Path) -> None:
    workspace = tmp_path / ".spec_orch_runs" / "run-123"

    written = write_issue_execution_payloads(
        workspace,
        live={"run_id": "run-123", "state": "building"},
        conclusion={"run_id": "run-123", "verdict": "pass"},
        manifest={"run_id": "run-123", "artifacts": {"report": "report.json"}},
    )

    assert written["live"] == normalized_issue_live_path(workspace)
    assert written["conclusion"] == normalized_issue_conclusion_path(workspace)
    assert written["manifest"] == normalized_issue_manifest_path(workspace)
    assert _read_json(written["live"]) == {"run_id": "run-123", "state": "building"}
    assert _read_json(written["conclusion"]) == {"run_id": "run-123", "verdict": "pass"}
    assert _read_json(written["manifest"]) == {
        "run_id": "run-123",
        "artifacts": {"report": "report.json"},
    }


def test_write_worker_execution_payloads_writes_builder_report(tmp_path: Path) -> None:
    worker_dir = tmp_path / "docs/specs/mission-1/workers/pkt-1"

    written = write_worker_execution_payloads(
        worker_dir,
        builder_report={"succeeded": True, "session_name": "mission-1-pkt-1"},
    )

    assert written["builder_report"] == normalized_worker_builder_report_path(worker_dir)
    assert _read_json(written["builder_report"]) == {
        "succeeded": True,
        "session_name": "mission-1-pkt-1",
    }


def test_write_round_supervision_payloads_writes_summary_and_optional_decision(
    tmp_path: Path,
) -> None:
    round_dir = tmp_path / "docs/specs/mission-1/rounds/round-02"

    written = write_round_supervision_payloads(
        round_dir,
        summary={"round_id": 2, "worker_results": [{"packet_id": "pkt-1"}]},
        decision={"action": "ask_human", "summary": "Need approval."},
    )

    assert written["summary"] == normalized_round_summary_path(round_dir)
    assert written["decision"] == normalized_round_decision_path(round_dir)
    assert _read_json(written["summary"]) == {
        "round_id": 2,
        "worker_results": [{"packet_id": "pkt-1"}],
    }
    assert _read_json(written["decision"]) == {
        "action": "ask_human",
        "summary": "Need approval.",
    }


def test_write_round_supervision_payloads_skips_decision_when_absent(tmp_path: Path) -> None:
    round_dir = tmp_path / "docs/specs/mission-1/rounds/round-03"

    written = write_round_supervision_payloads(
        round_dir,
        summary={"round_id": 3, "worker_results": []},
        decision=None,
    )

    assert written["summary"] == normalized_round_summary_path(round_dir)
    assert "decision" not in written
    assert normalized_round_summary_path(round_dir).exists()
    assert not normalized_round_decision_path(round_dir).exists()


def test_write_worker_attempt_payloads_synthesizes_builder_report_when_missing(
    tmp_path: Path,
) -> None:
    builder = BuilderResult(
        succeeded=True,
        command=["stub"],
        stdout="ok",
        stderr="",
        report_path=tmp_path / "missing-builder-report.json",
        adapter="stub",
        agent="stub-agent",
        metadata={"source": "test"},
    )

    written = write_worker_attempt_payloads(
        tmp_path,
        builder_result=builder,
        session_name="worker-123",
    )

    assert written["builder_report"] == normalized_worker_builder_report_path(tmp_path)
    assert _read_json(written["builder_report"]) == {
        "adapter": "stub",
        "agent": "stub-agent",
        "command": ["stub"],
        "metadata": {"source": "test"},
        "session_name": "worker-123",
        "stderr": "",
        "stdout": "ok",
        "succeeded": True,
    }
