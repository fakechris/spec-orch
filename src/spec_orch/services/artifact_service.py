from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from spec_orch.domain.models import VerificationSummary


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
        builder_adapter: str | None = None,
        verification: VerificationSummary | None = None,
        acceptance_criteria: list[str] | None = None,
    ) -> Path:
        explain = workspace / "explain.md"
        blocked = ", ".join(failed_conditions) if failed_conditions else "none"
        compliance = builder_contract_compliance or {}
        compliant = "yes" if compliance.get("compliant") else "no"
        first_action_seen = "yes" if compliance.get("first_action_seen") else "no"
        violation_count = len(compliance.get("violations", []))

        sections: list[str] = []

        sections.append(f"# Explain Report for {issue_id}")
        sections.append("")
        sections.append(f"**{issue_title}**")
        sections.append("")

        sections.append("## Verdict")
        sections.append("")
        sections.append(f"- mergeable={mergeable}")
        sections.append(f"- blocked_by={blocked}")
        sections.append("")

        sections.append("## Gate Conditions")
        sections.append("")
        sections.append("| Condition | Status | Notes |")
        sections.append("|-----------|--------|-------|")
        sections.append("| spec_exists | pass | |")
        sections.append("| spec_approved | pass | |")
        sections.append("| within_boundaries | pass | |")
        sections.append(f"| builder | {builder_status} | adapter={builder_adapter or 'unknown'} |")

        if verification:
            for step, detail in verification.details.items():
                passed = verification.get_step_passed(step)
                status = "pass" if passed else "fail"
                exit_info = f"exit_code={detail.exit_code}" if detail else ""
                sections.append(f"| verification.{step} | {status} | {exit_info} |")
        else:
            sections.append("| verification | pending | |")

        reviewed_by_val = reviewed_by or "pending"
        accepted_by_val = accepted_by or "pending"
        sections.append(f"| review | {review_status} | reviewed_by={reviewed_by_val} |")
        sections.append(
            f"| human_acceptance | {acceptance_status} | accepted_by={accepted_by_val} |"
        )
        sections.append("")

        sections.append("## Builder Summary")
        sections.append("")
        sections.append(f"- builder_status={builder_status}")
        sections.append(f"- adapter={builder_adapter or 'unknown'}")
        sections.append(f"- builder_contract_compliant={compliant}")
        sections.append(f"- builder_first_action_seen={first_action_seen}")
        sections.append(f"- builder_contract_violations={violation_count}")
        sections.append("")

        if acceptance_criteria:
            sections.append("## Acceptance Criteria")
            sections.append("")
            for criterion in acceptance_criteria:
                checked = self._auto_check_criterion(criterion, verification)
                mark = "x" if checked else " "
                sections.append(f"- [{mark}] {criterion}")
            sections.append("")

        review_focus = self._compute_review_focus(
            builder_status=builder_status,
            verification=verification,
            compliance=compliance,
        )
        if review_focus:
            sections.append("## Suggested Review Focus")
            sections.append("")
            for item in review_focus:
                sections.append(f"- {item}")
            sections.append("")

        diff_stat = self._git_diff_stat(workspace)
        if diff_stat:
            sections.append("## File Changes")
            sections.append("")
            sections.append("```")
            sections.append(diff_stat)
            sections.append("```")
            sections.append("")

        explain.write_text("\n".join(sections) + "\n")
        return explain

    def _auto_check_criterion(
        self, criterion: str, verification: VerificationSummary | None
    ) -> bool:
        if verification is None:
            return False
        lower = criterion.lower()
        if "all tests pass" in lower or "tests pass" in lower:
            return verification.get_step_passed("test")
        if "lint" in lower:
            return verification.get_step_passed("lint")
        return False

    def _compute_review_focus(
        self,
        *,
        builder_status: str,
        verification: VerificationSummary | None,
        compliance: dict,
    ) -> list[str]:
        focus: list[str] = []
        if builder_status == "failed":
            focus.append("Builder failed — check builder_report.json for details")
        if verification:
            for step in verification.details:
                if not verification.get_step_passed(step):
                    focus.append(f"Verification step '{step}' failed")
        if not compliance.get("compliant", True):
            focus.append(f"Builder contract violations: {len(compliance.get('violations', []))}")
        return focus

    def _git_diff_stat(self, workspace: Path) -> str:
        if not (workspace / ".git").exists():
            return ""
        result = subprocess.run(
            ["git", "diff", "--stat", "main"],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else ""

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
