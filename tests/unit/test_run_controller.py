import json
from pathlib import Path

import pytest

from spec_orch.domain.models import (
    BuilderResult,
    RunState,
    validate_transition,
)
from spec_orch.services.run_controller import RunController


def test_run_controller_executes_local_fixture_issue(tmp_path: Path) -> None:
    fixtures_dir = tmp_path / "fixtures" / "issues"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "SPC-1.json").write_text(
        json.dumps(
            {
                "issue_id": "SPC-1",
                "title": "Build MVP runner",
                "summary": "Run one local fixture issue through the prototype pipeline.",
            }
        )
    )
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
    assert '"adapter": "codex_exec"' in result.report.read_text()
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


def test_run_controller_keeps_builder_failure_when_executable_is_unavailable(
    tmp_path: Path,
) -> None:
    fixtures_dir = tmp_path / "fixtures" / "issues"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "SPC-21.json").write_text(
        json.dumps(
            {
                "issue_id": "SPC-21",
                "title": "Unavailable builder",
                "summary": "Keep the builder failure when the executable is unavailable.",
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
    assert result.builder.adapter == "codex_exec"
    assert result.builder.agent == "codex"
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
    assert any(
        event["event_type"] == "builder_completed"
        and event["adapter"] == "codex_exec"
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
    assert "| review | pass |" in reviewed.explain.read_text()
    assert accepted.gate.mergeable is True
    assert accepted.gate.failed_conditions == []
    assert (accepted.workspace / "acceptance.json").exists()
    assert '"accepted_by": "chris"' in (accepted.workspace / "report.json").read_text()
    assert "| human_acceptance | accepted |" in accepted.explain.read_text()
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


def test_run_issue_closes_activity_logger_on_exception(tmp_path: Path) -> None:
    fixtures_dir = tmp_path / "fixtures" / "issues"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "SPC-ERR.json").write_text(
        json.dumps(
            {
                "issue_id": "SPC-ERR",
                "title": "Run logger cleanup",
                "summary": "Close the logger when verification fails.",
            }
        )
    )
    controller = RunController(repo_root=tmp_path)
    logger = _TrackingActivityLogger()

    controller._open_activity_logger = lambda _workspace: logger
    controller.verification_service.run = _raise_runtime_error

    with pytest.raises(RuntimeError, match="boom"):
        controller.run_issue("SPC-ERR")

    assert logger.entered is True
    assert logger.exited is True
    assert logger.closed is True


def test_rerun_issue_closes_activity_logger_on_exception(tmp_path: Path) -> None:
    fixtures_dir = tmp_path / "fixtures" / "issues"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "SPC-RERR.json").write_text(
        json.dumps(
            {
                "issue_id": "SPC-RERR",
                "title": "Rerun logger cleanup",
                "summary": "Close the logger when rerun verification fails.",
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
    controller.builder_adapter = _PassingBuilderAdapter()
    controller.run_issue("SPC-RERR")
    logger = _TrackingActivityLogger()

    controller._open_activity_logger = lambda _workspace: logger
    controller.verification_service.run = _raise_runtime_error

    with pytest.raises(RuntimeError, match="boom"):
        controller.rerun_issue("SPC-RERR")

    assert logger.entered is True
    assert logger.exited is True
    assert logger.closed is True


def test_run_issue_persists_state_in_report(tmp_path: Path) -> None:
    fixtures_dir = tmp_path / "fixtures" / "issues"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "SPC-S1.json").write_text(
        json.dumps({
            "issue_id": "SPC-S1",
            "title": "State tracking",
            "summary": "Verify state is persisted.",
        })
    )
    controller = RunController(repo_root=tmp_path)
    result = controller.run_issue("SPC-S1")

    report_data = json.loads(result.report.read_text())
    assert report_data["state"] == "gate_evaluated"
    assert result.state == RunState.GATE_EVALUATED


def test_accept_issue_sets_accepted_state(tmp_path: Path) -> None:
    fixtures_dir = tmp_path / "fixtures" / "issues"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "SPC-S2.json").write_text(
        json.dumps({
            "issue_id": "SPC-S2",
            "title": "Acceptance state",
            "summary": "Verify accept sets ACCEPTED state.",
            "verification_commands": {
                "lint": ["{python}", "-c", "print('ok')"],
                "typecheck": ["{python}", "-c", "print('ok')"],
                "test": ["{python}", "-c", "print('ok')"],
                "build": ["{python}", "-c", "print('ok')"],
            },
        })
    )
    controller = RunController(repo_root=tmp_path)
    controller.run_issue("SPC-S2")
    controller.review_issue("SPC-S2", verdict="pass", reviewed_by="bot")
    accepted = controller.accept_issue("SPC-S2", accepted_by="chris")

    report_data = json.loads(accepted.report.read_text())
    assert report_data["state"] == "accepted"
    assert accepted.state == RunState.ACCEPTED


def test_get_state_returns_draft_for_unknown_issue(tmp_path: Path) -> None:
    fixtures_dir = tmp_path / "fixtures" / "issues"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "SPC-GHOST.json").write_text(
        json.dumps({
            "issue_id": "SPC-GHOST",
            "title": "Ghost",
            "summary": "No run yet.",
        })
    )
    controller = RunController(repo_root=tmp_path)
    assert controller.get_state("SPC-GHOST") == RunState.DRAFT


def test_get_state_returns_persisted_state(tmp_path: Path) -> None:
    fixtures_dir = tmp_path / "fixtures" / "issues"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "SPC-GS.json").write_text(
        json.dumps({
            "issue_id": "SPC-GS",
            "title": "State read",
            "summary": "Check get_state after run.",
        })
    )
    controller = RunController(repo_root=tmp_path)
    controller.run_issue("SPC-GS")
    assert controller.get_state("SPC-GS") == RunState.GATE_EVALUATED


def test_validate_transition_rejects_illegal_move() -> None:
    with pytest.raises(ValueError, match="Invalid state transition"):
        validate_transition(RunState.DRAFT, RunState.ACCEPTED)


def test_validate_transition_accepts_legal_move() -> None:
    validate_transition(RunState.DRAFT, RunState.BUILDING)
    validate_transition(RunState.GATE_EVALUATED, RunState.ACCEPTED)
    validate_transition(RunState.BUILDING, RunState.VERIFYING)


def _read_events(events_path: Path) -> list[dict]:
    return [json.loads(line) for line in events_path.read_text().splitlines()]


class _TrackingActivityLogger:
    def __init__(self) -> None:
        self.entered = False
        self.exited = False
        self.closed = False

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, *exc: object) -> None:
        self.exited = True
        self.close()

    def log(self, _event: dict) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class _PassingBuilderAdapter:
    ADAPTER_NAME = "passing_builder"
    AGENT_NAME = "codex"

    def run(self, **_kwargs) -> BuilderResult:
        return BuilderResult(
            succeeded=True,
            command=[],
            stdout="",
            stderr="",
            report_path=Path("builder_report.json"),
            adapter=self.ADAPTER_NAME,
            agent=self.AGENT_NAME,
            metadata={},
        )


def _raise_runtime_error(**_kwargs):
    raise RuntimeError("boom")
