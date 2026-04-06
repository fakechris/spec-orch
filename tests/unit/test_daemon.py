from __future__ import annotations

import signal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from spec_orch.domain.models import GateFlowControl, RunState
from spec_orch.services.daemon import DaemonConfig, SpecOrchDaemon
from spec_orch.services.readiness_checker import ReadinessChecker

_COMPLETE_DESC = (
    "## Goal\nDo something.\n\n## Acceptance Criteria\n"
    "- [ ] Done\n\n## Files in Scope\n- `src/x.py`\n"
)


def _init_checker(daemon: SpecOrchDaemon) -> None:
    """Ensure daemon has a ReadinessChecker for tests that call _poll_and_run."""
    if daemon._readiness_checker is None:
        daemon._readiness_checker = ReadinessChecker()


def test_daemon_config_from_toml(tmp_path: Path) -> None:
    toml_file = tmp_path / "spec-orch.toml"
    toml_file.write_text(
        """\
[linear]
token_env = "MY_TOKEN"
team_key = "PROJ"
poll_interval_seconds = 30
issue_filter = "all"

[builder]
adapter = "codex_exec"
codex_executable = "/usr/local/bin/codex"

[daemon]
max_concurrent = 2
lockfile_dir = ".locks/"
"""
    )
    cfg = DaemonConfig.from_toml(toml_file)
    assert cfg.linear_token_env == "MY_TOKEN"
    assert cfg.team_key == "PROJ"
    assert cfg.poll_interval_seconds == 30
    assert cfg.issue_filter == "all"
    assert cfg.codex_executable == "/usr/local/bin/codex"
    assert cfg.max_concurrent == 2
    assert cfg.lockfile_dir == ".locks/"


def test_daemon_config_defaults() -> None:
    cfg = DaemonConfig({})
    assert cfg.linear_token_env == "SPEC_ORCH_LINEAR_TOKEN"
    assert cfg.team_key == "SPC"
    assert cfg.poll_interval_seconds == 60
    assert cfg.builder_adapter == "codex_exec"
    assert cfg.max_concurrent == 1


def test_daemon_lockfile_prevents_reprocessing(tmp_path: Path) -> None:
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)

    assert not daemon._is_locked("SPC-1")
    daemon._claim("SPC-1")
    assert daemon._is_locked("SPC-1")


def test_daemon_signal_stops_loop(tmp_path: Path) -> None:
    cfg = DaemonConfig({})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)

    assert daemon._running is True
    daemon._handle_signal(signal.SIGINT, None)
    assert daemon._running is False


def test_daemon_notify_sends_bell(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cfg = DaemonConfig({})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)

    with patch("spec_orch.services.daemon._subprocess.run") as mock_run:
        daemon._notify("SPC-5", True)

    captured = capsys.readouterr()
    assert "\a" in captured.out
    mock_run.assert_called_once()
    args = mock_run.call_args
    assert "osascript" in args[0][0]


def test_daemon_config_planner_fields(tmp_path: Path) -> None:
    toml_file = tmp_path / "spec-orch.toml"
    toml_file.write_text(
        """\
[planner]
model = "openai/gpt-4o"
api_key_env = "MY_KEY"
api_base_env = "MY_BASE"
token_command = "echo test-token"
"""
    )
    cfg = DaemonConfig.from_toml(toml_file)
    assert cfg.planner_model == "openai/gpt-4o"
    assert cfg.planner_api_key_env == "MY_KEY"
    assert cfg.planner_api_base_env == "MY_BASE"
    assert cfg.planner_token_command == "echo test-token"


def test_daemon_config_planner_defaults() -> None:
    cfg = DaemonConfig({})
    assert cfg.planner_model is None
    assert cfg.planner_api_key_env is None
    assert cfg.planner_api_base_env is None
    assert cfg.planner_token_command is None


def test_build_round_orchestrator_wires_command_visual_evaluator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = DaemonConfig(
        {
            "supervisor": {
                "adapter": "litellm",
                "model": "openai/gpt-4o",
                "visual_evaluator": {
                    "adapter": "command",
                    "command": ["{python}", "tools/visual_eval.py"],
                    "timeout_seconds": 30,
                },
            }
        }
    )
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)

    captured: dict[str, object] = {}

    class StubRoundOrchestrator:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        "spec_orch.services.litellm_supervisor_adapter.LiteLLMSupervisorAdapter",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        "spec_orch.services.round_orchestrator.RoundOrchestrator",
        StubRoundOrchestrator,
    )

    orchestrator = daemon._build_round_orchestrator()

    assert isinstance(orchestrator, StubRoundOrchestrator)
    visual_evaluator = captured["visual_evaluator"]
    assert visual_evaluator is not None
    assert visual_evaluator.__class__.__name__ == "CommandVisualEvaluator"


def test_build_round_orchestrator_wires_acceptance_evaluator_and_filer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "spec_orch.services.daemon.LinearClient",
        lambda **kwargs: object(),
    )
    cfg = DaemonConfig(
        {
            "linear": {"team_key": "SON"},
            "supervisor": {
                "adapter": "litellm",
                "model": "openai/gpt-4o",
            },
            "acceptance_evaluator": {
                "adapter": "litellm",
                "model": "minimax/MiniMax-M2.7-highspeed",
                "auto_file_issues": True,
                "min_confidence": 0.91,
                "min_severity": "critical",
            },
        }
    )
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)

    captured: dict[str, object] = {}

    class StubRoundOrchestrator:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    captured_supervisor: dict[str, object] = {}
    captured_acceptance: dict[str, object] = {}

    monkeypatch.setattr(
        "spec_orch.services.litellm_supervisor_adapter.LiteLLMSupervisorAdapter",
        lambda **kwargs: captured_supervisor.update(kwargs) or object(),
    )
    monkeypatch.setattr(
        "spec_orch.services.acceptance.litellm_acceptance_evaluator.LiteLLMAcceptanceEvaluator",
        lambda **kwargs: captured_acceptance.update(kwargs) or object(),
    )
    monkeypatch.setattr(
        "spec_orch.services.acceptance.linear_filing.LinearAcceptanceFiler",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        "spec_orch.services.round_orchestrator.RoundOrchestrator",
        StubRoundOrchestrator,
    )

    orchestrator = daemon._build_round_orchestrator()

    assert isinstance(orchestrator, StubRoundOrchestrator)
    assert captured["acceptance_evaluator"] is not None
    assert captured["acceptance_filer"] is not None
    assert captured_supervisor["api_type"] == "anthropic"
    assert captured_acceptance["api_type"] == "anthropic"


def test_sync_linear_mirror_for_mission_uses_write_back_service(tmp_path: Path) -> None:
    cfg = DaemonConfig({})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)
    daemon._write_back = MagicMock()
    client = MagicMock()
    client.query.return_value = {"issue": {"description": "fresh description"}}

    raw_issue = {"id": "issue-1", "description": "mission: plan-sync"}

    daemon._sync_linear_mirror_for_mission(
        client=client,
        raw_issue=raw_issue,
        mission_id="plan-sync",
    )

    client.query.assert_called_once()
    daemon._write_back.sync_issue_mirror_from_mission.assert_called_once_with(
        repo_root=tmp_path,
        mission_id="plan-sync",
        linear_id="issue-1",
        current_description="fresh description",
    )


def test_build_round_orchestrator_passes_acpx_worker_robustness_knobs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = DaemonConfig(
        {
            "builder": {
                "adapter": "acpx_opencode",
                "startup_timeout_seconds": 17,
                "idle_progress_timeout_seconds": 45,
                "completion_quiet_period_seconds": 3,
                "max_retries": 2,
                "max_turns_per_session": 7,
                "max_session_age_seconds": 900,
            },
            "supervisor": {
                "adapter": "litellm",
                "model": "openai/gpt-4o",
            },
        }
    )
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)

    captured_orchestrator: dict[str, object] = {}
    captured_factory: dict[str, object] = {}

    class StubRoundOrchestrator:
        def __init__(self, **kwargs):
            captured_orchestrator.update(kwargs)

    monkeypatch.setattr(
        "spec_orch.services.litellm_supervisor_adapter.LiteLLMSupervisorAdapter",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        "spec_orch.services.workers.acpx_worker_handle_factory.AcpxWorkerHandleFactory",
        lambda **kwargs: captured_factory.update(kwargs) or object(),
    )
    monkeypatch.setattr(
        "spec_orch.services.round_orchestrator.RoundOrchestrator",
        StubRoundOrchestrator,
    )

    orchestrator = daemon._build_round_orchestrator()

    assert isinstance(orchestrator, StubRoundOrchestrator)
    assert captured_orchestrator["worker_factory"] is not None
    assert captured_factory["agent"] == "opencode"
    assert captured_factory["startup_timeout_seconds"] == 17.0
    assert captured_factory["idle_progress_timeout_seconds"] == 45.0
    assert captured_factory["completion_quiet_period_seconds"] == 3.0
    assert captured_factory["max_retries"] == 2
    assert captured_factory["max_turns_per_session"] == 7
    assert captured_factory["max_session_age_seconds"] == 900.0


def test_build_planner_inherits_default_model_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = DaemonConfig(
        {
            "llm": {"default_model_chain": "reasoning"},
            "models": {
                "minimax": {
                    "model": "MiniMax-M2.7-highspeed",
                    "api_type": "anthropic",
                    "api_key_env": "MINIMAX_API_KEY",
                    "api_base_env": "MINIMAX_ANTHROPIC_BASE_URL",
                }
            },
            "model_chains": {"reasoning": {"primary": "minimax"}},
            "planner": {},
        }
    )
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)
    captured: dict[str, object] = {}

    class StubPlanner:
        ADAPTER_NAME = "litellm"

        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setenv("MINIMAX_API_KEY", "minimax-key")
    monkeypatch.setenv("MINIMAX_ANTHROPIC_BASE_URL", "https://api.minimaxi.com/anthropic")
    monkeypatch.setattr(
        "spec_orch.services.litellm_planner_adapter.LiteLLMPlannerAdapter",
        StubPlanner,
    )

    planner = daemon._build_planner()

    assert isinstance(planner, StubPlanner)
    assert captured["model"] == "anthropic/MiniMax-M2.7-highspeed"
    assert captured["model_chain"]


def test_build_round_orchestrator_inherits_supervisor_default_model_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = DaemonConfig(
        {
            "llm": {"default_model_chain": "reasoning"},
            "models": {
                "minimax": {
                    "model": "MiniMax-M2.7-highspeed",
                    "api_type": "anthropic",
                    "api_key_env": "MINIMAX_API_KEY",
                    "api_base_env": "MINIMAX_ANTHROPIC_BASE_URL",
                }
            },
            "model_chains": {"reasoning": {"primary": "minimax"}},
            "supervisor": {"adapter": "litellm"},
        }
    )
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)
    captured_supervisor: dict[str, object] = {}

    class StubRoundOrchestrator:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setenv("MINIMAX_API_KEY", "minimax-key")
    monkeypatch.setenv("MINIMAX_ANTHROPIC_BASE_URL", "https://api.minimaxi.com/anthropic")
    monkeypatch.setattr(
        "spec_orch.services.litellm_supervisor_adapter.LiteLLMSupervisorAdapter",
        lambda **kwargs: captured_supervisor.update(kwargs) or object(),
    )
    monkeypatch.setattr(
        "spec_orch.services.round_orchestrator.RoundOrchestrator",
        StubRoundOrchestrator,
    )

    orchestrator = daemon._build_round_orchestrator()

    assert isinstance(orchestrator, StubRoundOrchestrator)
    assert captured_supervisor["model"] == "anthropic/MiniMax-M2.7-highspeed"
    assert captured_supervisor["model_chain"]


def test_daemon_poll_and_run_skips_locked(tmp_path: Path) -> None:
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)

    mock_client = MagicMock()
    mock_client.list_issues.return_value = [{"identifier": "SPC-10", "description": _COMPLETE_DESC}]
    mock_controller = MagicMock()

    _init_checker(daemon)
    daemon._claim("SPC-10")
    daemon._poll_and_run(mock_client, mock_controller)

    mock_controller.advance_to_completion.assert_not_called()


def test_daemon_poll_and_run_processes_new_issue(tmp_path: Path) -> None:
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)
    daemon._write_back = MagicMock()

    mock_client = MagicMock()
    mock_client.list_issues.return_value = [
        {"id": "uuid-11", "identifier": "SPC-11", "description": _COMPLETE_DESC}
    ]

    mock_gate = MagicMock()
    mock_gate.mergeable = True
    mock_gate.failed_conditions = []
    mock_result = MagicMock()
    mock_result.gate = mock_gate
    mock_result.state = RunState.ACCEPTED

    mock_controller = MagicMock()
    mock_controller.advance_to_completion.return_value = mock_result

    _init_checker(daemon)
    daemon._poll_and_run(mock_client, mock_controller)
    # Drain submits to a thread pool; wait for it to finish.
    daemon._executor_pool.shutdown(wait=True)

    mock_controller.advance_to_completion.assert_called_once_with("SPC-11", flow_type=None)
    assert "SPC-11" in daemon._processed
    daemon._write_back.post_run_summary.assert_called_once()


def test_daemon_poll_and_enqueue_records_execution_intent(tmp_path: Path) -> None:
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)

    mock_client = MagicMock()
    raw_issue = {"id": "uuid-11", "identifier": "SPC-11", "description": _COMPLETE_DESC}
    mock_client.list_issues.return_value = [raw_issue]
    mock_controller = MagicMock()

    _init_checker(daemon)
    with patch.object(daemon._daemon_executor, "dispatch", return_value=None) as mocked:
        daemon._poll_and_enqueue(mock_client, mock_controller)

    mocked.assert_not_called()
    intents = daemon._state_store.list_execution_intents()
    assert len(intents) == 1
    assert intents[0]["issue_id"] == "SPC-11"
    assert intents[0]["raw_issue"]["id"] == "uuid-11"


def test_daemon_poll_and_enqueue_reserves_capacity_within_same_tick(tmp_path: Path) -> None:
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks"), "max_concurrent": 1}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)

    mock_client = MagicMock()
    mock_client.list_issues.return_value = [
        {"id": "uuid-11", "identifier": "SPC-11", "description": _COMPLETE_DESC},
        {"id": "uuid-12", "identifier": "SPC-12", "description": _COMPLETE_DESC},
    ]
    mock_controller = MagicMock()

    _init_checker(daemon)
    with patch.object(daemon, "_triage_issue", return_value=True):
        daemon._poll_and_enqueue(mock_client, mock_controller)

    intents = daemon._state_store.list_execution_intents()
    assert [intent["issue_id"] for intent in intents] == ["SPC-11"]


def test_daemon_drain_execution_queue_delegates_execution_to_daemon_executor(
    tmp_path: Path,
) -> None:
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)
    daemon._state_store.enqueue_execution_intent(
        issue_id="SPC-11",
        raw_issue={"id": "uuid-11", "identifier": "SPC-11", "description": _COMPLETE_DESC},
        is_hotfix=False,
    )

    mock_client = MagicMock()
    mock_controller = MagicMock()

    with patch.object(daemon._daemon_executor, "dispatch", return_value=None) as mocked:
        daemon._drain_execution_queue(mock_client, mock_controller)
        # Wait for the pool to finish
        daemon._executor_pool.shutdown(wait=True)

    mocked.assert_called_once()
    assert daemon._state_store.list_execution_intents() == []
    # Issue should be tracked as in-progress
    assert "SPC-11" in daemon._in_progress
    # Future should be tracked
    assert "SPC-11" in daemon._execution_futures


def test_daemon_drain_execution_queue_drains_all_admitted_intents(tmp_path: Path) -> None:
    """Async drain pops ALL queued intents (admission was checked at enqueue)."""
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks"), "max_concurrent": 2}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)
    daemon._state_store.enqueue_execution_intent(
        issue_id="SPC-11",
        raw_issue={"id": "uuid-11", "identifier": "SPC-11", "description": _COMPLETE_DESC},
        is_hotfix=False,
        enqueued_at=1,
    )
    daemon._state_store.enqueue_execution_intent(
        issue_id="SPC-12",
        raw_issue={"id": "uuid-12", "identifier": "SPC-12", "description": _COMPLETE_DESC},
        is_hotfix=True,
        enqueued_at=2,
    )

    mock_client = MagicMock()
    mock_controller = MagicMock()

    with patch.object(daemon._daemon_executor, "dispatch", return_value=None) as mocked:
        daemon._drain_execution_queue(mock_client, mock_controller)
        daemon._executor_pool.shutdown(wait=True)

    assert mocked.call_count == 2
    assert daemon._state_store.list_execution_intents() == []
    assert "SPC-11" in daemon._in_progress
    assert "SPC-12" in daemon._in_progress


def test_daemon_reap_completed_futures(tmp_path: Path) -> None:
    """Reaping harvests done futures and removes them from tracking."""
    from concurrent.futures import Future

    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)

    done_future: Future[None] = Future()
    done_future.set_result(None)
    daemon._execution_futures["SPC-11"] = done_future

    pending_future: Future[None] = Future()
    daemon._execution_futures["SPC-12"] = pending_future

    daemon._reap_completed_futures()

    assert "SPC-11" not in daemon._execution_futures
    assert "SPC-12" in daemon._execution_futures
    # Clean up pending future
    pending_future.cancel()


def test_daemon_reap_completed_futures_logs_errors(tmp_path: Path) -> None:
    """Reaping logs exceptions from failed futures."""
    from concurrent.futures import Future

    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)

    failed_future: Future[None] = Future()
    failed_future.set_exception(RuntimeError("boom"))
    daemon._execution_futures["SPC-99"] = failed_future

    daemon._reap_completed_futures()

    assert "SPC-99" not in daemon._execution_futures
    events = daemon._event_bus.query_history(limit=10)
    error_events = [e for e in events if e.payload.get("kind") == "daemon.executor_future_error"]
    assert len(error_events) >= 1
    assert error_events[-1].payload["issue_id"] == "SPC-99"


def test_daemon_executor_dispatches_mission_issue_to_mission_executor() -> None:
    from spec_orch.services.daemon_executor import DaemonExecutor

    executor = DaemonExecutor()
    host = MagicMock()
    host._detect_mission.return_value = "mission-1"
    raw_issue = {"id": "uuid-1", "identifier": "SPC-1"}

    with (
        patch.object(executor._mission_executor, "execute", return_value=None) as mocked_mission,
        patch.object(
            executor._single_issue_executor, "execute", return_value=None
        ) as mocked_single,
    ):
        executor.dispatch(
            host=host,
            issue_id="SPC-1",
            raw_issue=raw_issue,
            client=MagicMock(),
            controller=MagicMock(),
            is_hotfix=False,
        )

    mocked_mission.assert_called_once()
    mocked_single.assert_not_called()


def test_daemon_executor_dispatches_single_issue_to_single_executor() -> None:
    from spec_orch.services.daemon_executor import DaemonExecutor

    executor = DaemonExecutor()
    host = MagicMock()
    host._detect_mission.return_value = None
    raw_issue = {"id": "uuid-1", "identifier": "SPC-1"}

    with (
        patch.object(executor._mission_executor, "execute", return_value=None) as mocked_mission,
        patch.object(
            executor._single_issue_executor, "execute", return_value=None
        ) as mocked_single,
    ):
        executor.dispatch(
            host=host,
            issue_id="SPC-1",
            raw_issue=raw_issue,
            client=MagicMock(),
            controller=MagicMock(),
            is_hotfix=True,
        )

    mocked_single.assert_called_once()
    mocked_mission.assert_not_called()


def test_daemon_poll_and_run_releases_non_terminal(tmp_path: Path) -> None:
    """Non-terminal states should release the lock so the next poll re-advances."""
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)
    daemon._write_back = MagicMock()

    mock_client = MagicMock()
    mock_client.list_issues.return_value = [
        {"id": "uuid-12", "identifier": "SPC-12", "description": _COMPLETE_DESC}
    ]

    mock_gate = MagicMock()
    mock_gate.mergeable = False
    mock_gate.failed_conditions = ["pre_build"]
    mock_result = MagicMock()
    mock_result.gate = mock_gate
    mock_result.state = RunState.SPEC_DRAFTING

    mock_controller = MagicMock()
    mock_controller.advance_to_completion.return_value = mock_result

    _init_checker(daemon)
    daemon._poll_and_run(mock_client, mock_controller)
    daemon._executor_pool.shutdown(wait=True)

    mock_controller.advance_to_completion.assert_called_once_with("SPC-12", flow_type=None)
    assert "SPC-12" not in daemon._processed
    assert not daemon._is_locked("SPC-12")


def test_daemon_poll_and_run_marks_gate_evaluated_as_processed(tmp_path: Path) -> None:
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)
    daemon._write_back = MagicMock()

    mock_client = MagicMock()
    mock_client.list_issues.return_value = [
        {"id": "uuid-13", "identifier": "SPC-13", "description": _COMPLETE_DESC}
    ]

    mock_gate = MagicMock()
    mock_gate.mergeable = False
    mock_gate.failed_conditions = ["human_acceptance"]
    mock_result = MagicMock()
    mock_result.gate = mock_gate
    mock_result.state = RunState.GATE_EVALUATED

    mock_controller = MagicMock()
    mock_controller.advance_to_completion.return_value = mock_result

    _init_checker(daemon)
    daemon._poll_and_run(mock_client, mock_controller)
    daemon._executor_pool.shutdown(wait=True)

    mock_controller.advance_to_completion.assert_called_once_with("SPC-13", flow_type=None)
    assert "SPC-13" in daemon._processed


def test_daemon_poll_and_run_defers_issue_when_admission_budget_is_saturated(
    tmp_path: Path,
) -> None:
    from spec_orch.services.admission_governor import load_admission_governor_snapshot

    cfg = DaemonConfig(
        {
            "daemon": {
                "lockfile_dir": str(tmp_path / "locks"),
                "max_concurrent": 1,
            }
        }
    )
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)
    daemon._in_progress.add("SPC-BUSY")

    mock_client = MagicMock()
    mock_client.list_issues.return_value = [
        {"id": "uuid-412", "identifier": "SPC-412", "description": _COMPLETE_DESC}
    ]
    mock_controller = MagicMock()

    _init_checker(daemon)
    daemon._poll_and_run(mock_client, mock_controller)

    mock_controller.advance_to_completion.assert_not_called()
    mock_client.update_issue_state.assert_not_called()

    snapshot = load_admission_governor_snapshot(tmp_path)
    assert snapshot["admission_decisions"][0]["subject_id"] == "SPC-412"
    assert snapshot["admission_decisions"][0]["decision"] == "defer"
    assert snapshot["admission_decisions"][0]["required_budgets"] == [
        "daemon:max_concurrent",
        "mission:max_concurrent",
        "worker:max_concurrent",
        "verifier:max_concurrent",
    ]
    assert snapshot["queue"][0]["queue_name"] == "daemon_admission"
    assert {item["subject_kind"] for item in snapshot["resource_budgets"]} == {
        "daemon",
        "mission",
        "worker",
        "verifier",
    }


def test_daemon_auto_create_pr(tmp_path: Path) -> None:
    """Daemon should attempt PR creation when reaching GATE_EVALUATED."""
    cfg = DaemonConfig({"daemon": {"lockfile_dir": str(tmp_path / "locks")}})
    daemon = SpecOrchDaemon(config=cfg, repo_root=tmp_path)

    mock_gate = MagicMock()
    mock_gate.mergeable = True
    mock_gate.failed_conditions = []
    mock_gate.flow_control = GateFlowControl(
        promotion_required=True,
        promotion_target="standard",
    )
    mock_result = MagicMock()
    mock_result.state = RunState.GATE_EVALUATED
    mock_result.gate = mock_gate
    mock_result.issue.title = "Test Issue"
    mock_result.issue.issue_id = "SPC-20"
    mock_result.workspace = tmp_path

    with patch("spec_orch.services.daemon.GitHubPRService") as MockGH:
        mock_gh = MockGH.return_value
        mock_gh._current_branch.return_value = "feat/spc-20"
        mock_gh.check_mergeable.return_value = {"mergeable": True, "conflicting_files": []}
        mock_gh.create_pr.return_value = "https://github.com/pr/99"
        daemon._auto_create_pr("SPC-20", mock_result)
        mock_gh.create_pr.assert_called_once()
        body = mock_gh.create_pr.call_args.kwargs["body"]
        assert "Promotion signal" in body
        assert "standard" in body
