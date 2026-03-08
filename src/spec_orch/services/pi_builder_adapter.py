from __future__ import annotations

import subprocess
from pathlib import Path

from spec_orch.domain.models import BuilderResult, Issue


class PiBuilderAdapter:
    def __init__(self, *, executable: str = "pi") -> None:
        self.executable = executable

    def run(self, *, issue: Issue, workspace: Path) -> BuilderResult:
        if not issue.builder_prompt:
            return BuilderResult(
                succeeded=True,
                command=[],
                stdout="",
                stderr="",
                skipped=True,
            )

        command = [self.executable, "-p", issue.builder_prompt]
        result = subprocess.run(
            command,
            cwd=workspace,
            check=False,
            capture_output=True,
            text=True,
        )
        return BuilderResult(
            succeeded=result.returncode == 0,
            command=command,
            stdout=result.stdout,
            stderr=result.stderr,
        )
