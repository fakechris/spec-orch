"""Extracted file-I/O and report-writing concerns from RunController."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from spec_orch.domain.compliance import default_turn_contract_compliance
from spec_orch.domain.models import (
    ArtifactManifest,
    BuilderResult,
    GateVerdict,
    Issue,
    ReviewSummary,
    RunState,
    VerificationDetail,
    VerificationSummary,
)
from spec_orch.runtime_core.paths import normalized_issue_live_path, normalized_issue_manifest_path
from spec_orch.services.io import atomic_write_json

logger = logging.getLogger(__name__)


class RunReportWriter:
    """Encapsulates report.json, artifact_manifest.json, and state persistence."""

    @staticmethod
    def load_persisted_run_payload(workspace: Path) -> dict[str, Any]:
        """Load persisted run payload preferring unified live snapshot.

        Preference order:
        1) run_artifact/live.json
        2) report.json
        """
        live_path = normalized_issue_live_path(workspace)
        report_path = workspace / "report.json"

        live_data = RunReportWriter.read_json_dict(live_path)
        report_data = RunReportWriter.read_json_dict(report_path)

        if live_data:
            merged = dict(live_data)
            for key in ("human_acceptance", "metadata", "title"):
                if key in report_data and key not in merged:
                    merged[key] = report_data[key]
            if "run_id" not in merged and "run_id" in report_data:
                merged["run_id"] = report_data["run_id"]
            return merged

        if report_data:
            return report_data

        raise FileNotFoundError(f"persisted run payload not found under {workspace}")

    @staticmethod
    def read_json_dict(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text())
            if isinstance(data, dict):
                return data
            logger.warning("Non-dict JSON in %s, resetting to empty", path)
            return {}
        except (json.JSONDecodeError, OSError):
            logger.warning("Failed to read %s, resetting to empty", path, exc_info=True)
            return {}

    @staticmethod
    def persist_state(
        workspace: Path,
        issue: Issue,
        run_id: str,
        state: RunState,
    ) -> None:
        """Write a minimal report.json to persist the current state."""
        report_path = workspace / "report.json"
        existing = RunReportWriter.read_json_dict(report_path)
        existing.update(
            {
                "state": state.value,
                "run_id": run_id,
                "issue_id": issue.issue_id,
                "title": issue.title,
            }
        )
        atomic_write_json(report_path, existing)

    @staticmethod
    def read_state(workspace: Path) -> RunState | None:
        """Read persisted run state from unified artifacts or legacy report."""
        try:
            data = RunReportWriter.load_persisted_run_payload(workspace)
        except FileNotFoundError:
            return None
        raw = data.get("state")
        if raw is None:
            return RunState.GATE_EVALUATED
        try:
            return RunState(raw)
        except ValueError:
            return RunState.GATE_EVALUATED

    @staticmethod
    def load_toml(path: Path) -> dict[str, Any]:
        """Load a TOML file (requires Python 3.11+)."""
        import tomllib

        with open(path, "rb") as f:
            return tomllib.load(f)  # type: ignore[no-any-return]

    @staticmethod
    def write_artifact_manifest(
        *,
        workspace: Path,
        run_id: str,
        issue: Issue,
        builder: BuilderResult,
        review: ReviewSummary,
        explain: Path,
        report: Path,
    ) -> Path:
        """Write artifact_manifest.json cataloguing all run artifacts."""
        artifacts: dict[str, str] = {}

        spec_path = workspace / "spec_snapshot.json"
        if spec_path.exists():
            artifacts["spec_snapshot"] = str(spec_path)

        if builder.report_path and builder.report_path.exists():
            artifacts["builder_report"] = str(builder.report_path)

        events_path = workspace / "telemetry" / "incoming_events.jsonl"
        if events_path.exists():
            artifacts["builder_events"] = str(events_path)

        artifacts["report"] = str(report)

        if explain.exists():
            artifacts["explain"] = str(explain)

        if review.report_path and review.report_path.exists():
            artifacts["review_report"] = str(review.report_path)

        deviations_path = workspace / "deviations.jsonl"
        if deviations_path.exists():
            artifacts["deviations"] = str(deviations_path)

        manifest = ArtifactManifest(
            run_id=run_id,
            issue_id=issue.issue_id,
            artifacts=artifacts,
            metadata={
                "compatibility_mode": "legacy_manifest_bridge",
                "canonical_manifest": str(normalized_issue_manifest_path(workspace)),
            },
        )
        manifest_path = workspace / "artifact_manifest.json"
        atomic_write_json(manifest_path, manifest.to_dict())
        return manifest_path

    @staticmethod
    def write_report(
        *,
        workspace: Path,
        issue: Issue,
        run_id: str,
        gate: GateVerdict,
        builder: BuilderResult,
        review: ReviewSummary,
        verification: VerificationSummary,
        accepted_by: str | None,
        state: RunState = RunState.GATE_EVALUATED,
    ) -> Path:
        report = workspace / "report.json"
        atomic_write_json(
            report,
            {
                "state": state.value,
                "run_id": run_id,
                "issue_id": issue.issue_id,
                "title": issue.title,
                "mergeable": gate.mergeable,
                "failed_conditions": gate.failed_conditions,
                "flow_control": {
                    "retry_recommended": gate.flow_control.retry_recommended,
                    "escalation_required": gate.flow_control.escalation_required,
                    "promotion_required": gate.flow_control.promotion_required,
                    "promotion_target": gate.flow_control.promotion_target,
                    "demotion_suggested": gate.flow_control.demotion_suggested,
                    "demotion_target": gate.flow_control.demotion_target,
                    "backtrack_reason": gate.flow_control.backtrack_reason,
                },
                "builder": {
                    "succeeded": builder.succeeded,
                    "skipped": builder.skipped,
                    "command": builder.command,
                    "report_path": str(builder.report_path),
                    "adapter": builder.adapter,
                    "agent": builder.agent,
                    "metadata": builder.metadata,
                },
                "review": {
                    "verdict": review.verdict,
                    "reviewed_by": review.reviewed_by,
                    "report_path": str(review.report_path) if review.report_path else None,
                },
                "verification": {
                    name: {
                        "exit_code": detail.exit_code,
                        "command": detail.command,
                    }
                    for name, detail in verification.details.items()
                },
                "human_acceptance": {
                    "accepted": accepted_by is not None,
                    "accepted_by": accepted_by,
                    "acceptance_path": str(workspace / "acceptance.json")
                    if accepted_by is not None
                    else None,
                },
            },
        )
        return report

    @staticmethod
    def issue_from_report(report_data: dict) -> Issue:
        """Reconstruct a minimal Issue from persisted report.json."""
        verification_cmds: dict[str, list[str]] = {}
        for name, detail in report_data.get("verification", {}).items():
            cmd = detail.get("command", [])
            if cmd:
                verification_cmds[name] = cmd
        return Issue(
            issue_id=report_data["issue_id"],
            title=report_data.get("title", report_data["issue_id"]),
            summary="",
            verification_commands=verification_cmds,
        )

    @staticmethod
    def builder_from_report(report_data: dict, workspace: Path) -> BuilderResult:
        builder_data = report_data["builder"]
        return BuilderResult(
            succeeded=builder_data["succeeded"],
            command=builder_data.get("command", []),
            stdout="",
            stderr="",
            report_path=workspace / "builder_report.json",
            adapter=builder_data["adapter"],
            agent=builder_data["agent"],
            skipped=builder_data.get("skipped", False),
            metadata={
                **builder_data.get("metadata", {}),
                "turn_contract_compliance": builder_data.get("metadata", {}).get(
                    "turn_contract_compliance", default_turn_contract_compliance()
                ),
            },
        )

    @staticmethod
    def verification_from_report(report_data: dict) -> VerificationSummary:
        details = {
            name: VerificationDetail(
                command=detail.get("command", []),
                exit_code=detail["exit_code"],
                stdout="",
                stderr="",
            )
            for name, detail in report_data["verification"].items()
        }
        summary = VerificationSummary(details=details)
        for name, detail in details.items():
            summary.set_step_passed(name, detail.exit_code == 0)
        return summary

    @staticmethod
    def review_from_report(report_data: dict, workspace: Path) -> ReviewSummary:
        review_data = report_data["review"]
        return ReviewSummary(
            verdict=review_data["verdict"],
            reviewed_by=review_data.get("reviewed_by"),
            report_path=workspace / "review_report.json",
        )
