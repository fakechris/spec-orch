from pathlib import Path

from spec_orch.domain.models import VerificationDetail, VerificationSummary
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


def test_artifact_service_distinguishes_failed_and_skipped_verification_steps() -> None:
    verification = VerificationSummary()
    verification.details["lint"] = VerificationDetail(
        command=["ruff"],
        exit_code=1,
        stdout="",
        stderr="lint failed",
    )
    verification.details["build"] = VerificationDetail(
        command=["npm", "run", "build"],
        exit_code=0,
        stdout="",
        stderr="build skipped",
    )
    verification.set_step_outcome("lint", "fail")
    verification.set_step_outcome("build", "skipped")

    focus = ArtifactService()._compute_review_focus(
        builder_status="passed",
        verification=verification,
        compliance={"compliant": True},
    )

    assert "Verification step 'lint' failed" in focus
    assert "Verification step 'build' skipped" in focus
