from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from spec_orch.domain.compliance import (
    default_turn_contract_compliance,
    evaluate_pre_action_narration_compliance,
)
from spec_orch.domain.models import (
    BuilderResult,
    GateInput,
    GateVerdict,
    Issue,
    ReviewSummary,
    RunResult,
    VerificationDetail,
    VerificationSummary,
)
from spec_orch.domain.protocols import BuilderAdapter, IssueSource
from spec_orch.services.artifact_service import ArtifactService
from spec_orch.services.codex_exec_builder_adapter import CodexExecBuilderAdapter
from spec_orch.services.fixture_issue_source import FixtureIssueSource
from spec_orch.services.gate_service import GateService
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
        builder_adapter: BuilderAdapter | None = None,
        issue_source: IssueSource | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.artifact_service = ArtifactService()
        self.builder_adapter: BuilderAdapter = builder_adapter or CodexExecBuilderAdapter(
            executable=codex_executable
        )
        self.gate_service = GateService()
        self.review_adapter = LocalReviewAdapter()
        self.telemetry_service = TelemetryService()
        self.verification_service = VerificationService()
        self.workspace_service = WorkspaceService(repo_root=self.repo_root)
        self.issue_source: IssueSource = issue_source or FixtureIssueSource(
            repo_root=self.repo_root
        )

    def run_issue(self, issue_id: str) -> RunResult:
        issue = self.issue_source.load(issue_id)
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
        self.telemetry_service.log_event(
            workspace=workspace,
            run_id=run_id,
            issue_id=issue.issue_id,
            component="verification",
            event_type="verification_started",
            message="Started verification steps.",
        )
        verification = self.verification_service.run(issue=issue, workspace=workspace)
        self._log_verification_events(
            workspace=workspace,
            issue_id=issue.issue_id,
            run_id=run_id,
            verification=verification,
        )
        review = self.review_adapter.initialize(
            issue_id=issue.issue_id,
            workspace=workspace,
            builder_turn_contract_compliance=builder.metadata.get(
                "turn_contract_compliance"
            ),
        )
        self.telemetry_service.log_event(
            workspace=workspace,
            run_id=run_id,
            issue_id=issue.issue_id,
            component="review",
            event_type="review_initialized",
            message="Initialized local review state.",
            data={"verdict": review.verdict},
        )

        gate, explain, report = self._finalize_run(
            issue=issue,
            workspace=workspace,
            run_id=run_id,
            builder=builder,
            verification=verification,
            review=review,
            human_acceptance=False,
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
        issue = self.issue_source.load(issue_id)
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
            builder_turn_contract_compliance=builder.metadata.get(
                "turn_contract_compliance"
            ),
        )
        human_acceptance = report_data["human_acceptance"]["accepted"]
        accepted_by = report_data["human_acceptance"]["accepted_by"]
        gate, explain, updated_report = self._finalize_run(
            issue=issue,
            workspace=workspace,
            run_id=run_id,
            builder=builder,
            verification=verification,
            review=review,
            human_acceptance=human_acceptance,
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
        issue = self.issue_source.load(issue_id)
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
        gate, explain, updated_report = self._finalize_run(
            issue=issue,
            workspace=workspace,
            run_id=run_id,
            builder=builder,
            verification=verification,
            review=review,
            human_acceptance=True,
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

    def _make_event_logger(
        self, *, workspace: Path, run_id: str, issue_id: str
    ) -> Callable[[dict[str, Any]], None]:
        def _log(event: dict[str, Any]) -> None:
            self.telemetry_service.log_event(
                workspace=workspace,
                run_id=run_id,
                issue_id=issue_id,
                component=event.get("component", "builder"),
                event_type=event["event_type"],
                severity=event.get("severity", "info"),
                message=event["message"],
                adapter=event.get("adapter"),
                agent=event.get("agent"),
                data=event.get("data"),
            )
        return _log

    def _finalize_run(
        self,
        *,
        issue: Issue,
        workspace: Path,
        run_id: str,
        builder: BuilderResult,
        verification: VerificationSummary,
        review: ReviewSummary,
        human_acceptance: bool,
        accepted_by: str | None,
    ) -> tuple[GateVerdict, Path, Path]:
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
        self._log_gate_event(
            workspace=workspace,
            issue_id=issue.issue_id,
            run_id=run_id,
            gate=gate,
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
            builder_contract_compliance=builder.metadata.get("turn_contract_compliance"),
            builder_adapter=builder.adapter,
            verification=verification,
            acceptance_criteria=issue.acceptance_criteria,
        )
        report = self._write_report(
            workspace=workspace,
            issue=issue,
            run_id=run_id,
            gate=gate,
            builder=builder,
            review=review,
            verification=verification,
            accepted_by=accepted_by,
        )
        return gate, explain, report

    def _builder_status(self, builder) -> str:
        if builder.skipped:
            return "skipped"
        if builder.succeeded:
            return "passed"
        return "failed"

    def _run_builder(self, *, issue: Issue, workspace: Path, run_id: str) -> BuilderResult:
        adapter_name = self.builder_adapter.ADAPTER_NAME
        agent_name = self.builder_adapter.AGENT_NAME
        self.telemetry_service.log_event(
            workspace=workspace,
            run_id=run_id,
            issue_id=issue.issue_id,
            component="builder",
            event_type="builder_started",
            message="Started builder adapter.",
            adapter=adapter_name,
            agent=agent_name,
        )
        try:
            builder = self.builder_adapter.run(
                issue=issue,
                workspace=workspace,
                run_id=run_id,
                event_logger=self._make_event_logger(
                    workspace=workspace, run_id=run_id, issue_id=issue.issue_id
                ),
            )
        except Exception as exc:
            compliance = evaluate_pre_action_narration_compliance(
                workspace / "telemetry" / "incoming_events.jsonl"
            )
            command = getattr(self.builder_adapter, "command", [])
            builder = BuilderResult(
                succeeded=False,
                command=command,
                stdout="",
                stderr=str(exc),
                report_path=workspace / "builder_report.json",
                adapter=adapter_name,
                agent=agent_name,
                metadata={
                    "run_id": run_id,
                    "failure_reason": str(exc),
                    "turn_contract_compliance": compliance,
                },
            )
        builder.metadata.setdefault(
            "turn_contract_compliance", default_turn_contract_compliance()
        )
        builder.metadata["run_id"] = run_id
        from spec_orch.services.codex_exec_builder_adapter import (
            _write_report as write_builder_report,
        )

        if builder.adapter == adapter_name:
            write_builder_report(builder)
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

    def _log_verification_events(
        self,
        *,
        workspace: Path,
        issue_id: str,
        run_id: str,
        verification: VerificationSummary,
    ) -> None:
        for step_name, detail in verification.details.items():
            self.telemetry_service.log_event(
                workspace=workspace,
                run_id=run_id,
                issue_id=issue_id,
                component="verification",
                event_type="verification_step_completed",
                severity="info" if detail.exit_code == 0 else "error",
                message=f"Verification step completed: {step_name}",
                data={
                    "step": step_name,
                    "exit_code": detail.exit_code,
                    "command": detail.command,
                },
            )

        self.telemetry_service.log_event(
            workspace=workspace,
            run_id=run_id,
            issue_id=issue_id,
            component="verification",
            event_type="verification_completed",
            severity="info" if verification.all_passed else "warning",
            message="Completed verification steps.",
            data={"all_passed": verification.all_passed},
        )

    def _log_gate_event(self, *, workspace: Path, issue_id: str, run_id: str, gate) -> None:
        self.telemetry_service.log_event(
            workspace=workspace,
            run_id=run_id,
            issue_id=issue_id,
            component="gate",
            event_type="gate_evaluated",
            severity="info" if gate.mergeable else "warning",
            message="Evaluated gate verdict.",
            data={
                "mergeable": gate.mergeable,
                "failed_conditions": gate.failed_conditions,
            },
        )

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
            metadata={
                **builder_data.get("metadata", {}),
                "turn_contract_compliance": builder_data.get("metadata", {}).get(
                    "turn_contract_compliance", default_turn_contract_compliance()
                ),
            },
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
