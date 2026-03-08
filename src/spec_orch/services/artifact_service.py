from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path


class ArtifactService:
    def write_initial_artifacts(
        self,
        *,
        workspace: Path,
        issue_id: str,
        issue_title: str,
    ) -> tuple[Path, Path]:
        task_spec = workspace / "task.spec.md"
        progress = workspace / "progress.md"

        task_spec.write_text(
            "\n".join(
                [
                    f"# {issue_title}",
                    "",
                    "## Intent",
                    f"- Issue: {issue_id}",
                    f"- Title: {issue_title}",
                    "",
                    "## Boundaries",
                    "- MVP prototype only",
                ]
            )
            + "\n"
        )
        progress.write_text(
            "\n".join(
                [
                    "# Progress",
                    "",
                    f"- Issue: {issue_id}",
                    "- Status: drafted",
                    "- Next: run local builder adapter",
                ]
            )
            + "\n"
        )

        return task_spec, progress

    def write_explain_report(
        self,
        *,
        workspace: Path,
        issue_id: str,
        issue_title: str,
        mergeable: bool,
        failed_conditions: list[str],
        builder_status: str,
        review_status: str,
        reviewed_by: str | None,
        acceptance_status: str,
        accepted_by: str | None,
        builder_contract_compliance: dict | None,
    ) -> Path:
        explain = workspace / "explain.md"
        blocked = ", ".join(failed_conditions) if failed_conditions else "none"
        reviewed_by_value = reviewed_by or "pending"
        accepted_by_value = accepted_by or "pending"
        compliance = builder_contract_compliance or {}
        compliant = "yes" if compliance.get("compliant") else "no"
        first_action_seen = "yes" if compliance.get("first_action_seen") else "no"
        violation_count = len(compliance.get("violations", []))
        explain.write_text(
            "\n".join(
                [
                    f"# Explain Report for {issue_id}",
                    "",
                    f"- Title: {issue_title}",
                    f"- builder_status={builder_status}",
                    f"- review_status={review_status}",
                    f"- reviewed_by={reviewed_by_value}",
                    f"- acceptance_status={acceptance_status}",
                    f"- accepted_by={accepted_by_value}",
                    f"- mergeable={mergeable}",
                    f"- blocked_by={blocked}",
                    f"- builder_contract_compliant={compliant}",
                    f"- builder_first_action_seen={first_action_seen}",
                    f"- builder_contract_violations={violation_count}",
                ]
            )
            + "\n"
        )
        return explain

    def write_acceptance_artifact(
        self,
        *,
        workspace: Path,
        issue_id: str,
        accepted_by: str,
    ) -> Path:
        acceptance = workspace / "acceptance.json"
        acceptance.write_text(
            json.dumps(
                {
                    "issue_id": issue_id,
                    "accepted_by": accepted_by,
                    "accepted_at": datetime.now(UTC).isoformat(),
                },
                indent=2,
            )
            + "\n"
        )
        return acceptance
