import json
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
    assert "builder" not in result.gate.failed_conditions
    assert "verification" in result.gate.failed_conditions
    assert "review" in result.gate.failed_conditions
    assert "human_acceptance" in result.explain.read_text()
    assert '"adapter": "pi_codex"' in result.report.read_text()
    assert '"agent": "codex"' in result.report.read_text()


def test_review_and_accept_issue_recompute_gate_and_update_artifacts(tmp_path: Path) -> None:
    fixtures_dir = tmp_path / "fixtures" / "issues"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "SPC-5.json").write_text(
        json.dumps(
            {
                "issue_id": "SPC-5",
                "title": "Acceptance flow",
                "summary": "Turn a passing run into mergeable after acceptance.",
                "verification_commands": {
                    "lint": ["{python}", "-c", "print('lint ok')"],
                    "typecheck": ["{python}", "-c", "print('type ok')"],
                    "test": ["{python}", "-c", "print('test ok')"],
                    "build": ["{python}", "-c", "print('build ok')"],
                },
            }
        )
    )
    controller = RunController(repo_root=tmp_path)

    initial = controller.run_issue("SPC-5")
    reviewed = controller.review_issue(
        "SPC-5",
        verdict="pass",
        reviewed_by="claude",
    )
    accepted = controller.accept_issue("SPC-5", accepted_by="chris")

    assert initial.gate.mergeable is False
    assert reviewed.gate.mergeable is False
    assert reviewed.gate.failed_conditions == ["human_acceptance"]
    assert (reviewed.workspace / "review_report.json").exists()
    assert '"reviewed_by": "claude"' in (reviewed.workspace / "report.json").read_text()
    assert "review_status=pass" in reviewed.explain.read_text()
    assert accepted.gate.mergeable is True
    assert accepted.gate.failed_conditions == []
    assert (accepted.workspace / "acceptance.json").exists()
    assert '"accepted_by": "chris"' in (accepted.workspace / "report.json").read_text()
    assert "acceptance_status=accepted" in accepted.explain.read_text()
