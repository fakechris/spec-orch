from pathlib import Path

from spec_orch.services.artifact_service import ArtifactService


def test_artifact_service_writes_task_spec_and_progress(tmp_path: Path) -> None:
    service = ArtifactService()
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    task_spec, progress = service.write_initial_artifacts(
        workspace=workspace,
        issue_id="SPC-1",
        issue_title="Build MVP runner",
    )

    assert task_spec.exists()
    assert progress.exists()
    assert "Build MVP runner" in task_spec.read_text()
    assert "SPC-1" in progress.read_text()
