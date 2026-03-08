from __future__ import annotations

import json
from pathlib import Path

from spec_orch.domain.models import Issue
from spec_orch.services.pi_codex_builder_adapter import PiCodexBuilderAdapter


def test_pi_codex_builder_adapter_runs_codex_contract_in_workspace(tmp_path: Path) -> None:
    fake_pi = tmp_path / "fake-pi"
    fake_pi.write_text(
        "\n".join(
            [
                "#!/bin/sh",
                "printf '%s\n' \"$@\" > builder-args.txt",
                "env | grep '^SPEC_ORCH_' | sort > builder-env.txt",
                "echo 'builder ok'",
            ]
        )
        + "\n"
    )
    fake_pi.chmod(0o755)

    adapter = PiCodexBuilderAdapter(executable=str(fake_pi))
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
    assert result.report_path.exists()
    report_data = json.loads(result.report_path.read_text())
    assert report_data["succeeded"] is True
    assert report_data["adapter"] == "pi_codex"
    assert report_data["agent"] == "codex"
    assert "Implement the issue in this workspace." in (tmp_path / "builder-args.txt").read_text()
    env_text = (tmp_path / "builder-env.txt").read_text()
    assert "SPEC_ORCH_BUILDER_ADAPTER=pi_codex" in env_text
    assert "SPEC_ORCH_BUILDER_AGENT=codex" in env_text
