from __future__ import annotations

from pathlib import Path

from spec_orch.domain.models import Issue
from spec_orch.services.verification_service import VerificationService


def test_verification_service_executes_configured_commands(tmp_path: Path) -> None:
    service = VerificationService()
    issue = Issue(
        issue_id="SPC-9",
        title="Run verification",
        summary="Execute configured commands.",
        verification_commands={
            "lint": ["{python}", "-c", "print('lint ok')"],
            "typecheck": ["{python}", "-c", "print('type ok')"],
            "test": ["{python}", "-c", "raise SystemExit(1)"],
            "build": ["{python}", "-c", "print('build ok')"],
        },
    )

    result = service.run(issue=issue, workspace=tmp_path)

    assert result.lint_passed is True
    assert result.typecheck_passed is True
    assert result.test_passed is False
    assert result.build_passed is True
    assert result.all_passed is False
    assert result.details["test"].exit_code == 1


def test_verification_service_handles_missing_command(tmp_path: Path) -> None:
    service = VerificationService()
    issue = Issue(
        issue_id="SPC-10",
        title="Missing command",
        summary="Command binary does not exist.",
        verification_commands={
            "lint": ["__nonexistent_binary_42__", "--check"],
        },
    )

    result = service.run(issue=issue, workspace=tmp_path)

    assert result.lint_passed is False
    assert result.details["lint"].exit_code == 127
    assert "command not found" in result.details["lint"].stderr
