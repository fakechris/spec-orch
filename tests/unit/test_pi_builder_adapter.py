from __future__ import annotations

from pathlib import Path

from spec_orch.domain.models import Issue
from spec_orch.services.pi_builder_adapter import PiBuilderAdapter


def test_pi_builder_adapter_runs_cli_in_workspace(tmp_path: Path) -> None:
    fake_pi = tmp_path / "fake-pi"
    fake_pi.write_text(
        "\n".join(
            [
                "#!/bin/sh",
                "printf '%s\n' \"$@\" > builder-args.txt",
                "echo 'builder ok'",
            ]
        )
        + "\n"
    )
    fake_pi.chmod(0o755)

    adapter = PiBuilderAdapter(executable=str(fake_pi))
    issue = Issue(
        issue_id="SPC-10",
        title="Run builder",
        summary="Execute pi in workspace.",
        builder_prompt="Implement the issue in this workspace.",
    )

    result = adapter.run(issue=issue, workspace=tmp_path)

    assert result.succeeded is True
    assert result.command[0] == str(fake_pi)
    assert "-p" in result.command
    assert "builder ok" in result.stdout
    assert "Implement the issue in this workspace." in (tmp_path / "builder-args.txt").read_text()
