from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from spec_orch.domain.models import Issue, VerificationDetail, VerificationSummary

_DEFAULT_VERIFICATION_TIMEOUT_S = 600


class VerificationService:
    STANDARD_STEPS = ("lint", "typecheck", "test", "build")

    def run(self, *, issue: Issue, workspace: Path) -> VerificationSummary:
        summary = VerificationSummary()

        step_names = list(issue.verification_commands.keys()) or list(self.STANDARD_STEPS)

        for step_name in step_names:
            command = issue.verification_commands.get(step_name)
            if not command:
                summary.details[step_name] = VerificationDetail(
                    command=[],
                    exit_code=0,
                    stdout="",
                    stderr="not configured — skipped",
                )
                summary.set_step_outcome(step_name, "skipped")
                continue

            resolved_command = [self._resolve_token(token) for token in command]
            try:
                result = subprocess.run(
                    resolved_command,
                    cwd=workspace,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=_DEFAULT_VERIFICATION_TIMEOUT_S,
                )
            except FileNotFoundError:
                summary.details[step_name] = VerificationDetail(
                    command=resolved_command,
                    exit_code=127,
                    stdout="",
                    stderr=f"command not found: {resolved_command[0]}",
                )
                summary.set_step_passed(step_name, False)
                continue
            except subprocess.TimeoutExpired:
                summary.details[step_name] = VerificationDetail(
                    command=resolved_command,
                    exit_code=124,
                    stdout="",
                    stderr=f"command timed out after {_DEFAULT_VERIFICATION_TIMEOUT_S}s",
                )
                summary.set_step_passed(step_name, False)
                continue
            summary.details[step_name] = VerificationDetail(
                command=resolved_command,
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )
            summary.set_step_passed(step_name, result.returncode == 0)

        return summary

    def _resolve_token(self, token: str) -> str:
        if token == "{python}":
            return sys.executable
        return token
