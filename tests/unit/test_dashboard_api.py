"""Tests for Dashboard API endpoints."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from spec_orch.services.event_bus import Event, EventTopic, get_event_bus

try:
    from fastapi.testclient import TestClient

    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    specs_dir = tmp_path / "docs" / "specs"
    specs_dir.mkdir(parents=True)
    (tmp_path / ".spec_orch_runs").mkdir()
    return tmp_path


@pytest.fixture
def client(repo: Path):
    if not HAS_FASTAPI:
        pytest.skip("fastapi not installed")
    from spec_orch.dashboard import create_app

    app = create_app(repo)
    return TestClient(app)


@pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")
class TestDashboardAPI:
    def test_health(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"

    def test_missions(self, client):
        r = client.get("/api/missions")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_mission_detail_endpoint(self, client, repo: Path):
        mission_id = "mission-detail"
        specs = repo / "docs" / "specs" / mission_id
        rounds = specs / "rounds" / "round-01"
        specs.mkdir(parents=True)
        rounds.mkdir(parents=True)

        (specs / "mission.json").write_text(
            json.dumps(
                {
                    "mission_id": mission_id,
                    "title": "Mission Detail",
                    "status": "approved",
                    "spec_path": f"docs/specs/{mission_id}/spec.md",
                    "acceptance_criteria": ["Show mission detail"],
                    "constraints": ["Keep mission context visible"],
                    "interface_contracts": [],
                    "created_at": "2026-03-25T00:00:00+00:00",
                    "approved_at": "2026-03-25T00:05:00+00:00",
                    "completed_at": None,
                }
            )
        )
        (specs / "spec.md").write_text("# Mission Detail\n")
        (specs / "plan.json").write_text(
            json.dumps(
                {
                    "plan_id": "plan-md",
                    "mission_id": mission_id,
                    "status": "executing",
                    "waves": [
                        {
                            "wave_number": 0,
                            "description": "Core wave",
                            "work_packets": [
                                {
                                    "packet_id": "pkt-1",
                                    "title": "Build mission detail",
                                    "spec_section": "overview",
                                    "run_class": "feature",
                                    "files_in_scope": ["src/spec_orch/dashboard.py"],
                                    "files_out_of_scope": [],
                                    "depends_on": [],
                                    "acceptance_criteria": ["Mission detail renders"],
                                    "verification_commands": {"test": ["pytest", "-q"]},
                                    "builder_prompt": "Implement mission detail",
                                    "linear_issue_id": "SON-201",
                                }
                            ],
                        }
                    ],
                }
            )
        )
        (rounds / "round_summary.json").write_text(
            json.dumps(
                {
                    "round_id": 1,
                    "wave_id": 0,
                    "status": "decided",
                    "started_at": "2026-03-25T00:10:00+00:00",
                    "completed_at": "2026-03-25T00:12:00+00:00",
                    "worker_results": [
                        {
                            "packet_id": "pkt-1",
                            "title": "Build mission detail",
                            "report_path": "docs/specs/mission-detail/workers/pkt-1/builder_report.json",
                            "succeeded": True,
                        }
                    ],
                    "decision": {
                        "action": "continue",
                        "reason_code": "wave_complete",
                        "summary": "Continue to the next wave.",
                        "confidence": 0.9,
                        "affected_workers": ["pkt-1"],
                        "artifacts": {
                            "review_memo": "docs/specs/mission-detail/rounds/round-01/supervisor_review.md"
                        },
                        "session_ops": {"reuse": [], "spawn": [], "cancel": []},
                        "blocking_questions": [],
                    },
                }
            )
        )
        (rounds / "round_decision.json").write_text(
            json.dumps(
                {
                    "action": "continue",
                    "reason_code": "wave_complete",
                    "summary": "Continue to the next wave.",
                    "confidence": 0.9,
                    "affected_workers": ["pkt-1"],
                    "artifacts": {
                        "review_memo": "docs/specs/mission-detail/rounds/round-01/supervisor_review.md"
                    },
                    "session_ops": {"reuse": [], "spawn": [], "cancel": []},
                    "blocking_questions": [],
                }
            )
        )
        (rounds / "supervisor_review.md").write_text("Looks good.\n")

        r = client.get(f"/api/missions/{mission_id}/detail")
        assert r.status_code == 200
        data = r.json()
        assert data["mission"]["mission_id"] == mission_id
        assert data["current_round"] == 1
        assert data["packets"][0]["packet_id"] == "pkt-1"
        assert data["rounds"][0]["decision"]["action"] == "continue"
        assert "inject_guidance" in data["actions"]
        assert data["artifacts"]["spec"].endswith(f"docs/specs/{mission_id}/spec.md")

    def test_packet_transcript_endpoint(self, client, repo: Path):
        mission_id = "mission-transcript"
        packet_id = "pkt-1"
        telemetry = repo / "docs" / "specs" / mission_id / "workers" / packet_id / "telemetry"
        telemetry.mkdir(parents=True)

        (telemetry / "activity.log").write_text(
            "2026-03-25T00:11:00Z BUILDER packet started\n"
            "2026-03-25T00:12:00Z BUILDER packet completed\n",
            encoding="utf-8",
        )
        (telemetry / "events.jsonl").write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "timestamp": "2026-03-25T00:11:30Z",
                            "event_type": "mission_packet_started",
                            "message": "packet started",
                        }
                    ),
                    json.dumps(
                        {
                            "timestamp": "2026-03-25T00:11:45Z",
                            "event_type": "tool_call_completed",
                            "message": "applied patch",
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (telemetry / "incoming_events.jsonl").write_text(
            json.dumps(
                {
                    "ts": "2026-03-25T00:11:40Z",
                    "kind": "assistant_message",
                    "excerpt": "Implementing mission detail now.",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        r = client.get(f"/api/missions/{mission_id}/packets/{packet_id}/transcript")
        assert r.status_code == 200
        data = r.json()
        assert data["mission_id"] == mission_id
        assert data["packet_id"] == packet_id
        assert len(data["entries"]) == 5
        kinds = {entry["kind"] for entry in data["entries"]}
        assert kinds == {"activity", "event", "incoming"}
        assert data["entries"][0]["message"] == "BUILDER packet started"

    def test_packet_transcript_endpoint_returns_empty_payload_when_missing(self, client):
        mission_id = "mission-transcript-missing"
        packet_id = "pkt-404"

        r = client.get(f"/api/missions/{mission_id}/packets/{packet_id}/transcript")
        assert r.status_code == 200
        data = r.json()
        assert data["mission_id"] == mission_id
        assert data["packet_id"] == packet_id
        assert data["entries"] == []
        assert data["telemetry"] == {
            "activity_log": None,
            "events": None,
            "incoming": None,
        }

    def test_lifecycle_endpoint(self, client):
        r = client.get("/api/lifecycle")
        assert r.status_code == 200
        assert isinstance(r.json(), dict)

    def test_evolution_endpoint(self, client):
        r = client.get("/api/evolution")
        assert r.status_code == 200
        data = r.json()
        assert "prompt_variants" in data

    def test_evolution_endpoint_reads_unified_run_trend(self, client, repo: Path):
        run_dir = repo / ".spec_orch_runs" / "R100" / "run_artifact"
        run_dir.mkdir(parents=True)
        (run_dir / "conclusion.json").write_text(
            '{"state":"gate_evaluated","mergeable":true,"issue_id":"R100"}'
        )
        r = client.get("/api/evolution")
        assert r.status_code == 200
        data = r.json()
        assert data["total_runs"] == 1
        assert data["successful_runs"] == 1

    def test_evolution_endpoint_falls_back_to_legacy_report(self, client, repo: Path):
        run_dir = repo / ".spec_orch_runs" / "R101"
        run_dir.mkdir(parents=True)
        (run_dir / "report.json").write_text(
            '{"state":"gate_evaluated","mergeable":false,"issue_id":"R101"}'
        )
        r = client.get("/api/evolution")
        assert r.status_code == 200
        data = r.json()
        assert data["total_runs"] == 1
        assert data["successful_runs"] == 0

    def test_approve_unknown_mission(self, client):
        r = client.post("/api/missions/nonexistent/approve")
        assert r.status_code == 200
        data = r.json()
        assert "ok" in data or "error" in data

    def test_discuss_endpoint(self, client):
        r = client.post(
            "/api/discuss",
            content='{"thread_id": "test-1", "message": "hello"}',
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code in (200, 503)

    def test_btw_no_active_issue(self, client):
        r = client.post(
            "/api/btw",
            content='{"issue_id": "SON-99", "message": "handle X"}',
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code in (200, 503)

    def test_homepage(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "spec-orch" in r.text.lower()
        assert "/static/operator-console.css" in r.text
        assert "/static/operator-console.js" in r.text
        assert 'id="operator-shell"' in r.text
        assert 'id="mission-list"' in r.text
        assert 'id="mission-detail-view"' in r.text
        assert 'id="operator-context-rail"' in r.text
        assert 'id="packet-transcript-view"' in r.text

    def test_static_operator_console_assets(self, client):
        css = client.get("/static/operator-console.css")
        assert css.status_code == 200
        assert "text/css" in css.headers.get("content-type", "")

        js = client.get("/static/operator-console.js")
        assert js.status_code == 200
        assert "javascript" in js.headers.get("content-type", "")

    def test_favicon_route_returns_no_content(self, client):
        response = client.get("/favicon.ico")
        assert response.status_code == 204
        assert response.content == b""

    def test_websocket_route_registers_websocket_param(self, repo: Path):
        from spec_orch.dashboard import create_app

        app = create_app(repo)
        ws_route = next(route for route in app.router.routes if getattr(route, "path", None) == "/ws")
        dependant = ws_route.dependant
        assert dependant.websocket_param_name == "websocket"
        assert dependant.query_params == []

    def test_runs_endpoint(self, client):
        r = client.get("/api/runs")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_runs_endpoint_tolerates_non_object_conclusion(self, client, repo: Path):
        run_dir = repo / ".spec_orch_runs" / "R1" / "run_artifact"
        run_dir.mkdir(parents=True)
        (run_dir / "conclusion.json").write_text("[]")
        r = client.get("/api/runs")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_events_endpoint(self, client):
        bus = get_event_bus()
        bus.publish(
            Event(
                topic=EventTopic.ISSUE_STATE,
                payload={"issue_id": "SON-194", "run_id": "run-194", "state": "building"},
                source="test",
            )
        )
        r = client.get("/api/events")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1

        filtered = client.get("/api/events?issue_id=SON-194&topic=issue.state&limit=1")
        assert filtered.status_code == 200
        result = filtered.json()
        assert len(result) == 1
        assert result[0]["payload"]["issue_id"] == "SON-194"

    # ---- Control Tower (P5) tests ----

    def test_control_overview(self, client):
        r = client.get("/api/control/overview")
        assert r.status_code == 200
        data = r.json()
        assert "flywheel" in data
        assert "run_summary" in data
        assert "skills_count" in data

    def test_control_skills(self, client, repo: Path):
        skills_dir = repo / ".spec_orch" / "skills"
        skills_dir.mkdir(parents=True)
        (skills_dir / "s1.yaml").write_text("id: s1\nname: S1\nkind: gate_check\n")
        r = client.get("/api/control/skills")
        assert r.status_code == 200
        data = r.json()
        assert len(data["skills"]) == 1
        assert data["skills"][0]["id"] == "s1"

    def test_control_eval(self, client, repo: Path):
        run_dir = repo / ".spec_orch_runs" / "eval-test" / "run_artifact"
        run_dir.mkdir(parents=True)
        (run_dir / "conclusion.json").write_text(
            '{"run_id":"e1","issue_id":"eval-test","mergeable":true,"verdict":"pass"}'
        )
        r = client.get("/api/control/eval")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1

    def test_control_eval_trigger(self, client):
        r = client.post("/api/control/eval/run")
        assert r.status_code == 200
        data = r.json()
        assert "triggered" in data

    def test_control_reactions(self, client):
        r = client.get("/api/control/reactions")
        assert r.status_code == 200
        data = r.json()
        assert "rules" in data
