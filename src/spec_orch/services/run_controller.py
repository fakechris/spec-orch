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
from spec_orch.services.codex_harness_builder_adapter import (
    CodexHarnessBuilderAdapter,
    CodexHarnessTransportError,
)
from spec_orch.services.gate_service import GateService
from spec_orch.services.pi_codex_builder_adapter import PiCodexBuilderAdapter
from spec_orch.services.review_adapter import LocalReviewAdapter
from spec_orch.services.telemetry_service import TelemetryService
from spec_orch.services.verification_service import VerificationService
from spec_orch.services.workspace_service import WorkspaceService


class RunController:
    def __init__(
        self,
        *,
        repo_root: Path,
        codex_executable: str = "codex",
        pi_executable: str = "pi",
    ) -> None:
        self.repo_root = Path(repo_root)
        self.artifact_service = ArtifactService()
        self.harness_builder_adapter = CodexHarnessBuilderAdapter(
            executable=codex_executable
        )
        self.pi_builder_adapter = PiCodexBuilderAdapter(executable=pi_executable)
        self.gate_service = GateService()
        self.review_adapter = LocalReviewAdapter()
        self.telemetry_service = TelemetryService()
        self.verification_service = VerificationService()
        self.workspace_service = WorkspaceService(repo_root=self.repo_root)

    def run_issue(self, issue_id: str) -> RunResult:
        issue = self._load_fixture(issue_id)
        workspace = self.workspace_service.prepare_issue_workspace(issue.issue_id)
        run_id = self.telemetry_service.new_run_id(issue.issue_id)
        self.telemetry_service.log_event(
            workspace=workspace,
            run_id=run_id,
            issue_id=issue.issue_id,
            component="run_controller",
            event_type="run_started",
            message="Started issue run.",
        )

        task_spec, progress = self.artifact_service.write_initial_artifacts(
            workspace=workspace,
            issue_id=issue.issue_id,
            issue_title=issue.title,
        )

        builder = self._run_builder(issue=issue, workspace=workspace, run_id=run_id)
        verification = self.verification_service.run(issue=issue, workspace=workspace)
        review = self.review_adapter.initialize(issue_id=issue.issue_id, workspace=workspace)

        gate = self.gate_service.evaluate(
            GateInput(
                spec_exists=True,
                spec_approved=True,
                within_boundaries=True,
                builder_succeeded=builder.succeeded,
                verification=verification,
                review=review,
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
            review_status=review.verdict,
            reviewed_by=review.reviewed_by,
            acceptance_status="pending",
            accepted_by=None,
        )
        report = self._write_report(
            workspace=workspace,
            issue=issue,
            run_id=run_id,
            gate=gate,
            builder=builder,
            review=review,
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
            review=review,
            gate=gate,
        )

    def review_issue(
        self,
        issue_id: str,
        *,
        verdict: str,
        reviewed_by: str,
    ) -> RunResult:
        issue = self._load_fixture(issue_id)
        workspace = self.workspace_service.issue_workspace_path(issue.issue_id)
        if not workspace.exists():
            raise FileNotFoundError(f"workspace not found for issue {issue.issue_id}")

        report = workspace / "report.json"
        if not report.exists():
            raise FileNotFoundError(f"report not found for issue {issue.issue_id}")

        report_data = json.loads(report.read_text())
        run_id = report_data["run_id"]
        builder = self._builder_from_report(report_data, workspace)
        verification = self._verification_from_report(report_data)
        review = self.review_adapter.review(
            issue_id=issue.issue_id,
            workspace=workspace,
            verdict=verdict,
            reviewed_by=reviewed_by,
        )
        human_acceptance = report_data["human_acceptance"]["accepted"]
        accepted_by = report_data["human_acceptance"]["accepted_by"]
        gate = self.gate_service.evaluate(
            GateInput(
                spec_exists=True,
                spec_approved=True,
                within_boundaries=True,
                builder_succeeded=builder.succeeded,
                verification=verification,
                review=review,
                human_acceptance=human_acceptance,
            )
        )
        explain = self.artifact_service.write_explain_report(
            workspace=workspace,
            issue_id=issue.issue_id,
            issue_title=issue.title,
            mergeable=gate.mergeable,
            failed_conditions=gate.failed_conditions,
            builder_status=self._builder_status(builder),
            review_status=review.verdict,
            reviewed_by=review.reviewed_by,
            acceptance_status="accepted" if human_acceptance else "pending",
            accepted_by=accepted_by,
        )
        updated_report = self._write_report(
            workspace=workspace,
            issue=issue,
            run_id=run_id,
            gate=gate,
            builder=builder,
            review=review,
            verification=verification,
            accepted_by=accepted_by,
        )
        self.telemetry_service.log_event(
            workspace=workspace,
            run_id=run_id,
            issue_id=issue.issue_id,
            component="review",
            event_type="review_completed",
            message="Recorded review verdict.",
            data={"verdict": verdict, "reviewed_by": reviewed_by},
        )

        return RunResult(
            issue=issue,
            workspace=workspace,
            task_spec=workspace / "task.spec.md",
            progress=workspace / "progress.md",
            explain=explain,
            report=updated_report,
            builder=builder,
            review=review,
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
        run_id = report_data["run_id"]
        self.artifact_service.write_acceptance_artifact(
            workspace=workspace,
            issue_id=issue.issue_id,
            accepted_by=accepted_by,
        )
        builder = self._builder_from_report(report_data, workspace)
        verification = self._verification_from_report(report_data)
        review = self._review_from_report(report_data, workspace)
        gate = self.gate_service.evaluate(
            GateInput(
                spec_exists=True,
                spec_approved=True,
                within_boundaries=True,
                builder_succeeded=builder.succeeded,
                verification=verification,
                review=review,
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
            review_status=review.verdict,
            reviewed_by=review.reviewed_by,
            acceptance_status="accepted",
            accepted_by=accepted_by,
        )
        updated_report = self._write_report(
            workspace=workspace,
            issue=issue,
            run_id=run_id,
            gate=gate,
            builder=builder,
            review=review,
            verification=verification,
            accepted_by=accepted_by,
        )
        self.telemetry_service.log_event(
            workspace=workspace,
            run_id=run_id,
            issue_id=issue.issue_id,
            component="acceptance",
            event_type="acceptance_recorded",
            message="Recorded human acceptance.",
            data={"accepted_by": accepted_by},
        )

        return RunResult(
            issue=issue,
            workspace=workspace,
            task_spec=workspace / "task.spec.md",
            progress=workspace / "progress.md",
            explain=explain,
            report=updated_report,
            builder=builder,
            review=review,
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

    def _run_builder(self, *, issue: Issue, workspace: Path, run_id: str) -> BuilderResult:
        self.telemetry_service.log_event(
            workspace=workspace,
            run_id=run_id,
            issue_id=issue.issue_id,
            component="builder",
            event_type="builder_started",
            message="Started builder adapter.",
            adapter=self.harness_builder_adapter.ADAPTER_NAME,
            agent=self.harness_builder_adapter.AGENT_NAME,
        )
        try:
            builder = self.harness_builder_adapter.run(issue=issue, workspace=workspace)
        except CodexHarnessTransportError as exc:
            self.telemetry_service.log_event(
                workspace=workspace,
                run_id=run_id,
                issue_id=issue.issue_id,
                component="builder",
                event_type="builder_fallback",
                severity="warning",
                message="Falling back from codex harness to pi.",
                adapter=self.pi_builder_adapter.ADAPTER_NAME,
                agent=self.pi_builder_adapter.AGENT_NAME,
                data={"reason": str(exc)},
            )
            builder = self.pi_builder_adapter.run(
                issue=issue,
                workspace=workspace,
                run_id=run_id,
            )
            builder.metadata["fallback_from"] = CodexHarnessBuilderAdapter.ADAPTER_NAME
            builder.metadata["fallback_reason"] = str(exc)
            self.pi_builder_adapter._write_report(builder)
        builder.metadata["run_id"] = run_id
        if builder.adapter == self.harness_builder_adapter.ADAPTER_NAME:
            self.harness_builder_adapter._write_report(builder)
        if builder.adapter == self.pi_builder_adapter.ADAPTER_NAME:
            self.pi_builder_adapter._write_report(builder)
        self.telemetry_service.log_event(
            workspace=workspace,
            run_id=run_id,
            issue_id=issue.issue_id,
            component="builder",
            event_type="builder_completed",
            severity="info" if builder.succeeded else "error",
            message="Builder adapter completed.",
            adapter=builder.adapter,
            agent=builder.agent,
            data={"succeeded": builder.succeeded, "skipped": builder.skipped},
        )
        return builder

    def _builder_from_report(self, report_data: dict, workspace: Path) -> BuilderResult:
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
            metadata=builder_data.get("metadata", {}),
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

    def _review_from_report(self, report_data: dict, workspace: Path) -> ReviewSummary:
        review_data = report_data["review"]
        return ReviewSummary(
            verdict=review_data["verdict"],
            reviewed_by=review_data.get("reviewed_by"),
            report_path=workspace / "review_report.json",
        )

    def _write_report(
        self,
        *,
        workspace: Path,
        issue: Issue,
        run_id: str,
        gate,
        builder: BuilderResult,
        review: ReviewSummary,
        verification: VerificationSummary,
        accepted_by: str | None,
    ) -> Path:
        report = workspace / "report.json"
        report.write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "issue_id": issue.issue_id,
                    "title": issue.title,
                    "mergeable": gate.mergeable,
                    "failed_conditions": gate.failed_conditions,
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
                indent=2,
            )
            + "\n"
        )
        return report
