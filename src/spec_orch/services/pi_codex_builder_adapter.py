from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from spec_orch.domain.models import BuilderResult, Issue


class PiCodexBuilderAdapter:
    ADAPTER_NAME = "pi_codex"
    AGENT_NAME = "codex"

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
                adapter=self.ADAPTER_NAME,
                agent=self.AGENT_NAME,
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
            env=self._build_env(issue),
        )
        result = BuilderResult(
            succeeded=process.returncode == 0,
            command=command,
            stdout=process.stdout,
            stderr=process.stderr,
            report_path=report_path,
            adapter=self.ADAPTER_NAME,
            agent=self.AGENT_NAME,
        )
        self._write_report(result)
        return result

    def _build_env(self, issue: Issue) -> dict[str, str]:
        env = dict(os.environ)
        env.update(
            {
                "SPEC_ORCH_BUILDER_ADAPTER": self.ADAPTER_NAME,
                "SPEC_ORCH_BUILDER_AGENT": self.AGENT_NAME,
                "SPEC_ORCH_ISSUE_ID": issue.issue_id,
            }
        )
        return env

    def _write_report(self, result: BuilderResult) -> None:
        result.report_path.write_text(
            json.dumps(
                {
                    "succeeded": result.succeeded,
                    "skipped": result.skipped,
                    "command": result.command,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "adapter": result.adapter,
                    "agent": result.agent,
                },
                indent=2,
            )
            + "\n"
        )
