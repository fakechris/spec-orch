from __future__ import annotations

import json
from pathlib import Path

from spec_orch.domain.models import (
    GateInput,
    Issue,
    ReviewSummary,
    RunResult,
    VerificationSummary,
)
from spec_orch.services.artifact_service import ArtifactService
from spec_orch.services.gate_service import GateService


class RunController:
    def __init__(self, *, repo_root: Path) -> None:
        self.repo_root = Path(repo_root)
        self.artifact_service = ArtifactService()
        self.gate_service = GateService()

    def run_issue(self, issue_id: str) -> RunResult:
        issue = self._load_fixture(issue_id)
        workspace = self.repo_root / ".spec_orch_runs" / issue.issue_id
        workspace.mkdir(parents=True, exist_ok=True)

        task_spec, progress = self.artifact_service.write_initial_artifacts(
            workspace=workspace,
            issue_id=issue.issue_id,
            issue_title=issue.title,
        )

        gate = self.gate_service.evaluate(
            GateInput(
                spec_exists=True,
                spec_approved=True,
                within_boundaries=True,
                verification=VerificationSummary(
                    lint_passed=True,
                    typecheck_passed=True,
                    test_passed=True,
                    build_passed=True,
                ),
                review=ReviewSummary(verdict="pass"),
                human_acceptance=False,
            )
        )
        report = workspace / "report.json"
        report.write_text(
            json.dumps(
                {
                    "issue_id": issue.issue_id,
                    "title": issue.title,
                    "mergeable": gate.mergeable,
                    "failed_conditions": gate.failed_conditions,
                },
                indent=2,
            )
            + "\n"
        )

        return RunResult(
            issue=issue,
            workspace=workspace,
            task_spec=task_spec,
            progress=progress,
            report=report,
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
            )

        return Issue(
            issue_id=issue_id,
            title="Build MVP runner",
            summary="Local happy-path issue fixture for the first prototype.",
        )
