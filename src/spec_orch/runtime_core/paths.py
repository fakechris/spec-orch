"""Helpers for normalized runtime payload locations."""

from __future__ import annotations

from pathlib import Path


def normalized_issue_root(workspace: Path) -> Path:
    return workspace / "run_artifact"


def normalized_issue_live_path(workspace: Path) -> Path:
    return normalized_issue_root(workspace) / "live.json"


def normalized_issue_conclusion_path(workspace: Path) -> Path:
    return normalized_issue_root(workspace) / "conclusion.json"


def normalized_issue_manifest_path(workspace: Path) -> Path:
    return normalized_issue_root(workspace) / "manifest.json"


def normalized_mission_root(spec_root: Path) -> Path:
    return spec_root


def normalized_round_root(round_dir: Path) -> Path:
    return round_dir


def normalized_round_summary_path(round_dir: Path) -> Path:
    return normalized_round_root(round_dir) / "round_summary.json"


def normalized_round_decision_path(round_dir: Path) -> Path:
    return normalized_round_root(round_dir) / "round_decision.json"


def normalized_worker_builder_report_path(worker_dir: Path) -> Path:
    return worker_dir / "builder_report.json"


__all__ = [
    "normalized_issue_conclusion_path",
    "normalized_issue_live_path",
    "normalized_issue_manifest_path",
    "normalized_issue_root",
    "normalized_mission_root",
    "normalized_round_decision_path",
    "normalized_round_root",
    "normalized_round_summary_path",
    "normalized_worker_builder_report_path",
]
