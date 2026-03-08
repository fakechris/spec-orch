from __future__ import annotations

import json
import subprocess
from pathlib import Path

from spec_orch.domain.models import BuilderResult, Issue


class PiBuilderAdapter:
    def __init__(self, *, executable: str = "pi") -> None:
        self.executable = executable

    def run(self, *, issue: Issue, workspace: Path) -> BuilderResult:
        report_path = workspace / "builder_report.json"
        if not issue.builder_prompt:
            result = BuilderResult(
                succeeded=True,
                command=[],
                stdout="",
                stderr="",
                report_path=report_path,
                skipped=True,
            )
            self._write_report(result)
            return result

        command = [self.executable, "-p", issue.builder_prompt]
        process = subprocess.run(
            command,
            cwd=workspace,
            check=False,
            capture_output=True,
            text=True,
        )
        result = BuilderResult(
            succeeded=process.returncode == 0,
            command=command,
            stdout=process.stdout,
            stderr=process.stderr,
            report_path=report_path,
        )
        self._write_report(result)
        return result

    def _write_report(self, result: BuilderResult) -> None:
        result.report_path.write_text(
            json.dumps(
                {
                    "succeeded": result.succeeded,
                    "skipped": result.skipped,
                    "command": result.command,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                },
                indent=2,
            )
            + "\n"
        )
