from __future__ import annotations

import json
from pathlib import Path

from spec_orch.domain.models import (
    BuilderResult,
    GateInput,
    Issue,
    ReviewSummary,
    RunResult,
    VerificationDetail,
    VerificationSummary,
)
from spec_orch.services.artifact_service import ArtifactService
from spec_orch.services.gate_service import GateService
from spec_orch.services.pi_builder_adapter import PiBuilderAdapter
from spec_orch.services.verification_service import VerificationService
from spec_orch.services.workspace_service import WorkspaceService


class RunController:
    def __init__(self, *, repo_root: Path, pi_executable: str = "pi") -> None:
        self.repo_root = Path(repo_root)
        self.artifact_service = ArtifactService()
        self.builder_adapter = PiBuilderAdapter(executable=pi_executable)
        self.gate_service = GateService()
        self.verification_service = VerificationService()
        self.workspace_service = WorkspaceService(repo_root=self.repo_root)

    def run_issue(self, issue_id: str) -> RunResult:
        issue = self._load_fixture(issue_id)
        workspace = self.workspace_service.prepare_issue_workspace(issue.issue_id)

        task_spec, progress = self.artifact_service.write_initial_artifacts(
            workspace=workspace,
            issue_id=issue.issue_id,
            issue_title=issue.title,
        )

        builder = self.builder_adapter.run(issue=issue, workspace=workspace)
        verification = self.verification_service.run(issue=issue, workspace=workspace)

        gate = self.gate_service.evaluate(
            GateInput(
                spec_exists=True,
                spec_approved=True,
                within_boundaries=True,
                builder_succeeded=builder.succeeded,
                verification=verification,
                review=ReviewSummary(verdict="pass"),
                human_acceptance=False,
            )
        )
        explain = self.artifact_service.write_explain_report(
            workspace=workspace,
            issue_id=issue.issue_id,
            issue_title=issue.title,
            mergeable=gate.mergeable,
            failed_conditions=gate.failed_conditions,
            builder_status=self._builder_status(builder),
            acceptance_status="pending",
            accepted_by=None,
        )
        report = self._write_report(
            workspace=workspace,
            issue=issue,
            gate=gate,
            builder=builder,
            verification=verification,
            accepted_by=None,
        )

        return RunResult(
            issue=issue,
            workspace=workspace,
            task_spec=task_spec,
            progress=progress,
            explain=explain,
            report=report,
            builder=builder,
            gate=gate,
        )

    def accept_issue(self, issue_id: str, *, accepted_by: str) -> RunResult:
        issue = self._load_fixture(issue_id)
        workspace = self.workspace_service.issue_workspace_path(issue.issue_id)
        if not workspace.exists():
            raise FileNotFoundError(f"workspace not found for issue {issue.issue_id}")

        report = workspace / "report.json"
        if not report.exists():
            raise FileNotFoundError(f"report not found for issue {issue.issue_id}")

        report_data = json.loads(report.read_text())
        self.artifact_service.write_acceptance_artifact(
            workspace=workspace,
            issue_id=issue.issue_id,
            accepted_by=accepted_by,
        )
        builder = self._builder_from_report(report_data, workspace)
        verification = self._verification_from_report(report_data)
        gate = self.gate_service.evaluate(
            GateInput(
                spec_exists=True,
                spec_approved=True,
                within_boundaries=True,
                builder_succeeded=builder.succeeded,
                verification=verification,
                review=ReviewSummary(verdict="pass"),
                human_acceptance=True,
            )
        )
        explain = self.artifact_service.write_explain_report(
            workspace=workspace,
            issue_id=issue.issue_id,
            issue_title=issue.title,
            mergeable=gate.mergeable,
            failed_conditions=gate.failed_conditions,
            builder_status=self._builder_status(builder),
            acceptance_status="accepted",
            accepted_by=accepted_by,
        )
        updated_report = self._write_report(
            workspace=workspace,
            issue=issue,
            gate=gate,
            builder=builder,
            verification=verification,
            accepted_by=accepted_by,
        )

        return RunResult(
            issue=issue,
            workspace=workspace,
            task_spec=workspace / "task.spec.md",
            progress=workspace / "progress.md",
            explain=explain,
            report=updated_report,
            builder=builder,
            gate=gate,
        )

    def _load_fixture(self, issue_id: str) -> Issue:
        fixture_path = self.repo_root / "fixtures" / "issues" / f"{issue_id}.json"
        if fixture_path.exists():
            data = json.loads(fixture_path.read_text())
            return Issue(
                issue_id=data["issue_id"],
                title=data["title"],
                summary=data["summary"],
                builder_prompt=data.get("builder_prompt"),
                verification_commands=data.get("verification_commands", {}),
            )

        return Issue(
            issue_id=issue_id,
            title="Build MVP runner",
            summary="Local happy-path issue fixture for the first prototype.",
        )

    def _builder_status(self, builder) -> str:
        if builder.skipped:
            return "skipped"
        if builder.succeeded:
            return "passed"
        return "failed"

    def _builder_from_report(self, report_data: dict, workspace: Path) -> BuilderResult:
        builder_data = report_data["builder"]
        return BuilderResult(
            succeeded=builder_data["succeeded"],
            command=builder_data.get("command", []),
            stdout="",
            stderr="",
            report_path=workspace / "builder_report.json",
            skipped=builder_data.get("skipped", False),
        )

    def _verification_from_report(self, report_data: dict) -> VerificationSummary:
        details = {
            name: VerificationDetail(
                command=detail.get("command", []),
                exit_code=detail["exit_code"],
                stdout="",
                stderr="",
            )
            for name, detail in report_data["verification"].items()
        }
        return VerificationSummary(
            lint_passed=details["lint"].exit_code == 0,
            typecheck_passed=details["typecheck"].exit_code == 0,
            test_passed=details["test"].exit_code == 0,
            build_passed=details["build"].exit_code == 0,
            details=details,
        )

    def _write_report(
        self,
        *,
        workspace: Path,
        issue: Issue,
        gate,
        builder: BuilderResult,
        verification: VerificationSummary,
        accepted_by: str | None,
    ) -> Path:
        report = workspace / "report.json"
        report.write_text(
            json.dumps(
                {
                    "issue_id": issue.issue_id,
                    "title": issue.title,
                    "mergeable": gate.mergeable,
                    "failed_conditions": gate.failed_conditions,
                    "builder": {
                        "succeeded": builder.succeeded,
                        "skipped": builder.skipped,
                        "command": builder.command,
                        "report_path": str(builder.report_path),
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
                indent=2,
            )
            + "\n"
        )
        return report
