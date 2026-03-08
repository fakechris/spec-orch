from pathlib import Path

from spec_orch.services.run_controller import RunController


def test_run_controller_executes_local_fixture_issue(tmp_path: Path) -> None:
    controller = RunController(repo_root=tmp_path)

    result = controller.run_issue("SPC-1")

    assert result.issue.issue_id == "SPC-1"
    assert result.workspace.exists()
    assert result.task_spec.exists()
    assert result.progress.exists()
    assert result.explain.exists()
    assert result.report.exists()
    assert result.gate.mergeable is False
    assert "human_acceptance" in result.explain.read_text()
