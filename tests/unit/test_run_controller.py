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
    assert '"adapter": "codex_harness"' in result.report.read_text()
    assert '"agent": "codex"' in result.report.read_text()
    telemetry_dir = result.workspace / "telemetry"
    assert telemetry_dir.exists()
    assert (telemetry_dir / "events.jsonl").exists()
    report_data = json.loads(result.report.read_text())
    assert report_data["run_id"]
    assert report_data["builder"]["metadata"]["run_id"] == report_data["run_id"]
    events = _read_events(telemetry_dir / "events.jsonl")
    assert any(event["event_type"] == "verification_started" for event in events)
    assert any(
        event["event_type"] == "verification_step_completed"
        and event["data"]["step"] == "lint"
        for event in events
    )
    assert any(
        event["event_type"] == "review_initialized"
        and event["data"]["verdict"] == "pending"
        for event in events
    )
    assert any(
        event["event_type"] == "gate_evaluated"
        and event["data"]["mergeable"] is False
        and "verification" in event["data"]["failed_conditions"]
        for event in events
    )


def test_run_controller_keeps_codex_harness_failure_when_app_server_is_unavailable(
    tmp_path: Path,
) -> None:
    fixtures_dir = tmp_path / "fixtures" / "issues"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "SPC-21.json").write_text(
        json.dumps(
            {
                "issue_id": "SPC-21",
                "title": "Unavailable harness",
                "summary": "Keep the codex harness failure when the app-server is unavailable.",
                "builder_prompt": "Implement without fallback.",
                "verification_commands": {
                    "lint": ["{python}", "-c", "print('lint ok')"],
                    "typecheck": ["{python}", "-c", "print('type ok')"],
                    "test": ["{python}", "-c", "print('test ok')"],
                    "build": ["{python}", "-c", "print('build ok')"],
                },
            }
        )
    )

    controller = RunController(
        repo_root=tmp_path,
        codex_executable=str(tmp_path / "missing-codex"),
    )

    result = controller.run_issue("SPC-21")

    assert result.builder.succeeded is False
    assert result.builder.adapter == "codex_harness"
    assert result.builder.agent == "codex"
    assert "missing-codex" in result.builder.stderr
    assert result.builder.metadata["turn_contract_compliance"] == {
        "compliant": True,
        "first_action_seen": False,
        "first_action_method": None,
        "first_action_excerpt": None,
        "violations": [],
    }
    telemetry_dir = result.workspace / "telemetry"
    assert telemetry_dir.exists()
    assert (telemetry_dir / "events.jsonl").exists()
    report_data = json.loads(result.report.read_text())
    assert (
        report_data["builder"]["metadata"]["turn_contract_compliance"]
        == result.builder.metadata["turn_contract_compliance"]
    )
    explain_text = result.explain.read_text()
    assert "builder_contract_compliant=yes" in explain_text
    assert "builder_first_action_seen=no" in explain_text
    assert "builder_contract_violations=0" in explain_text
    events = _read_events(telemetry_dir / "events.jsonl")
    assert not any(event["event_type"] == "builder_fallback" for event in events)
    assert any(
        event["event_type"] == "builder_completed"
        and event["adapter"] == "codex_harness"
        and event["data"]["succeeded"] is False
        for event in events
    )
    assert any(
        event["event_type"] == "gate_evaluated"
        and event["data"]["mergeable"] is False
        and "builder" in event["data"]["failed_conditions"]
        for event in events
    )

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
    review_report = json.loads((reviewed.workspace / "review_report.json").read_text())
    assert (
        review_report["builder_turn_contract_compliance"]
        == initial.builder.metadata["turn_contract_compliance"]
    )
    assert '"reviewed_by": "claude"' in (reviewed.workspace / "report.json").read_text()
    assert "review_status=pass" in reviewed.explain.read_text()
    assert accepted.gate.mergeable is True
    assert accepted.gate.failed_conditions == []
    assert (accepted.workspace / "acceptance.json").exists()
    assert '"accepted_by": "chris"' in (accepted.workspace / "report.json").read_text()
    assert "acceptance_status=accepted" in accepted.explain.read_text()
    telemetry_dir = accepted.workspace / "telemetry"
    assert telemetry_dir.exists()
    events = _read_events(telemetry_dir / "events.jsonl")
    assert any(event["event_type"] == "review_completed" for event in events)
    assert any(event["event_type"] == "acceptance_recorded" for event in events)
    assert any(
        event["event_type"] == "gate_evaluated"
        and event["data"]["mergeable"] is True
        and event["data"]["failed_conditions"] == []
        for event in events
    )


def _read_events(events_path: Path) -> list[dict]:
    return [json.loads(line) for line in events_path.read_text().splitlines()]
