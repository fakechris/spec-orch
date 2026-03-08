from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from spec_orch.domain.models import Issue, VerificationDetail, VerificationSummary


class VerificationService:
    STEP_NAMES = ("lint", "typecheck", "test", "build")

    def run(self, *, issue: Issue, workspace: Path) -> VerificationSummary:
        summary = VerificationSummary()

        for step_name in self.STEP_NAMES:
            command = issue.verification_commands.get(step_name)
            if not command:
                summary.details[step_name] = VerificationDetail(
                    command=[],
                    exit_code=-1,
                    stdout="",
                    stderr="not configured",
                )
                continue

            resolved_command = [self._resolve_token(token) for token in command]
            result = subprocess.run(
                resolved_command,
                cwd=workspace,
                check=False,
                capture_output=True,
                text=True,
            )
            summary.details[step_name] = VerificationDetail(
                command=resolved_command,
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )
            passed = result.returncode == 0
            setattr(summary, f"{step_name}_passed", passed)

        return summary

    def _resolve_token(self, token: str) -> str:
        if token == "{python}":
            return sys.executable
        return token
