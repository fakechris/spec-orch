from __future__ import annotations

import json
from pathlib import Path
from urllib.error import HTTPError, URLError


def test_materialize_fresh_execution_artifacts_writes_proof_files(tmp_path: Path) -> None:
    from spec_orch.services.fresh_acpx_e2e import materialize_fresh_execution_artifacts

    repo_root = tmp_path
    operator_dir = repo_root / "docs" / "specs" / "fresh-acpx-1" / "operator"
    round_dir = repo_root / "docs" / "specs" / "fresh-acpx-1" / "rounds" / "round-01"
    operator_dir.mkdir(parents=True, exist_ok=True)
    round_dir.mkdir(parents=True, exist_ok=True)

    mission_bootstrap = {
        "mission_id": "fresh-acpx-1",
        "title": "Fresh ACPX Mission E2E Smoke",
    }
    launch = {
        "last_launch": {
            "state": {
                "mission_id": "fresh-acpx-1",
                "phase": "executing",
            }
        },
        "runner": {
            "status": "running",
        },
    }
    (operator_dir / "mission_bootstrap.json").write_text(
        json.dumps(mission_bootstrap) + "\n",
        encoding="utf-8",
    )
    (operator_dir / "launch.json").write_text(
        json.dumps(launch) + "\n",
        encoding="utf-8",
    )
    round_summary = {
        "round_id": 1,
        "wave_id": 0,
        "status": "decided",
        "worker_results": [{"packet_id": "pkt-1", "status": "completed"}],
    }
    (round_dir / "round_summary.json").write_text(
        json.dumps(round_summary) + "\n",
        encoding="utf-8",
    )

    proof = materialize_fresh_execution_artifacts(
        repo_root=repo_root,
        mission_id="fresh-acpx-1",
        round_dir=round_dir,
        launch_result={
            "background_runner_started": True,
            "state": {"mission_id": "fresh-acpx-1", "phase": "executing"},
        },
    )

    daemon_run = json.loads((operator_dir / "daemon_run.json").read_text(encoding="utf-8"))
    assert daemon_run["mission_id"] == "fresh-acpx-1"
    assert daemon_run["fresh_round_path"] == str(round_dir)
    assert daemon_run["runner_status"] == "running"

    fresh_round_summary = json.loads(
        (round_dir / "fresh_round_summary.json").read_text(encoding="utf-8")
    )
    assert fresh_round_summary["round_id"] == 1
    builder_execution_summary = json.loads(
        (round_dir / "builder_execution_summary.json").read_text(encoding="utf-8")
    )
    assert builder_execution_summary["worker_results"][0]["packet_id"] == "pkt-1"

    assert proof["proof_type"] == "fresh_execution"
    assert proof["daemon_run"]["fresh_round_path"] == str(round_dir)
    assert proof["builder_execution_summary"]["worker_results"][0]["packet_id"] == "pkt-1"


def test_materialize_fresh_execution_artifacts_tolerates_malformed_json(tmp_path: Path) -> None:
    from spec_orch.services.fresh_acpx_e2e import materialize_fresh_execution_artifacts

    repo_root = tmp_path
    operator_dir = repo_root / "docs" / "specs" / "fresh-acpx-1" / "operator"
    round_dir = repo_root / "docs" / "specs" / "fresh-acpx-1" / "rounds" / "round-01"
    operator_dir.mkdir(parents=True, exist_ok=True)
    round_dir.mkdir(parents=True, exist_ok=True)

    (operator_dir / "mission_bootstrap.json").write_text("{not-json\n", encoding="utf-8")
    (operator_dir / "launch.json").write_text("{not-json\n", encoding="utf-8")
    (round_dir / "round_summary.json").write_text("{not-json\n", encoding="utf-8")

    proof = materialize_fresh_execution_artifacts(
        repo_root=repo_root,
        mission_id="fresh-acpx-1",
        round_dir=round_dir,
        launch_result={
            "background_runner_started": True,
            "state": {"mission_id": "fresh-acpx-1", "phase": "executing"},
        },
    )

    daemon_run = json.loads((operator_dir / "daemon_run.json").read_text(encoding="utf-8"))
    assert daemon_run["runner_status"] == "started"
    assert daemon_run["launch_phase"] == "executing"
    assert proof["mission_bootstrap"] == {}
    assert proof["launch"] == {}
    assert proof["builder_execution_summary"]["worker_results"] == []


def test_write_fresh_acpx_mission_report_separates_proof_layers(tmp_path: Path) -> None:
    from spec_orch.domain.models import AcceptanceCampaign, AcceptanceMode, AcceptanceReviewResult
    from spec_orch.services.fresh_acpx_e2e import write_fresh_acpx_mission_report

    round_dir = tmp_path / "docs" / "specs" / "fresh-acpx-1" / "rounds" / "round-01"
    round_dir.mkdir(parents=True, exist_ok=True)
    result = AcceptanceReviewResult(
        status="pass",
        summary="Fresh mission execution and workflow replay both succeeded.",
        confidence=0.97,
        evaluator="litellm_acceptance",
        tested_routes=["/", "/?mission=fresh-acpx-1&mode=missions&tab=overview"],
        acceptance_mode="workflow",
        coverage_status="complete",
        campaign=AcceptanceCampaign(
            mode=AcceptanceMode.WORKFLOW,
            goal="Validate a fresh mission post-run workflow replay.",
            primary_routes=["/"],
        ),
    )

    report = write_fresh_acpx_mission_report(
        round_dir=round_dir,
        mission_id="fresh-acpx-1",
        dashboard_url="http://127.0.0.1:8426/?mission=fresh-acpx-1&mode=missions&tab=overview",
        fresh_execution={
            "proof_type": "fresh_execution",
            "mission_bootstrap": {
                "mission_id": "fresh-acpx-1",
                "metadata": {"fresh_variant": "multi_packet"},
            },
            "launch": {"last_launch": {"state": {"phase": "executing"}}},
            "daemon_run": {"fresh_round_path": str(round_dir)},
            "builder_execution_summary": {"worker_results": [{"packet_id": "pkt-1"}]},
            "fresh_round_path": str(round_dir),
        },
        workflow_replay={
            "proof_type": "workflow_replay",
            "review_routes": {
                "overview": "/?mission=fresh-acpx-1&mode=missions&tab=overview",
            },
        },
        acceptance_review=result,
    )

    markdown = (round_dir / "fresh_acpx_mission_e2e_report.md").read_text(encoding="utf-8")
    assert "fresh execution proof" in markdown.lower()
    assert "workflow replay proof" in markdown.lower()
    assert "remaining gaps" in markdown.lower()
    assert "fresh-acpx-1" in markdown

    report_json = json.loads(
        (round_dir / "fresh_acpx_mission_e2e_report.json").read_text(encoding="utf-8")
    )
    assert report_json["mission_id"] == "fresh-acpx-1"
    assert report_json["variant"] == "multi_packet"
    assert report_json["fresh_execution"]["daemon_run"]["fresh_round_path"] == str(round_dir)
    assert report_json["workflow_replay"]["review_routes"]["overview"].endswith("tab=overview")
    assert report_json["acceptance_review"]["status"] == "pass"
    assert report["markdown_path"].endswith("fresh_acpx_mission_e2e_report.md")


def test_run_fresh_execution_once_advances_lifecycle_and_records_daemon_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from spec_orch.services.fresh_acpx_e2e import run_fresh_execution_once

    repo_root = tmp_path
    operator_dir = repo_root / "docs" / "specs" / "fresh-acpx-1" / "operator"
    operator_dir.mkdir(parents=True, exist_ok=True)

    class FakeState:
        def to_dict(self) -> dict[str, object]:
            return {"mission_id": "fresh-acpx-1", "phase": "all_done", "current_round": 1}

    class FakeLifecycleManager:
        def auto_advance(self, mission_id: str) -> FakeState:
            assert mission_id == "fresh-acpx-1"
            return FakeState()

    monkeypatch.setattr(
        "spec_orch.services.fresh_acpx_e2e._build_execution_lifecycle_manager",
        lambda repo_root: FakeLifecycleManager(),
    )

    result = run_fresh_execution_once(repo_root=repo_root, mission_id="fresh-acpx-1")

    daemon_run = json.loads((operator_dir / "daemon_run.json").read_text(encoding="utf-8"))
    assert daemon_run["runner_status"] == "finished"
    assert daemon_run["state"]["phase"] == "all_done"
    assert result["state"]["phase"] == "all_done"


def test_run_fresh_launch_and_pickup_records_consistent_proof(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from spec_orch.services.fresh_acpx_e2e import run_fresh_launch_and_pickup

    operator_dir = tmp_path / "docs" / "specs" / "fresh-acpx-1" / "operator"
    operator_dir.mkdir(parents=True, exist_ok=True)
    launch_calls: list[bool] = []

    monkeypatch.setattr(
        "spec_orch.dashboard.launcher._launch_mission",
        lambda repo_root, mission_id, *, allow_background_runner=True: (
            launch_calls.append(allow_background_runner)
            or {
                "mission_id": mission_id,
                "background_runner_started": False,
                "state": {"mission_id": mission_id, "phase": "executing"},
                "launch": {"runner": {"status": "foreground_required"}},
            }
        ),
    )
    monkeypatch.setattr(
        "spec_orch.services.fresh_acpx_e2e.run_fresh_execution_once",
        lambda *, repo_root, mission_id: {
            "mission_id": mission_id,
            "runner_status": "finished",
            "state": {"mission_id": mission_id, "phase": "all_done"},
        },
    )

    result = run_fresh_launch_and_pickup(repo_root=tmp_path, mission_id="fresh-acpx-1")

    persisted = json.loads((operator_dir / "launch_pickup.json").read_text(encoding="utf-8"))
    assert launch_calls == [False]
    assert persisted["mission_id"] == "fresh-acpx-1"
    assert persisted["launch_result"]["state"]["phase"] == "executing"
    assert persisted["daemon_run"]["state"]["phase"] == "all_done"
    assert result["daemon_run"]["runner_status"] == "finished"


def test_run_fresh_launch_and_pickup_skips_local_pickup_when_daemon_running(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from spec_orch.services.fresh_acpx_e2e import run_fresh_launch_and_pickup

    operator_dir = tmp_path / "docs" / "specs" / "fresh-acpx-1" / "operator"
    operator_dir.mkdir(parents=True, exist_ok=True)
    pickup_attempts: list[str] = []

    monkeypatch.setattr(
        "spec_orch.dashboard.launcher._launch_mission",
        lambda repo_root, mission_id, *, allow_background_runner=True: {
            "mission_id": mission_id,
            "background_runner_started": False,
            "state": {"mission_id": mission_id, "phase": "executing"},
            "launch": {"runner": {"status": "daemon_running"}},
        },
    )
    monkeypatch.setattr(
        "spec_orch.services.fresh_acpx_e2e.run_fresh_execution_once",
        lambda *, repo_root, mission_id: pickup_attempts.append(mission_id),
    )

    result = run_fresh_launch_and_pickup(repo_root=tmp_path, mission_id="fresh-acpx-1")

    persisted = json.loads((operator_dir / "launch_pickup.json").read_text(encoding="utf-8"))
    assert pickup_attempts == []
    assert persisted["daemon_run"] is None
    assert result["daemon_run"] is None


def test_wait_for_dashboard_ready_retries_until_probe_succeeds(monkeypatch) -> None:
    from spec_orch.services.fresh_acpx_e2e import wait_for_dashboard_ready

    attempts: list[int] = []

    def fake_probe(url: str, timeout_seconds: float) -> dict[str, object]:
        attempts.append(1)
        if len(attempts) < 3:
            raise URLError("connection refused")
        return {"status": 200, "url": url}

    monkeypatch.setattr("spec_orch.services.fresh_acpx_e2e._probe_dashboard", fake_probe)
    monkeypatch.setattr("spec_orch.services.fresh_acpx_e2e.time.sleep", lambda _: None)

    result = wait_for_dashboard_ready("http://127.0.0.1:8426/", timeout_seconds=1.0)

    assert result["ready"] is True
    assert result["attempts"] == 3
    assert result["status"] == 200


def test_wait_for_dashboard_ready_times_out_with_last_error(monkeypatch) -> None:
    from spec_orch.services.fresh_acpx_e2e import wait_for_dashboard_ready

    monkeypatch.setattr(
        "spec_orch.services.fresh_acpx_e2e._probe_dashboard",
        lambda url, timeout_seconds: (_ for _ in ()).throw(URLError("still starting")),
    )
    monkeypatch.setattr("spec_orch.services.fresh_acpx_e2e.time.sleep", lambda _: None)

    try:
        wait_for_dashboard_ready("http://127.0.0.1:8426/", timeout_seconds=0.01)
    except TimeoutError as exc:
        assert "still starting" in str(exc)
    else:
        raise AssertionError("Expected readiness polling to time out")


def test_wait_for_dashboard_ready_treats_http_error_status_as_ready(monkeypatch) -> None:
    from spec_orch.services.fresh_acpx_e2e import wait_for_dashboard_ready

    def fake_probe(url: str, timeout_seconds: float) -> dict[str, object]:
        raise HTTPError(url, 404, "not found", hdrs=None, fp=None)

    monkeypatch.setattr("spec_orch.services.fresh_acpx_e2e._probe_dashboard", fake_probe)
    monkeypatch.setattr("spec_orch.services.fresh_acpx_e2e.time.sleep", lambda _: None)

    result = wait_for_dashboard_ready("http://127.0.0.1:8426/", timeout_seconds=0.1)

    assert result["ready"] is True
    assert result["status"] == 404


def test_assert_fresh_plan_budget_rejects_broad_plan() -> None:
    from spec_orch.services.fresh_acpx_e2e import assert_fresh_plan_budget

    broad_plan = {
        "waves": [
            {"wave_number": 0, "work_packets": [{"packet_id": "one"}, {"packet_id": "two"}]},
            {"wave_number": 1, "work_packets": [{"packet_id": "three"}]},
        ]
    }

    try:
        assert_fresh_plan_budget(broad_plan, max_waves=1, max_packets=2)
    except ValueError as exc:
        assert "max_waves=1" in str(exc)
        assert "max_packets=2" in str(exc)
    else:
        raise AssertionError("Expected broad fresh plan to fail budget guard")


def test_assert_fresh_plan_budget_accepts_narrow_plan() -> None:
    from spec_orch.services.fresh_acpx_e2e import assert_fresh_plan_budget

    narrow_plan = {
        "waves": [
            {"wave_number": 0, "work_packets": [{"packet_id": "one"}, {"packet_id": "two"}]},
        ]
    }

    summary = assert_fresh_plan_budget(narrow_plan, max_waves=1, max_packets=2)

    assert summary["wave_count"] == 1
    assert summary["packet_count"] == 2
