"""Runtime-core writer helpers for canonical normalized carriers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from spec_orch.runtime_core.paths import (
    normalized_issue_conclusion_path,
    normalized_issue_live_path,
    normalized_issue_manifest_path,
    normalized_round_decision_path,
    normalized_round_summary_path,
    normalized_worker_builder_report_path,
)
from spec_orch.services.io import atomic_write_json


def write_issue_execution_payloads(
    workspace: Path,
    *,
    live: dict[str, Any],
    conclusion: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Path]:
    """Write normalized issue carriers in canonical order.

    Files are written in this order:
    1. ``live.json``
    2. ``conclusion.json``
    3. ``manifest.json``

    Because each call uses ``atomic_write_json`` independently, a later failure can
    still leave earlier files present. During the dual-write migration this is
    expected; readers must continue to tolerate partial normalized state and fall
    back to legacy carriers where needed.
    """
    live_path = normalized_issue_live_path(workspace)
    conclusion_path = normalized_issue_conclusion_path(workspace)
    manifest_path = normalized_issue_manifest_path(workspace)
    atomic_write_json(live_path, live)
    atomic_write_json(conclusion_path, conclusion)
    atomic_write_json(manifest_path, manifest)
    return {
        "live": live_path,
        "conclusion": conclusion_path,
        "manifest": manifest_path,
    }


def write_worker_execution_payloads(
    worker_dir: Path,
    *,
    builder_report: dict[str, Any],
) -> dict[str, Path]:
    builder_report_path = normalized_worker_builder_report_path(worker_dir)
    atomic_write_json(builder_report_path, builder_report)
    return {"builder_report": builder_report_path}


def write_round_supervision_payloads(
    round_dir: Path,
    *,
    summary: dict[str, Any],
    decision: dict[str, Any] | None,
) -> dict[str, Path]:
    summary_path = normalized_round_summary_path(round_dir)
    atomic_write_json(summary_path, summary)
    written = {"summary": summary_path}
    if decision is not None:
        decision_path = normalized_round_decision_path(round_dir)
        atomic_write_json(decision_path, decision)
        written["decision"] = decision_path
    return written


__all__ = [
    "write_issue_execution_payloads",
    "write_round_supervision_payloads",
    "write_worker_execution_payloads",
]
