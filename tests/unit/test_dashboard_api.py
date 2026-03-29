"""Tests for Dashboard API endpoints."""

from __future__ import annotations

import json
from datetime import UTC
from datetime import datetime as real_datetime
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
    def test_launcher_readiness_endpoint(self, client, monkeypatch):
        monkeypatch.setattr(
            "spec_orch.dashboard.routes.dashboard_app._gather_launcher_readiness",
            lambda root: {
                "config_present": True,
                "dashboard": {"ready": True},
                "linear": {"ready": False, "token_env": "SPEC_ORCH_LINEAR_TOKEN"},
                "planner": {"ready": True, "model": "MiniMax-M2.5"},
                "builder": {"ready": True, "adapter": "acpx_codex"},
            },
        )

        response = client.get("/api/launcher/readiness")

        assert response.status_code == 200
        assert response.json()["linear"]["ready"] is False

    def test_launcher_create_mission_endpoint(self, client, monkeypatch):
        monkeypatch.setattr(
            "spec_orch.dashboard.routes.dashboard_app._create_mission_draft",
            lambda root, payload: {
                "mission_id": "launcher-created",
                "title": payload["title"],
                "status": "drafting",
                "spec_path": "docs/specs/launcher-created/spec.md",
            },
        )

        response = client.post(
            "/api/launcher/missions",
            json={"title": "Launcher Created", "intent": "Create from dashboard."},
        )

        assert response.status_code == 200
        assert response.json()["mission_id"] == "launcher-created"

    def test_launcher_approve_plan_endpoint(self, client, monkeypatch):
        monkeypatch.setattr(
            "spec_orch.dashboard.routes.dashboard_app._approve_and_plan_mission",
            lambda root, mission_id: {
                "mission_id": mission_id,
                "approved_at": "2026-03-27T08:00:00+00:00",
                "status": "approved",
                "plan": {"plan_id": "plan-1", "waves": []},
            },
        )

        response = client.post("/api/launcher/missions/launcher-smoke/approve-plan")

        assert response.status_code == 200
        assert response.json()["plan"]["plan_id"] == "plan-1"

    def test_launcher_linear_create_endpoint(self, client, monkeypatch):
        monkeypatch.setattr(
            "spec_orch.dashboard.routes.dashboard_app._create_linear_issue_for_mission",
            lambda root, mission_id, title, description: {
                "mission_id": mission_id,
                "linear_issue": {
                    "id": "issue-1",
                    "identifier": "SON-999",
                    "title": title,
                },
            },
        )

        response = client.post(
            "/api/launcher/missions/launcher-smoke/linear-create",
            json={"title": "Dogfood launcher run", "description": "Track this run."},
        )

        assert response.status_code == 200
        assert response.json()["linear_issue"]["identifier"] == "SON-999"

    def test_launcher_linear_bind_endpoint(self, client, monkeypatch):
        monkeypatch.setattr(
            "spec_orch.dashboard.routes.dashboard_app._bind_linear_issue_to_mission",
            lambda root, mission_id, linear_issue_id: {
                "mission_id": mission_id,
                "linear_issue": {"identifier": linear_issue_id},
            },
        )

        response = client.post(
            "/api/launcher/missions/launcher-smoke/linear-bind",
            json={"linear_issue_id": "SON-241"},
        )

        assert response.status_code == 200
        assert response.json()["linear_issue"]["identifier"] == "SON-241"

    def test_launcher_launch_endpoint(self, client, monkeypatch):
        monkeypatch.setattr(
            "spec_orch.dashboard.routes.dashboard_app._launch_mission",
            lambda root, mission_id: {
                "mission_id": mission_id,
                "state": {"mission_id": mission_id, "phase": "executing"},
            },
        )

        response = client.post("/api/launcher/missions/launcher-smoke/launch")

        assert response.status_code == 200
        assert response.json()["state"]["phase"] == "executing"

    def test_acceptance_review_endpoint_returns_empty_state(self, client, repo: Path):
        mission_id = "mission-acceptance-empty"
        specs = repo / "docs" / "specs" / mission_id
        specs.mkdir(parents=True)
        (specs / "mission.json").write_text(
            json.dumps(
                {
                    "mission_id": mission_id,
                    "title": "Acceptance Empty Mission",
                    "status": "approved",
                    "spec_path": f"docs/specs/{mission_id}/spec.md",
                    "acceptance_criteria": [],
                    "constraints": [],
                    "interface_contracts": [],
                    "created_at": "2026-03-27T00:00:00+00:00",
                    "approved_at": "2026-03-27T00:10:00+00:00",
                    "completed_at": None,
                }
            ),
            encoding="utf-8",
        )
        (specs / "spec.md").write_text("# Acceptance Empty Mission\n", encoding="utf-8")

        response = client.get(f"/api/missions/{mission_id}/acceptance-review")

        assert response.status_code == 200
        data = response.json()
        assert data["mission_id"] == mission_id
        assert data["latest_review"] is None
        assert data["summary"]["total_reviews"] == 0
        assert data["review_route"] == f"/?mission={mission_id}&mode=missions&tab=acceptance"

    def test_acceptance_review_endpoint_surfaces_latest_review_and_filed_issues(
        self,
        client,
        repo: Path,
    ):
        mission_id = "mission-acceptance"
        specs = repo / "docs" / "specs" / mission_id
        round_dir = specs / "rounds" / "round-02"
        round_dir.mkdir(parents=True)
        (specs / "mission.json").write_text(
            json.dumps(
                {
                    "mission_id": mission_id,
                    "title": "Acceptance Mission",
                    "status": "approved",
                    "spec_path": f"docs/specs/{mission_id}/spec.md",
                    "acceptance_criteria": ["ship it"],
                    "constraints": [],
                    "interface_contracts": [],
                    "created_at": "2026-03-27T00:00:00+00:00",
                    "approved_at": "2026-03-27T00:10:00+00:00",
                    "completed_at": None,
                }
            ),
            encoding="utf-8",
        )
        (specs / "spec.md").write_text("# Acceptance Mission\n", encoding="utf-8")
        (round_dir / "acceptance_review.json").write_text(
            json.dumps(
                {
                    "status": "fail",
                    "summary": "Home page CTA is missing.",
                    "confidence": 0.93,
                    "evaluator": "acceptance_llm",
                    "acceptance_mode": "impact_sweep",
                    "coverage_status": "partial",
                    "tested_routes": ["/"],
                    "untested_expected_routes": ["/pricing"],
                    "recommended_next_step": "Expand coverage before filing copy-only issues.",
                    "findings": [
                        {"severity": "high", "summary": "Primary CTA missing", "route": "/"}
                    ],
                    "issue_proposals": [
                        {
                            "title": "Restore primary CTA",
                            "summary": "Acceptance evaluator found no CTA in the hero section.",
                            "severity": "high",
                            "confidence": 0.93,
                            "linear_issue_id": "SON-777",
                            "filing_status": "filed",
                            "filing_error": "",
                        }
                    ],
                    "artifacts": {
                        "acceptance_review": "docs/specs/mission-acceptance/rounds/round-02/acceptance_review.json"
                    },
                    "campaign": {
                        "mode": "impact_sweep",
                        "goal": "Sweep home and pricing routes for launch regressions.",
                        "primary_routes": ["/"],
                        "related_routes": ["/pricing"],
                        "coverage_expectations": ["homepage", "pricing"],
                        "filing_policy": "auto_file_regressions_only",
                        "exploration_budget": "medium",
                    },
                }
            ),
            encoding="utf-8",
        )

        response = client.get(f"/api/missions/{mission_id}/acceptance-review")

        assert response.status_code == 200
        data = response.json()
        assert data["summary"]["total_reviews"] == 1
        assert data["summary"]["failures"] == 1
        assert data["summary"]["filed_issues"] == 1
        assert data["latest_review"]["summary"] == "Home page CTA is missing."
        assert data["latest_review"]["acceptance_mode"] == "impact_sweep"
        assert data["latest_review"]["coverage_status"] == "partial"
        assert data["latest_review"]["untested_expected_routes"] == ["/pricing"]
        assert data["latest_review"]["issue_proposals"][0]["linear_issue_id"] == "SON-777"
        assert data["latest_review"]["review_route"] == (
            f"/?mission={mission_id}&mode=missions&tab=acceptance&round=2"
        )

    def test_acceptance_review_endpoint_sorts_rounds_numerically(self, client, repo: Path):
        mission_id = "mission-acceptance-sort"
        specs = repo / "docs" / "specs" / mission_id
        for round_name, summary in (
            ("round-2", "Older review"),
            ("round-10", "Newest review"),
        ):
            round_dir = specs / "rounds" / round_name
            round_dir.mkdir(parents=True, exist_ok=True)
            (round_dir / "acceptance_review.json").write_text(
                json.dumps(
                    {
                        "status": "warn",
                        "summary": summary,
                        "confidence": 0.5,
                        "evaluator": "acceptance_llm",
                        "tested_routes": ["/"],
                        "findings": [],
                        "issue_proposals": [],
                        "artifacts": {},
                    }
                ),
                encoding="utf-8",
            )

        response = client.get(f"/api/missions/{mission_id}/acceptance-review")

        assert response.status_code == 200
        data = response.json()
        assert [review["round_id"] for review in data["reviews"]] == [2, 10]
        assert data["latest_review"]["summary"] == "Newest review"

    def test_mission_detail_includes_acceptance_review_summary(self, client, repo: Path):
        mission_id = "mission-acceptance-detail"
        specs = repo / "docs" / "specs" / mission_id
        round_dir = specs / "rounds" / "round-01"
        round_dir.mkdir(parents=True)
        (specs / "mission.json").write_text(
            json.dumps(
                {
                    "mission_id": mission_id,
                    "title": "Acceptance Detail Mission",
                    "status": "approved",
                    "spec_path": f"docs/specs/{mission_id}/spec.md",
                    "acceptance_criteria": [],
                    "constraints": [],
                    "interface_contracts": [],
                    "created_at": "2026-03-27T00:00:00+00:00",
                    "approved_at": "2026-03-27T00:10:00+00:00",
                    "completed_at": None,
                }
            ),
            encoding="utf-8",
        )
        (specs / "spec.md").write_text("# Acceptance Detail Mission\n", encoding="utf-8")
        (round_dir / "acceptance_review.json").write_text(
            json.dumps(
                {
                    "status": "warn",
                    "summary": "There is one warning to inspect.",
                    "confidence": 0.61,
                    "evaluator": "acceptance_llm",
                    "tested_routes": ["/settings"],
                    "findings": [{"severity": "medium", "summary": "Copy mismatch"}],
                    "issue_proposals": [],
                    "artifacts": {},
                }
            ),
            encoding="utf-8",
        )

        response = client.get(f"/api/missions/{mission_id}/detail")

        assert response.status_code == 200
        data = response.json()
        assert data["acceptance_review"]["summary"]["total_reviews"] == 1
        assert data["acceptance_review"]["review_route"] == (
            f"/?mission={mission_id}&mode=missions&tab=acceptance"
        )

    def test_health(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"

    def test_missions(self, client):
        r = client.get("/api/missions")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_inbox_endpoint_groups_paused_and_failed_missions(self, client, repo: Path):
        paused_id = "mission-paused"
        failed_id = "mission-failed"

        for mission_id, status in ((paused_id, "approved"), (failed_id, "completed")):
            specs = repo / "docs" / "specs" / mission_id
            specs.mkdir(parents=True)
            (specs / "mission.json").write_text(
                json.dumps(
                    {
                        "mission_id": mission_id,
                        "title": mission_id.replace("-", " ").title(),
                        "status": status,
                        "spec_path": f"docs/specs/{mission_id}/spec.md",
                        "acceptance_criteria": [],
                        "constraints": [],
                        "interface_contracts": [],
                        "created_at": "2026-03-25T00:00:00+00:00",
                        "approved_at": "2026-03-25T00:05:00+00:00",
                        "completed_at": None,
                    }
                )
            )
            (specs / "spec.md").write_text("# Spec\n", encoding="utf-8")

        lifecycle_dir = repo / ".spec_orch_runs"
        lifecycle_dir.mkdir(exist_ok=True)
        (lifecycle_dir / "lifecycle_state.json").write_text(
            json.dumps(
                {
                    paused_id: {
                        "mission_id": paused_id,
                        "phase": "executing",
                        "issue_ids": ["SON-1"],
                        "completed_issues": [],
                        "error": None,
                        "updated_at": "2026-03-25T00:20:00+00:00",
                        "current_round": 2,
                        "round_orchestrator_state": {
                            "paused": True,
                            "blocking_questions": ["Approve the revised rollout?"],
                        },
                    },
                    failed_id: {
                        "mission_id": failed_id,
                        "phase": "failed",
                        "issue_ids": ["SON-2"],
                        "completed_issues": [],
                        "error": "verification failed",
                        "updated_at": "2026-03-25T00:30:00+00:00",
                        "current_round": 1,
                        "round_orchestrator_state": {},
                    },
                }
            ),
            encoding="utf-8",
        )

        r = client.get("/api/inbox")
        assert r.status_code == 200
        data = r.json()
        assert data["counts"] == {
            "paused": 1,
            "failed": 1,
            "approvals": 0,
            "budgets": 0,
            "attention": 2,
        }
        assert data["items"][0]["mission_id"] == paused_id
        assert data["items"][0]["kind"] == "paused"
        assert data["items"][0]["summary"] == "Approve the revised rollout?"
        assert data["items"][1]["mission_id"] == failed_id
        assert data["items"][1]["kind"] == "failed"
        assert data["items"][1]["summary"] == "verification failed"

    def test_inbox_endpoint_promotes_ask_human_rounds_to_approval_items(
        self,
        client,
        repo: Path,
    ):
        mission_id = "mission-approval"
        specs = repo / "docs" / "specs" / mission_id
        round_dir = specs / "rounds" / "round-03"
        specs.mkdir(parents=True)
        round_dir.mkdir(parents=True)

        (specs / "mission.json").write_text(
            json.dumps(
                {
                    "mission_id": mission_id,
                    "title": "Approval Mission",
                    "status": "approved",
                    "spec_path": f"docs/specs/{mission_id}/spec.md",
                    "acceptance_criteria": [],
                    "constraints": [],
                    "interface_contracts": [],
                    "created_at": "2026-03-25T00:00:00+00:00",
                    "approved_at": "2026-03-25T00:05:00+00:00",
                    "completed_at": None,
                }
            ),
            encoding="utf-8",
        )
        (specs / "spec.md").write_text("# Approval Mission\n", encoding="utf-8")
        (round_dir / "round_summary.json").write_text(
            json.dumps(
                {
                    "round_id": 3,
                    "wave_id": 1,
                    "status": "decided",
                    "started_at": "2026-03-25T00:10:00+00:00",
                    "completed_at": "2026-03-25T00:18:00+00:00",
                    "worker_results": [],
                    "decision": {
                        "action": "ask_human",
                        "reason_code": "needs_approval",
                        "summary": "Approve the rollout after visual QA review.",
                        "confidence": 0.72,
                        "affected_workers": [],
                        "artifacts": {},
                        "session_ops": {"reuse": [], "spawn": [], "cancel": []},
                        "blocking_questions": ["Approve the rollout after visual QA review?"],
                    },
                }
            ),
            encoding="utf-8",
        )
        (repo / ".spec_orch_runs" / "lifecycle_state.json").write_text(
            json.dumps(
                {
                    mission_id: {
                        "mission_id": mission_id,
                        "phase": "executing",
                        "issue_ids": ["SON-3"],
                        "completed_issues": [],
                        "error": None,
                        "updated_at": "2026-03-25T00:18:30+00:00",
                        "current_round": 3,
                        "round_orchestrator_state": {
                            "paused": True,
                            "blocking_questions": ["Approve the rollout after visual QA review?"],
                        },
                    }
                }
            ),
            encoding="utf-8",
        )

        r = client.get("/api/inbox")
        assert r.status_code == 200
        data = r.json()
        assert data["counts"] == {
            "paused": 0,
            "failed": 0,
            "approvals": 1,
            "budgets": 0,
            "attention": 1,
        }
        assert data["items"] == [
            {
                "mission_id": mission_id,
                "title": "Approval Mission",
                "kind": "approval",
                "phase": "executing",
                "summary": "Approve the rollout after visual QA review.",
                "updated_at": "2026-03-25T00:18:30+00:00",
                "current_round": 3,
                "blocking_question": "Approve the rollout after visual QA review?",
                "decision_action": "ask_human",
                "latest_operator_action": None,
                "approval_state": {
                    "status": "awaiting_human",
                    "summary": "Awaiting operator decision",
                },
                "approval_request": {
                    "round_id": 3,
                    "timestamp": "2026-03-25T00:18:00+00:00",
                    "summary": "Approve the rollout after visual QA review.",
                    "blocking_question": "Approve the rollout after visual QA review?",
                    "decision_action": "ask_human",
                    "review_route": f"/?mission={mission_id}&mode=missions&tab=approvals&round=3",
                    "actions": [
                        {
                            "key": "approve",
                            "label": "Approve",
                            "message": "@approve Approve the rollout after visual QA review?",
                        },
                        {
                            "key": "request_revision",
                            "label": "Request revision",
                            "message": "@request-revision Please revise this round before rollout.",
                        },
                        {
                            "key": "ask_followup",
                            "label": "Ask follow-up",
                            "message": "@follow-up I need more detail before approving this round.",
                        },
                    ],
                },
            }
        ]

    def test_inbox_endpoint_surfaces_latest_operator_action_for_approval_items(
        self,
        client,
        repo: Path,
    ):
        mission_id = "mission-approval-history"
        specs = repo / "docs" / "specs" / mission_id
        round_dir = specs / "rounds" / "round-02"
        operator_dir = specs / "operator"
        specs.mkdir(parents=True)
        round_dir.mkdir(parents=True)
        operator_dir.mkdir(parents=True)

        (specs / "mission.json").write_text(
            json.dumps(
                {
                    "mission_id": mission_id,
                    "title": "Approval History Mission",
                    "status": "approved",
                    "spec_path": f"docs/specs/{mission_id}/spec.md",
                    "acceptance_criteria": [],
                    "constraints": [],
                    "interface_contracts": [],
                    "created_at": "2026-03-25T00:00:00+00:00",
                    "approved_at": "2026-03-25T00:05:00+00:00",
                    "completed_at": None,
                }
            ),
            encoding="utf-8",
        )
        (specs / "spec.md").write_text("# Approval History Mission\n", encoding="utf-8")
        (round_dir / "round_summary.json").write_text(
            json.dumps(
                {
                    "round_id": 2,
                    "wave_id": 1,
                    "status": "decided",
                    "started_at": "2026-03-25T00:10:00+00:00",
                    "completed_at": "2026-03-25T00:16:00+00:00",
                    "worker_results": [],
                    "decision": {
                        "action": "ask_human",
                        "reason_code": "needs_approval",
                        "summary": "Need operator approval before rollout.",
                        "confidence": 0.66,
                        "affected_workers": [],
                        "artifacts": {},
                        "session_ops": {"reuse": [], "spawn": [], "cancel": []},
                        "blocking_questions": ["Approve this rollout?"],
                    },
                }
            ),
            encoding="utf-8",
        )
        (operator_dir / "approval_actions.jsonl").write_text(
            json.dumps(
                {
                    "timestamp": "2026-03-25T00:17:00+00:00",
                    "action_key": "request_revision",
                    "label": "Request revision",
                    "message": "@request-revision Please tighten the rollout evidence.",
                    "channel": "web-dashboard",
                    "status": "sent",
                    "effect": "revision_requested",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (repo / ".spec_orch_runs" / "lifecycle_state.json").write_text(
            json.dumps(
                {
                    mission_id: {
                        "mission_id": mission_id,
                        "phase": "executing",
                        "issue_ids": ["SON-4"],
                        "completed_issues": [],
                        "error": None,
                        "updated_at": "2026-03-25T00:17:30+00:00",
                        "current_round": 2,
                        "round_orchestrator_state": {
                            "paused": True,
                            "blocking_questions": ["Approve this rollout?"],
                        },
                    }
                }
            ),
            encoding="utf-8",
        )

        response = client.get("/api/inbox")
        assert response.status_code == 200
        data = response.json()
        assert data["items"][0]["latest_operator_action"] == {
            "timestamp": "2026-03-25T00:17:00+00:00",
            "action_key": "request_revision",
            "label": "Request revision",
            "message": "@request-revision Please tighten the rollout evidence.",
            "channel": "web-dashboard",
            "status": "sent",
            "effect": "revision_requested",
        }
        assert data["items"][0]["approval_state"] == {
            "status": "revision_requested",
            "summary": "Operator requested revision",
        }

    def test_approvals_endpoint_returns_dedicated_queue(self, client, repo: Path, monkeypatch):
        mission_id = "mission-approval-queue"
        specs = repo / "docs" / "specs" / mission_id
        round_dir = specs / "rounds" / "round-04"
        operator_dir = specs / "operator"
        specs.mkdir(parents=True)
        round_dir.mkdir(parents=True)
        operator_dir.mkdir(parents=True)

        (specs / "mission.json").write_text(
            json.dumps(
                {
                    "mission_id": mission_id,
                    "title": "Approval Queue Mission",
                    "status": "approved",
                    "spec_path": f"docs/specs/{mission_id}/spec.md",
                    "acceptance_criteria": [],
                    "constraints": [],
                    "interface_contracts": [],
                    "created_at": "2026-03-25T00:00:00+00:00",
                    "approved_at": "2026-03-25T00:05:00+00:00",
                    "completed_at": None,
                }
            ),
            encoding="utf-8",
        )
        (specs / "spec.md").write_text("# Approval Queue Mission\n", encoding="utf-8")
        (round_dir / "round_summary.json").write_text(
            json.dumps(
                {
                    "round_id": 4,
                    "wave_id": 2,
                    "status": "decided",
                    "started_at": "2026-03-25T00:18:00+00:00",
                    "completed_at": "2026-03-25T00:22:00+00:00",
                    "worker_results": [],
                    "decision": {
                        "action": "ask_human",
                        "reason_code": "needs_approval",
                        "summary": "Approve rollout after transcript review.",
                        "confidence": 0.77,
                        "affected_workers": [],
                        "artifacts": {},
                        "session_ops": {"reuse": [], "spawn": [], "cancel": []},
                        "blocking_questions": ["Approve rollout after transcript review?"],
                    },
                }
            ),
            encoding="utf-8",
        )
        (operator_dir / "approval_actions.jsonl").write_text(
            json.dumps(
                {
                    "timestamp": "2026-03-25T00:22:30+00:00",
                    "action_key": "ask_followup",
                    "label": "Ask follow-up",
                    "message": "@follow-up Need one more artifact before approval.",
                    "channel": "web-dashboard",
                    "status": "sent",
                    "effect": "followup_requested",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (repo / ".spec_orch_runs" / "lifecycle_state.json").write_text(
            json.dumps(
                {
                    mission_id: {
                        "mission_id": mission_id,
                        "phase": "executing",
                        "issue_ids": ["SON-55"],
                        "completed_issues": [],
                        "error": None,
                        "updated_at": "2026-03-25T00:23:00+00:00",
                        "current_round": 4,
                        "round_orchestrator_state": {
                            "paused": True,
                            "blocking_questions": ["Approve rollout after transcript review?"],
                        },
                    }
                }
            ),
            encoding="utf-8",
        )

        class FakeDateTime:
            @staticmethod
            def now(_tz=None):
                return real_datetime(2026, 3, 25, 0, 23, tzinfo=UTC)

            @staticmethod
            def fromisoformat(value: str):
                return real_datetime.fromisoformat(value)

        monkeypatch.setattr("spec_orch.dashboard.surfaces.datetime", FakeDateTime)

        response = client.get("/api/approvals")
        assert response.status_code == 200
        data = response.json()
        assert data["counts"] == {
            "pending": 1,
            "missions": 1,
            "requires_followup": 1,
            "stale": 0,
            "aged": 0,
            "failed_actions": 0,
        }
        assert data["items"] == [
            {
                "mission_id": mission_id,
                "title": "Approval Queue Mission",
                "kind": "approval",
                "phase": "executing",
                "summary": "Approve rollout after transcript review.",
                "updated_at": "2026-03-25T00:23:00+00:00",
                "current_round": 4,
                "blocking_question": "Approve rollout after transcript review?",
                "decision_action": "ask_human",
                "latest_operator_action": {
                    "timestamp": "2026-03-25T00:22:30+00:00",
                    "action_key": "ask_followup",
                    "label": "Ask follow-up",
                    "message": "@follow-up Need one more artifact before approval.",
                    "channel": "web-dashboard",
                    "status": "sent",
                    "effect": "followup_requested",
                },
                "approval_state": {
                    "status": "followup_requested",
                    "summary": "Operator requested follow-up",
                },
                "recommended_action": "Approve",
                "wait_minutes": 1,
                "urgency": "followup",
                "age_bucket": "fresh",
                "review_route": f"/?mission={mission_id}&mode=missions&tab=approvals",
                "available_actions": ["approve", "request_revision", "ask_followup"],
                "approval_request": {
                    "round_id": 4,
                    "timestamp": "2026-03-25T00:22:00+00:00",
                    "summary": "Approve rollout after transcript review.",
                    "blocking_question": "Approve rollout after transcript review?",
                    "decision_action": "ask_human",
                    "review_route": f"/?mission={mission_id}&mode=missions&tab=approvals&round=4",
                    "actions": [
                        {
                            "key": "approve",
                            "label": "Approve",
                            "message": "@approve Approve rollout after transcript review?",
                        },
                        {
                            "key": "request_revision",
                            "label": "Request revision",
                            "message": "@request-revision Please revise this round before rollout.",
                        },
                        {
                            "key": "ask_followup",
                            "label": "Ask follow-up",
                            "message": "@follow-up I need more detail before approving this round.",
                        },
                    ],
                },
            }
        ]

    def test_approvals_batch_action_endpoint_processes_multiple_items(
        self,
        client,
        repo: Path,
        monkeypatch,
    ):
        mission_ids = ["mission-batch-a", "mission-batch-b"]
        issue_ids = {
            "mission-batch-a": "SON-BATCH-A",
            "mission-batch-b": "SON-BATCH-B",
        }
        for mission_id in mission_ids:
            specs = repo / "docs" / "specs" / mission_id
            round_dir = specs / "rounds" / "round-01"
            specs.mkdir(parents=True)
            round_dir.mkdir(parents=True)
            (specs / "mission.json").write_text(
                json.dumps(
                    {
                        "mission_id": mission_id,
                        "title": mission_id,
                        "status": "approved",
                        "spec_path": f"docs/specs/{mission_id}/spec.md",
                        "acceptance_criteria": [],
                        "constraints": [],
                        "interface_contracts": [],
                        "created_at": "2026-03-25T00:00:00+00:00",
                        "approved_at": "2026-03-25T00:05:00+00:00",
                        "completed_at": None,
                    }
                ),
                encoding="utf-8",
            )
            (specs / "spec.md").write_text("# Approval Batch Mission\n", encoding="utf-8")
            (round_dir / "round_summary.json").write_text(
                json.dumps(
                    {
                        "round_id": 1,
                        "wave_id": 0,
                        "status": "decided",
                        "started_at": "2026-03-25T00:10:00+00:00",
                        "completed_at": "2026-03-25T00:11:00+00:00",
                        "worker_results": [],
                        "decision": {
                            "action": "ask_human",
                            "reason_code": "needs_approval",
                            "summary": "Approve rollout after QA.",
                            "confidence": 0.8,
                            "affected_workers": [],
                            "artifacts": {},
                            "session_ops": {"reuse": [], "spawn": [], "cancel": []},
                            "blocking_questions": ["Approve rollout after QA?"],
                        },
                    }
                ),
                encoding="utf-8",
            )

        calls: list[tuple[str, str, str]] = []

        class FakeLifecycleManager:
            def get_state(self, tracked_mission_id: str):
                return type(
                    "State",
                    (),
                    {
                        "issue_ids": [issue_ids[tracked_mission_id]],
                        "completed_issues": [],
                    },
                )()

            def inject_btw(self, issue_id: str, message: str, channel: str) -> bool:
                calls.append((issue_id, message, channel))
                return issue_id != issue_ids["mission-batch-b"]

        monkeypatch.setattr(
            "spec_orch.dashboard.routes.dashboard_app._get_lifecycle_manager",
            lambda _root: FakeLifecycleManager(),
        )

        response = client.post(
            "/api/approvals/batch-action",
            content=json.dumps(
                {
                    "mission_ids": mission_ids,
                    "action_key": "approve",
                }
            ),
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["summary"] == {
            "requested": 2,
            "processed": 2,
            "applied": 1,
            "not_applied": 1,
            "failed": 0,
        }
        assert payload["focus_mission_id"] == "mission-batch-b"
        assert payload["next_pending_mission_id"] == "mission-batch-b"
        assert [item["mission_id"] for item in payload["results"]] == mission_ids
        assert payload["results"][0]["action"]["status"] == "applied"
        assert payload["results"][1]["action"]["status"] == "not_applied"
        assert payload["results"][0]["result_summary"] == "Applied guidance to mission-batch-a"
        assert (
            payload["results"][1]["result_summary"] == "Recorded guidance only for mission-batch-b"
        )
        assert payload["results"][0]["redirect_to"].endswith(
            "mission=mission-batch-a&mode=missions&tab=approvals"
        )
        assert payload["results"][1]["redirect_to"].endswith(
            "mission=mission-batch-b&mode=missions&tab=approvals"
        )
        assert calls == [
            ("SON-BATCH-A", "@approve Approve rollout after QA?", "web-dashboard"),
            ("SON-BATCH-B", "@approve Approve rollout after QA?", "web-dashboard"),
        ]

    def test_approvals_batch_action_counts_bare_errors_as_failed(
        self,
        client,
        repo: Path,
        monkeypatch,
    ):
        mission_ids = ["mission-batch-error-a", "mission-batch-error-b"]
        for mission_id in mission_ids:
            specs = repo / "docs" / "specs" / mission_id
            round_dir = specs / "rounds" / "round-01"
            specs.mkdir(parents=True)
            round_dir.mkdir(parents=True)
            (specs / "mission.json").write_text(
                json.dumps(
                    {
                        "mission_id": mission_id,
                        "title": mission_id,
                        "status": "approved",
                        "spec_path": f"docs/specs/{mission_id}/spec.md",
                        "acceptance_criteria": [],
                        "constraints": [],
                        "interface_contracts": [],
                        "created_at": "2026-03-25T00:00:00+00:00",
                        "approved_at": "2026-03-25T00:05:00+00:00",
                        "completed_at": None,
                    }
                ),
                encoding="utf-8",
            )
            (specs / "spec.md").write_text("# Approval Batch Error Mission\n", encoding="utf-8")
            (round_dir / "round_summary.json").write_text(
                json.dumps(
                    {
                        "round_id": 1,
                        "wave_id": 0,
                        "status": "decided",
                        "started_at": "2026-03-25T00:10:00+00:00",
                        "completed_at": "2026-03-25T00:11:00+00:00",
                        "worker_results": [],
                        "decision": {
                            "action": "ask_human",
                            "reason_code": "needs_approval",
                            "summary": "Approve rollout after QA.",
                            "confidence": 0.8,
                            "affected_workers": [],
                            "artifacts": {},
                            "session_ops": {"reuse": [], "spawn": [], "cancel": []},
                            "blocking_questions": ["Approve rollout after QA?"],
                        },
                    }
                ),
                encoding="utf-8",
            )

        monkeypatch.setattr(
            "spec_orch.dashboard.routes.dashboard_app._get_lifecycle_manager",
            lambda _root: None,
        )

        response = client.post(
            "/api/approvals/batch-action",
            content=json.dumps(
                {
                    "mission_ids": mission_ids,
                    "action_key": "approve",
                }
            ),
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["summary"] == {
            "requested": 2,
            "processed": 2,
            "applied": 0,
            "not_applied": 0,
            "failed": 2,
        }
        assert payload["focus_mission_id"] == "mission-batch-error-a"
        assert payload["next_pending_mission_id"] == "mission-batch-error-a"
        assert payload["results"][0]["action"]["status"] == "failed"
        assert payload["results"][1]["action"]["status"] == "failed"

    def test_approvals_endpoint_surfaces_stale_and_failed_counts(
        self,
        client,
        repo: Path,
        monkeypatch,
    ):
        fresh_id = "mission-approval-fresh"
        stale_id = "mission-approval-stale"
        aged_id = "mission-approval-aged"

        for mission_id, completed_at, updated_at, history in [
            (
                fresh_id,
                "2026-03-25T03:22:00+00:00",
                "2026-03-25T03:23:00+00:00",
                None,
            ),
            (
                stale_id,
                "2026-03-25T02:00:00+00:00",
                "2026-03-25T02:30:00+00:00",
                None,
            ),
            (
                aged_id,
                "2026-03-25T00:00:00+00:00",
                "2026-03-25T03:30:00+00:00",
                {
                    "timestamp": "2026-03-25T03:31:00+00:00",
                    "action_key": "approve",
                    "label": "Approve",
                    "message": "@approve Approve this round.",
                    "channel": "web-dashboard",
                    "status": "failed",
                    "effect": "approval_granted",
                },
            ),
        ]:
            specs = repo / "docs" / "specs" / mission_id
            round_dir = specs / "rounds" / "round-01"
            specs.mkdir(parents=True)
            round_dir.mkdir(parents=True)
            (specs / "mission.json").write_text(
                json.dumps(
                    {
                        "mission_id": mission_id,
                        "title": mission_id,
                        "status": "approved",
                        "spec_path": f"docs/specs/{mission_id}/spec.md",
                        "acceptance_criteria": [],
                        "constraints": [],
                        "interface_contracts": [],
                        "created_at": "2026-03-25T00:00:00+00:00",
                        "approved_at": "2026-03-25T00:05:00+00:00",
                        "completed_at": None,
                    }
                ),
                encoding="utf-8",
            )
            (specs / "spec.md").write_text("# Approval Mission\n", encoding="utf-8")
            (round_dir / "round_summary.json").write_text(
                json.dumps(
                    {
                        "round_id": 1,
                        "wave_id": 0,
                        "status": "decided",
                        "started_at": "2026-03-25T00:00:00+00:00",
                        "completed_at": completed_at,
                        "worker_results": [],
                        "decision": {
                            "action": "ask_human",
                            "reason_code": "needs_approval",
                            "summary": "Approve this round.",
                            "confidence": 0.8,
                            "affected_workers": [],
                            "artifacts": {},
                            "session_ops": {"reuse": [], "spawn": [], "cancel": []},
                            "blocking_questions": ["Approve this round?"],
                        },
                    }
                ),
                encoding="utf-8",
            )
            if history is not None:
                operator_dir = specs / "operator"
                operator_dir.mkdir(parents=True, exist_ok=True)
                (operator_dir / "approval_actions.jsonl").write_text(
                    json.dumps(history) + "\n",
                    encoding="utf-8",
                )

            lifecycle_payload = (
                json.loads(
                    (repo / ".spec_orch_runs" / "lifecycle_state.json").read_text(encoding="utf-8")
                )
                if (repo / ".spec_orch_runs" / "lifecycle_state.json").exists()
                else {}
            )
            lifecycle_payload[mission_id] = {
                "mission_id": mission_id,
                "phase": "executing",
                "issue_ids": [],
                "completed_issues": [],
                "error": None,
                "updated_at": updated_at,
                "current_round": 1,
                "round_orchestrator_state": {
                    "paused": True,
                    "blocking_questions": ["Approve this round?"],
                },
            }
            (repo / ".spec_orch_runs" / "lifecycle_state.json").write_text(
                json.dumps(lifecycle_payload),
                encoding="utf-8",
            )

        class FakeDateTime:
            @staticmethod
            def now(_tz=None):
                return real_datetime(2026, 3, 25, 3, 30, tzinfo=UTC)

            @staticmethod
            def fromisoformat(value: str):
                return real_datetime.fromisoformat(value)

        monkeypatch.setattr("spec_orch.dashboard.surfaces.datetime", FakeDateTime)

        response = client.get("/api/approvals")
        assert response.status_code == 200
        data = response.json()
        assert data["counts"] == {
            "pending": 3,
            "missions": 3,
            "requires_followup": 0,
            "stale": 1,
            "aged": 1,
            "failed_actions": 1,
        }

    def test_approvals_endpoint_uses_current_time_for_wait_minutes(
        self,
        client,
        repo: Path,
        monkeypatch,
    ):
        mission_id = "mission-approval-clock"
        specs = repo / "docs" / "specs" / mission_id
        round_dir = specs / "rounds" / "round-01"
        specs.mkdir(parents=True)
        round_dir.mkdir(parents=True)
        (specs / "mission.json").write_text(
            json.dumps(
                {
                    "mission_id": mission_id,
                    "title": "Approval Clock Mission",
                    "status": "approved",
                    "spec_path": f"docs/specs/{mission_id}/spec.md",
                    "acceptance_criteria": [],
                    "constraints": [],
                    "interface_contracts": [],
                    "created_at": "2026-03-25T00:00:00+00:00",
                    "approved_at": "2026-03-25T00:05:00+00:00",
                    "completed_at": None,
                }
            ),
            encoding="utf-8",
        )
        (specs / "spec.md").write_text("# Approval Clock Mission\n", encoding="utf-8")
        (round_dir / "round_summary.json").write_text(
            json.dumps(
                {
                    "round_id": 1,
                    "wave_id": 0,
                    "status": "decided",
                    "started_at": "2026-03-25T00:00:00+00:00",
                    "completed_at": "2026-03-25T00:00:00+00:00",
                    "worker_results": [],
                    "decision": {
                        "action": "ask_human",
                        "reason_code": "needs_approval",
                        "summary": "Approve this round.",
                        "confidence": 0.8,
                        "affected_workers": [],
                        "artifacts": {},
                        "session_ops": {"reuse": [], "spawn": [], "cancel": []},
                        "blocking_questions": ["Approve this round?"],
                    },
                }
            ),
            encoding="utf-8",
        )
        (repo / ".spec_orch_runs" / "lifecycle_state.json").write_text(
            json.dumps(
                {
                    mission_id: {
                        "mission_id": mission_id,
                        "phase": "executing",
                        "issue_ids": [],
                        "completed_issues": [],
                        "error": None,
                        "updated_at": "2026-03-25T00:01:00+00:00",
                        "current_round": 1,
                        "round_orchestrator_state": {
                            "paused": True,
                            "blocking_questions": ["Approve this round?"],
                        },
                    }
                }
            ),
            encoding="utf-8",
        )

        class FakeDateTime:
            @staticmethod
            def now(_tz=None):
                return real_datetime(2026, 3, 25, 2, 30, tzinfo=UTC)

            @staticmethod
            def fromisoformat(value: str):
                return real_datetime.fromisoformat(value)

        monkeypatch.setattr("spec_orch.dashboard.surfaces.datetime", FakeDateTime)

        response = client.get("/api/approvals")

        assert response.status_code == 200
        payload = response.json()
        assert payload["counts"]["stale"] == 1
        assert payload["items"][0]["wait_minutes"] == 150
        assert payload["items"][0]["age_bucket"] == "stale"

    def test_inbox_endpoint_ignores_stale_historical_approval_requests(
        self,
        client,
        repo: Path,
    ):
        mission_id = "mission-historical-approval"
        specs = repo / "docs" / "specs" / mission_id
        round_one = specs / "rounds" / "round-01"
        round_two = specs / "rounds" / "round-02"
        specs.mkdir(parents=True)
        round_one.mkdir(parents=True)
        round_two.mkdir(parents=True)
        (specs / "mission.json").write_text(
            json.dumps(
                {
                    "mission_id": mission_id,
                    "title": "Historical Approval Mission",
                    "status": "approved",
                    "spec_path": f"docs/specs/{mission_id}/spec.md",
                    "acceptance_criteria": [],
                    "constraints": [],
                    "interface_contracts": [],
                    "created_at": "2026-03-25T00:00:00+00:00",
                    "approved_at": "2026-03-25T00:05:00+00:00",
                    "completed_at": None,
                }
            ),
            encoding="utf-8",
        )
        (specs / "spec.md").write_text("# Historical Approval Mission\n", encoding="utf-8")
        (round_one / "round_summary.json").write_text(
            json.dumps(
                {
                    "round_id": 1,
                    "wave_id": 0,
                    "status": "decided",
                    "started_at": "2026-03-25T00:00:00+00:00",
                    "completed_at": "2026-03-25T00:10:00+00:00",
                    "worker_results": [],
                    "decision": {
                        "action": "ask_human",
                        "reason_code": "needs_approval",
                        "summary": "Approve this round.",
                        "confidence": 0.8,
                        "affected_workers": [],
                        "artifacts": {},
                        "session_ops": {"reuse": [], "spawn": [], "cancel": []},
                        "blocking_questions": ["Approve this round?"],
                    },
                }
            ),
            encoding="utf-8",
        )
        (round_two / "round_summary.json").write_text(
            json.dumps(
                {
                    "round_id": 2,
                    "wave_id": 1,
                    "status": "decided",
                    "started_at": "2026-03-25T00:11:00+00:00",
                    "completed_at": "2026-03-25T00:20:00+00:00",
                    "worker_results": [],
                    "decision": {
                        "action": "stop",
                        "reason_code": "verification_failed",
                        "summary": "Mission failed after approval request.",
                        "confidence": 0.4,
                        "affected_workers": [],
                        "artifacts": {},
                        "session_ops": {"reuse": [], "spawn": [], "cancel": []},
                        "blocking_questions": [],
                    },
                }
            ),
            encoding="utf-8",
        )
        (repo / ".spec_orch_runs" / "lifecycle_state.json").write_text(
            json.dumps(
                {
                    mission_id: {
                        "mission_id": mission_id,
                        "phase": "failed",
                        "issue_ids": [],
                        "completed_issues": [],
                        "error": "Mission execution failed.",
                        "updated_at": "2026-03-25T00:21:00+00:00",
                        "current_round": 2,
                        "round_orchestrator_state": {},
                    }
                }
            ),
            encoding="utf-8",
        )

        response = client.get("/api/inbox")

        assert response.status_code == 200
        payload = response.json()
        assert payload["counts"]["approvals"] == 0
        assert payload["counts"]["failed"] == 1
        assert payload["items"] == [
            {
                "mission_id": mission_id,
                "title": "Historical Approval Mission",
                "kind": "failed",
                "phase": "failed",
                "summary": "Mission execution failed.",
                "updated_at": "2026-03-25T00:21:00+00:00",
                "current_round": 2,
            }
        ]

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
        assert data["approval_request"] is None
        assert data["artifacts"]["spec"].endswith(f"docs/specs/{mission_id}/spec.md")

    def test_mission_detail_endpoint_surfaces_approval_request(self, client, repo: Path):
        mission_id = "mission-detail-approval"
        specs = repo / "docs" / "specs" / mission_id
        round_dir = specs / "rounds" / "round-02"
        specs.mkdir(parents=True)
        round_dir.mkdir(parents=True)

        (specs / "mission.json").write_text(
            json.dumps(
                {
                    "mission_id": mission_id,
                    "title": "Mission Detail Approval",
                    "status": "approved",
                    "spec_path": f"docs/specs/{mission_id}/spec.md",
                    "acceptance_criteria": ["Ship safely"],
                    "constraints": ["Keep rollback path available"],
                    "interface_contracts": [],
                    "created_at": "2026-03-25T00:00:00+00:00",
                    "approved_at": "2026-03-25T00:05:00+00:00",
                    "completed_at": None,
                }
            ),
            encoding="utf-8",
        )
        (specs / "spec.md").write_text("# Mission Detail Approval\n", encoding="utf-8")
        (round_dir / "round_summary.json").write_text(
            json.dumps(
                {
                    "round_id": 2,
                    "wave_id": 1,
                    "status": "decided",
                    "started_at": "2026-03-25T00:10:00+00:00",
                    "completed_at": "2026-03-25T00:12:30+00:00",
                    "worker_results": [],
                    "decision": {
                        "action": "ask_human",
                        "reason_code": "needs_review",
                        "summary": "Approve the rollout after checking the visual diff.",
                        "confidence": 0.78,
                        "affected_workers": [],
                        "artifacts": {
                            "review_memo": f"docs/specs/{mission_id}/rounds/round-02/supervisor_review.md"
                        },
                        "session_ops": {"reuse": [], "spawn": [], "cancel": []},
                        "blocking_questions": ["Approve rollout after visual diff review?"],
                    },
                }
            ),
            encoding="utf-8",
        )
        (repo / ".spec_orch_runs" / "lifecycle_state.json").write_text(
            json.dumps(
                {
                    mission_id: {
                        "mission_id": mission_id,
                        "phase": "executing",
                        "issue_ids": ["SON-500"],
                        "completed_issues": [],
                        "error": None,
                        "updated_at": "2026-03-25T00:13:00+00:00",
                        "current_round": 2,
                        "round_orchestrator_state": {
                            "paused": True,
                            "blocking_questions": ["Approve rollout after visual diff review?"],
                        },
                    }
                }
            ),
            encoding="utf-8",
        )

        r = client.get(f"/api/missions/{mission_id}/detail")
        assert r.status_code == 200
        data = r.json()
        assert data["approval_request"] == {
            "round_id": 2,
            "timestamp": "2026-03-25T00:12:30+00:00",
            "summary": "Approve the rollout after checking the visual diff.",
            "blocking_question": "Approve rollout after visual diff review?",
            "decision_action": "ask_human",
            "review_route": f"/?mission={mission_id}&mode=missions&tab=approvals&round=2",
            "actions": [
                {
                    "key": "approve",
                    "label": "Approve",
                    "message": "@approve Approve rollout after visual diff review?",
                },
                {
                    "key": "request_revision",
                    "label": "Request revision",
                    "message": "@request-revision Please revise this round before rollout.",
                },
                {
                    "key": "ask_followup",
                    "label": "Ask follow-up",
                    "message": "@follow-up I need more detail before approving this round.",
                },
            ],
        }
        assert data["approval_history"] == []
        assert data["approval_state"] == {
            "status": "awaiting_human",
            "summary": "Awaiting operator decision",
        }
        assert data["visual_qa"] == {
            "mission_id": mission_id,
            "summary": {
                "total_rounds": 0,
                "blocking_findings": 0,
                "warning_findings": 0,
                "latest_confidence": 0.0,
                "blocking_rounds": [],
                "gallery_items": 0,
                "diff_items": 0,
                "comparison_rounds": 0,
                "focus_transcript_route": None,
            },
            "review_route": f"/?mission={mission_id}&mode=missions&tab=visual",
            "rounds": [],
        }
        assert data["costs"] == {
            "mission_id": mission_id,
            "summary": {
                "workers": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0.0,
                "budget_status": "unconfigured",
                "thresholds": None,
                "incident_count": 0,
                "remaining_budget_usd": None,
            },
            "review_route": f"/?mission={mission_id}&mode=missions&tab=costs",
            "focus_packet_id": None,
            "highest_cost_worker": None,
            "incidents": [],
            "workers": [],
        }

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
        assert data["summary"] == {
            "entry_count": 5,
            "kind_counts": {"activity": 2, "event": 2, "incoming": 1},
            "block_counts": {
                "activity": 2,
                "message": 1,
                "milestone": 1,
                "tool": 1,
            },
            "latest_timestamp": "2026-03-25T00:12:00Z",
            "operator_readout": "1 milestones, 1 tool blocks, 0 alerts, latest signal at 2026-03-25T00:12:00Z",
        }
        assert data["milestones"] == [
            {
                "timestamp": "2026-03-25T00:11:30Z",
                "event_type": "mission_packet_started",
                "message": "packet started",
            }
        ]
        assert data["blocks"] == [
            {
                "block_type": "activity",
                "emphasis": "log",
                "timestamp": "2026-03-25T00:11:00Z",
                "title": "BUILDER packet started",
                "body": "2026-03-25T00:11:00Z BUILDER packet started",
                "source_path": f"docs/specs/{mission_id}/workers/{packet_id}/telemetry/activity.log",
                "jump_targets": [
                    {
                        "kind": "source",
                        "label": "Activity log",
                        "path": f"docs/specs/{mission_id}/workers/{packet_id}/telemetry/activity.log",
                        "href": f"/artifacts/docs/specs/{mission_id}/workers/{packet_id}/telemetry/activity.log",
                    }
                ],
            },
            {
                "block_type": "milestone",
                "emphasis": "milestone",
                "timestamp": "2026-03-25T00:11:30Z",
                "title": "packet started",
                "body": "mission_packet_started",
                "source_path": f"docs/specs/{mission_id}/workers/{packet_id}/telemetry/events.jsonl",
                "details": {
                    "timestamp": "2026-03-25T00:11:30Z",
                    "event_type": "mission_packet_started",
                    "message": "packet started",
                },
                "jump_targets": [
                    {
                        "kind": "source",
                        "label": "Events stream",
                        "path": f"docs/specs/{mission_id}/workers/{packet_id}/telemetry/events.jsonl",
                        "href": f"/artifacts/docs/specs/{mission_id}/workers/{packet_id}/telemetry/events.jsonl",
                    }
                ],
            },
            {
                "block_type": "message",
                "emphasis": "narrative",
                "timestamp": "2026-03-25T00:11:40Z",
                "title": "Implementing mission detail now.",
                "body": "assistant_message",
                "source_path": f"docs/specs/{mission_id}/workers/{packet_id}/telemetry/incoming_events.jsonl",
                "details": {
                    "ts": "2026-03-25T00:11:40Z",
                    "kind": "assistant_message",
                    "excerpt": "Implementing mission detail now.",
                },
                "jump_targets": [
                    {
                        "kind": "source",
                        "label": "Incoming events",
                        "path": f"docs/specs/{mission_id}/workers/{packet_id}/telemetry/incoming_events.jsonl",
                        "href": f"/artifacts/docs/specs/{mission_id}/workers/{packet_id}/telemetry/incoming_events.jsonl",
                    }
                ],
            },
            {
                "block_type": "tool",
                "emphasis": "tool",
                "timestamp": "2026-03-25T00:11:45Z",
                "title": "applied patch",
                "body": "tool_call_completed",
                "source_path": f"docs/specs/{mission_id}/workers/{packet_id}/telemetry/events.jsonl",
                "details": {
                    "timestamp": "2026-03-25T00:11:45Z",
                    "event_type": "tool_call_completed",
                    "message": "applied patch",
                },
                "jump_targets": [
                    {
                        "kind": "source",
                        "label": "Events stream",
                        "path": f"docs/specs/{mission_id}/workers/{packet_id}/telemetry/events.jsonl",
                        "href": f"/artifacts/docs/specs/{mission_id}/workers/{packet_id}/telemetry/events.jsonl",
                    }
                ],
            },
            {
                "block_type": "activity",
                "emphasis": "log",
                "timestamp": "2026-03-25T00:12:00Z",
                "title": "BUILDER packet completed",
                "body": "2026-03-25T00:12:00Z BUILDER packet completed",
                "source_path": f"docs/specs/{mission_id}/workers/{packet_id}/telemetry/activity.log",
                "jump_targets": [
                    {
                        "kind": "source",
                        "label": "Activity log",
                        "path": f"docs/specs/{mission_id}/workers/{packet_id}/telemetry/activity.log",
                        "href": f"/artifacts/docs/specs/{mission_id}/workers/{packet_id}/telemetry/activity.log",
                    }
                ],
            },
        ]
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
        assert data["summary"] == {
            "entry_count": 0,
            "kind_counts": {},
            "block_counts": {},
            "latest_timestamp": None,
        }
        assert data["milestones"] == []
        assert data["blocks"] == []
        assert data["telemetry"] == {
            "activity_log": None,
            "events": None,
            "incoming": None,
        }

    def test_packet_transcript_endpoint_includes_round_evidence_blocks(self, client, repo: Path):
        mission_id = "mission-transcript-evidence"
        packet_id = "pkt-1"
        telemetry = repo / "docs" / "specs" / mission_id / "workers" / packet_id / "telemetry"
        round_dir = repo / "docs" / "specs" / mission_id / "rounds" / "round-02"
        telemetry.mkdir(parents=True)
        round_dir.mkdir(parents=True)

        (telemetry / "activity.log").write_text(
            "2026-03-25T00:11:00Z BUILDER packet started\n",
            encoding="utf-8",
        )
        (round_dir / "round_summary.json").write_text(
            json.dumps(
                {
                    "round_id": 2,
                    "wave_id": 1,
                    "status": "decided",
                    "started_at": "2026-03-25T00:12:10Z",
                    "completed_at": "2026-03-25T00:12:30Z",
                    "worker_results": [
                        {
                            "packet_id": packet_id,
                            "title": "Build mission detail",
                            "report_path": f"docs/specs/{mission_id}/workers/{packet_id}/builder_report.json",
                            "succeeded": True,
                        }
                    ],
                    "decision": {
                        "action": "ask_human",
                        "reason_code": "needs_review",
                        "summary": "Need human approval before rollout.",
                        "confidence": 0.74,
                        "affected_workers": [packet_id],
                        "artifacts": {},
                        "session_ops": {"reuse": [], "spawn": [], "cancel": []},
                        "blocking_questions": ["Approve rollout?"],
                    },
                }
            ),
            encoding="utf-8",
        )
        (round_dir / "visual_evaluation.json").write_text(
            json.dumps(
                {
                    "evaluator": "playwright",
                    "summary": "Visual QA found a spacing regression.",
                    "confidence": 0.81,
                    "findings": [{"severity": "blocking", "message": "Header overlaps metrics."}],
                    "artifacts": {
                        "dashboard": f"docs/specs/{mission_id}/rounds/round-02/visual/dashboard.png"
                    },
                }
            ),
            encoding="utf-8",
        )

        r = client.get(f"/api/missions/{mission_id}/packets/{packet_id}/transcript")
        assert r.status_code == 200
        data = r.json()
        assert data["blocks"][-2:] == [
            {
                "block_type": "supervisor",
                "emphasis": "decision",
                "timestamp": "2026-03-25T00:12:30Z",
                "title": "Need human approval before rollout.",
                "body": "ask_human",
                "artifact_path": f"docs/specs/{mission_id}/rounds/round-02/supervisor_review.md",
                "review_route": f"/?mission={mission_id}&mode=missions&tab=approvals&round=2",
                "details": {
                    "reason_code": "needs_review",
                    "confidence": 0.74,
                    "blocking_questions": ["Approve rollout?"],
                },
                "jump_targets": [
                    {
                        "kind": "artifact",
                        "label": "Supervisor review",
                        "path": f"docs/specs/{mission_id}/rounds/round-02/supervisor_review.md",
                        "href": f"/artifacts/docs/specs/{mission_id}/rounds/round-02/supervisor_review.md",
                    }
                ],
            },
            {
                "block_type": "visual_finding",
                "emphasis": "alert",
                "timestamp": "2026-03-25T00:12:30Z",
                "title": "Visual QA found a spacing regression.",
                "body": "playwright",
                "artifact_path": f"docs/specs/{mission_id}/rounds/round-02/visual_evaluation.json",
                "review_route": f"/?mission={mission_id}&mode=missions&tab=visual&round=2",
                "details": {
                    "confidence": 0.81,
                    "findings": [{"severity": "blocking", "message": "Header overlaps metrics."}],
                    "artifacts": {
                        "dashboard": f"docs/specs/{mission_id}/rounds/round-02/visual/dashboard.png"
                    },
                },
                "jump_targets": [
                    {
                        "kind": "artifact",
                        "label": "Visual evaluation",
                        "path": f"docs/specs/{mission_id}/rounds/round-02/visual_evaluation.json",
                        "href": f"/artifacts/docs/specs/{mission_id}/rounds/round-02/visual_evaluation.json",
                    },
                    {
                        "kind": "artifact",
                        "label": "dashboard",
                        "path": f"docs/specs/{mission_id}/rounds/round-02/visual/dashboard.png",
                        "href": f"/artifacts/docs/specs/{mission_id}/rounds/round-02/visual/dashboard.png",
                    },
                ],
            },
        ]

    def test_visual_qa_endpoint_aggregates_round_findings(self, client, repo: Path):
        mission_id = "mission-visual-qa"
        round_dir = repo / "docs" / "specs" / mission_id / "rounds" / "round-02"
        specs = repo / "docs" / "specs" / mission_id
        specs.mkdir(parents=True)
        round_dir.mkdir(parents=True)

        (specs / "mission.json").write_text(
            json.dumps(
                {
                    "mission_id": mission_id,
                    "title": "Visual QA Mission",
                    "status": "approved",
                    "spec_path": f"docs/specs/{mission_id}/spec.md",
                    "acceptance_criteria": [],
                    "constraints": [],
                    "interface_contracts": [],
                    "created_at": "2026-03-25T00:00:00+00:00",
                    "approved_at": "2026-03-25T00:05:00+00:00",
                    "completed_at": None,
                }
            ),
            encoding="utf-8",
        )
        (specs / "spec.md").write_text("# Visual QA Mission\n", encoding="utf-8")
        (round_dir / "visual_evaluation.json").write_text(
            json.dumps(
                {
                    "evaluator": "playwright",
                    "summary": "Visual QA found a spacing regression.",
                    "confidence": 0.81,
                    "findings": [
                        {"severity": "blocking", "message": "Header overlaps metrics."},
                        {"severity": "warning", "message": "Sidebar spacing is tight."},
                    ],
                    "artifacts": {
                        "dashboard": f"docs/specs/{mission_id}/rounds/round-02/visual/dashboard.png"
                    },
                }
            ),
            encoding="utf-8",
        )

        response = client.get(f"/api/missions/{mission_id}/visual-qa")
        assert response.status_code == 200
        data = response.json()
        assert data == {
            "mission_id": mission_id,
            "summary": {
                "total_rounds": 1,
                "blocking_findings": 1,
                "warning_findings": 1,
                "latest_confidence": 0.81,
                "blocking_rounds": [2],
                "gallery_items": 1,
                "diff_items": 0,
                "comparison_rounds": 0,
                "focus_transcript_route": None,
            },
            "review_route": f"/?mission={mission_id}&mode=missions&tab=visual",
            "rounds": [
                {
                    "round_id": 2,
                    "summary": "Visual QA found a spacing regression.",
                    "confidence": 0.81,
                    "status": "blocking",
                    "artifact_path": f"docs/specs/{mission_id}/rounds/round-02/visual_evaluation.json",
                    "findings": [
                        {"severity": "blocking", "message": "Header overlaps metrics."},
                        {"severity": "warning", "message": "Sidebar spacing is tight."},
                    ],
                    "artifacts": {
                        "dashboard": f"docs/specs/{mission_id}/rounds/round-02/visual/dashboard.png"
                    },
                    "gallery": [
                        {
                            "label": "dashboard",
                            "path": f"docs/specs/{mission_id}/rounds/round-02/visual/dashboard.png",
                            "kind": "image",
                        }
                    ],
                    "primary_artifact": f"docs/specs/{mission_id}/rounds/round-02/visual/dashboard.png",
                    "comparison": None,
                    "review_route": f"/?mission={mission_id}&mode=missions&tab=visual&round=2",
                    "transcript_routes": [],
                }
            ],
        }

    def test_visual_qa_endpoint_promotes_diff_first_comparisons(self, client, repo: Path):
        mission_id = "mission-visual-diff"
        round_dir = repo / "docs" / "specs" / mission_id / "rounds" / "round-04"
        specs = repo / "docs" / "specs" / mission_id
        specs.mkdir(parents=True)
        round_dir.mkdir(parents=True)

        (specs / "mission.json").write_text(
            json.dumps(
                {
                    "mission_id": mission_id,
                    "title": "Visual Diff Mission",
                    "status": "approved",
                    "spec_path": f"docs/specs/{mission_id}/spec.md",
                    "acceptance_criteria": [],
                    "constraints": [],
                    "interface_contracts": [],
                    "created_at": "2026-03-25T00:00:00+00:00",
                    "approved_at": "2026-03-25T00:05:00+00:00",
                    "completed_at": None,
                }
            ),
            encoding="utf-8",
        )
        (specs / "spec.md").write_text("# Visual Diff Mission\n", encoding="utf-8")
        (round_dir / "visual_evaluation.json").write_text(
            json.dumps(
                {
                    "evaluator": "playwright",
                    "summary": "Diff highlights a nav spacing regression.",
                    "confidence": 0.89,
                    "findings": [
                        {"severity": "blocking", "message": "Left rail width changed."},
                    ],
                    "artifacts": {
                        "before": f"docs/specs/{mission_id}/rounds/round-04/visual/before.png",
                        "after": f"docs/specs/{mission_id}/rounds/round-04/visual/after.png",
                        "diff": f"docs/specs/{mission_id}/rounds/round-04/visual/diff.png",
                    },
                }
            ),
            encoding="utf-8",
        )

        response = client.get(f"/api/missions/{mission_id}/visual-qa")
        assert response.status_code == 200
        data = response.json()
        assert data["summary"]["diff_items"] == 1
        assert data["summary"]["comparison_rounds"] == 1
        assert data["summary"]["focus_transcript_route"] is None
        assert data["review_route"] == f"/?mission={mission_id}&mode=missions&tab=visual"
        assert data["rounds"][0]["comparison"] == {
            "mode": "diff-first",
            "primary": {
                "label": "diff",
                "path": f"docs/specs/{mission_id}/rounds/round-04/visual/diff.png",
                "kind": "diff",
            },
            "related": [
                {
                    "label": "before",
                    "path": f"docs/specs/{mission_id}/rounds/round-04/visual/before.png",
                    "kind": "image",
                },
                {
                    "label": "after",
                    "path": f"docs/specs/{mission_id}/rounds/round-04/visual/after.png",
                    "kind": "image",
                },
            ],
        }
        assert data["rounds"][0]["review_route"] == (
            f"/?mission={mission_id}&mode=missions&tab=visual&round=4"
        )
        assert data["rounds"][0]["transcript_routes"] == []

    def test_visual_qa_endpoint_links_back_to_packet_transcripts(self, client, repo: Path):
        mission_id = "mission-visual-transcript-link"
        round_dir = repo / "docs" / "specs" / mission_id / "rounds" / "round-05"
        specs = repo / "docs" / "specs" / mission_id
        specs.mkdir(parents=True)
        round_dir.mkdir(parents=True)

        (specs / "mission.json").write_text(
            json.dumps(
                {
                    "mission_id": mission_id,
                    "title": "Visual Transcript Link Mission",
                    "status": "approved",
                    "spec_path": f"docs/specs/{mission_id}/spec.md",
                    "acceptance_criteria": [],
                    "constraints": [],
                    "interface_contracts": [],
                    "created_at": "2026-03-25T00:00:00+00:00",
                    "approved_at": "2026-03-25T00:05:00+00:00",
                    "completed_at": None,
                }
            ),
            encoding="utf-8",
        )
        (specs / "spec.md").write_text("# Visual Transcript Link Mission\n", encoding="utf-8")
        (round_dir / "round_summary.json").write_text(
            json.dumps(
                {
                    "round_id": 5,
                    "wave_id": 2,
                    "status": "decided",
                    "started_at": "2026-03-25T00:10:00+00:00",
                    "completed_at": "2026-03-25T00:12:00+00:00",
                    "worker_results": [
                        {"packet_id": "pkt-a", "title": "A", "succeeded": True},
                        {"packet_id": "pkt-b", "title": "B", "succeeded": True},
                    ],
                    "decision": None,
                }
            ),
            encoding="utf-8",
        )
        (round_dir / "visual_evaluation.json").write_text(
            json.dumps(
                {
                    "evaluator": "playwright",
                    "summary": "Detected spacing regressions.",
                    "confidence": 0.73,
                    "findings": [{"severity": "blocking", "message": "Spacing regressed."}],
                    "artifacts": {
                        "diff": f"docs/specs/{mission_id}/rounds/round-05/visual/diff.png",
                    },
                }
            ),
            encoding="utf-8",
        )

        response = client.get(f"/api/missions/{mission_id}/visual-qa")
        assert response.status_code == 200
        data = response.json()
        assert data["summary"]["focus_transcript_route"] == (
            f"/?mission={mission_id}&mode=missions&tab=transcript&packet=pkt-a"
        )
        assert data["rounds"][0]["transcript_routes"] == [
            f"/?mission={mission_id}&mode=missions&tab=transcript&packet=pkt-a",
            f"/?mission={mission_id}&mode=missions&tab=transcript&packet=pkt-b",
        ]

    def test_costs_endpoint_aggregates_worker_reports(self, client, repo: Path):
        mission_id = "mission-costs"
        worker_one = repo / "docs" / "specs" / mission_id / "workers" / "pkt-1"
        worker_two = repo / "docs" / "specs" / mission_id / "workers" / "pkt-2"
        worker_one.mkdir(parents=True)
        worker_two.mkdir(parents=True)

        (worker_one / "builder_report.json").write_text(
            json.dumps(
                {
                    "adapter": "codex_exec",
                    "metadata": {
                        "turn_status": "success",
                        "usage": {"input_tokens": 1000, "output_tokens": 400},
                    },
                }
            ),
            encoding="utf-8",
        )
        (worker_two / "builder_report.json").write_text(
            json.dumps(
                {
                    "adapter": "claude_code",
                    "metadata": {
                        "turn_status": "success",
                        "usage": {"input_tokens": 600, "output_tokens": 300},
                        "cost_usd": 0.12,
                    },
                }
            ),
            encoding="utf-8",
        )
        (repo / "spec-orch.toml").write_text(
            "[dashboard.costs]\nwarning_usd = 0.1\ncritical_usd = 0.11\n",
            encoding="utf-8",
        )

        response = client.get(f"/api/missions/{mission_id}/costs")
        assert response.status_code == 200
        data = response.json()
        assert data == {
            "mission_id": mission_id,
            "summary": {
                "workers": 2,
                "input_tokens": 1600,
                "output_tokens": 700,
                "cost_usd": 0.12,
                "budget_status": "critical",
                "thresholds": {"warning_usd": 0.1, "critical_usd": 0.11},
                "incident_count": 1,
                "remaining_budget_usd": -0.01,
            },
            "review_route": f"/?mission={mission_id}&mode=missions&tab=costs",
            "focus_packet_id": "pkt-2",
            "highest_cost_worker": {
                "packet_id": "pkt-2",
                "cost_usd": 0.12,
                "report_path": f"docs/specs/{mission_id}/workers/pkt-2/builder_report.json",
                "transcript_route": f"/?mission={mission_id}&mode=missions&tab=transcript&packet=pkt-2",
            },
            "incidents": [
                {
                    "severity": "critical",
                    "message": "Mission cost exceeded critical budget threshold.",
                    "status_copy": "Critical budget threshold exceeded",
                    "recommended_action": "Pause new work, review packet cost hotspots, and decide whether to cut scope or raise the budget.",
                    "operator_guidance": "Open the mission, inspect the most expensive packets, and either reduce scope or explicitly continue at higher spend.",
                    "suggested_action": {
                        "label": "Open mission costs",
                        "route": f"/?mission={mission_id}&mode=missions&tab=costs",
                    },
                    "transcript_route": f"/?mission={mission_id}&mode=missions&tab=transcript&packet=pkt-2",
                    "actual_cost_usd": 0.12,
                    "threshold_usd": 0.11,
                }
            ],
            "workers": [
                {
                    "packet_id": "pkt-1",
                    "report_path": f"docs/specs/{mission_id}/workers/pkt-1/builder_report.json",
                    "adapter": "codex_exec",
                    "turn_status": "success",
                    "input_tokens": 1000,
                    "output_tokens": 400,
                    "cost_usd": 0.0,
                    "transcript_route": f"/?mission={mission_id}&mode=missions&tab=transcript&packet=pkt-1",
                },
                {
                    "packet_id": "pkt-2",
                    "report_path": f"docs/specs/{mission_id}/workers/pkt-2/builder_report.json",
                    "adapter": "claude_code",
                    "turn_status": "success",
                    "input_tokens": 600,
                    "output_tokens": 300,
                    "cost_usd": 0.12,
                    "transcript_route": f"/?mission={mission_id}&mode=missions&tab=transcript&packet=pkt-2",
                },
            ],
        }

    def test_inbox_endpoint_surfaces_budget_alerts(self, client, repo: Path):
        mission_id = "mission-budget-alert"
        specs = repo / "docs" / "specs" / mission_id
        worker = specs / "workers" / "pkt-1"
        specs.mkdir(parents=True)
        worker.mkdir(parents=True)
        (specs / "mission.json").write_text(
            json.dumps(
                {
                    "mission_id": mission_id,
                    "title": "Budget Alert Mission",
                    "status": "approved",
                    "spec_path": f"docs/specs/{mission_id}/spec.md",
                    "acceptance_criteria": [],
                    "constraints": [],
                    "interface_contracts": [],
                    "created_at": "2026-03-25T00:00:00+00:00",
                    "approved_at": "2026-03-25T00:05:00+00:00",
                    "completed_at": None,
                }
            ),
            encoding="utf-8",
        )
        (specs / "spec.md").write_text("# Budget Alert Mission\n", encoding="utf-8")
        (worker / "builder_report.json").write_text(
            json.dumps(
                {
                    "adapter": "claude_code",
                    "metadata": {
                        "turn_status": "success",
                        "usage": {"input_tokens": 100, "output_tokens": 50},
                        "cost_usd": 1.5,
                    },
                }
            ),
            encoding="utf-8",
        )
        (repo / "spec-orch.toml").write_text(
            "[dashboard.costs]\nwarning_usd = 1.0\ncritical_usd = 1.2\n",
            encoding="utf-8",
        )

        response = client.get("/api/inbox")
        assert response.status_code == 200
        data = response.json()
        assert data["counts"] == {
            "paused": 0,
            "failed": 0,
            "approvals": 0,
            "budgets": 1,
            "attention": 1,
        }
        assert data["items"] == [
            {
                "mission_id": mission_id,
                "title": "Budget Alert Mission",
                "kind": "budget",
                "phase": "approved",
                "summary": "Mission cost exceeded critical budget threshold.",
                "updated_at": None,
                "current_round": 0,
                "budget_status": "critical",
                "cost_usd": 1.5,
                "operator_guidance": "Open the mission, inspect the most expensive packets, and either reduce scope or explicitly continue at higher spend.",
                "review_route": f"/?mission={mission_id}&mode=missions&tab=costs",
            }
        ]

    def test_costs_endpoint_ignores_invalid_budget_threshold_values(
        self,
        client,
        repo: Path,
    ):
        mission_id = "mission-costs-invalid-threshold"
        worker = repo / "docs" / "specs" / mission_id / "workers" / "pkt-1"
        worker.mkdir(parents=True)
        (repo / "spec-orch.toml").write_text(
            '[dashboard.costs]\nwarning_usd = "oops"\ncritical_usd = "bad"\n',
            encoding="utf-8",
        )
        (worker / "builder_report.json").write_text(
            json.dumps(
                {
                    "adapter": "claude_code",
                    "metadata": {
                        "turn_status": "success",
                        "usage": {"input_tokens": 100, "output_tokens": 50},
                        "cost_usd": 1.5,
                    },
                }
            ),
            encoding="utf-8",
        )

        response = client.get(f"/api/missions/{mission_id}/costs")
        assert response.status_code == 200
        data = response.json()
        assert data["summary"]["thresholds"] is None
        assert data["summary"]["incident_count"] == 0
        assert data["summary"]["remaining_budget_usd"] is None
        assert data["incidents"] == []

    def test_costs_endpoint_skips_non_object_builder_reports(self, client, repo: Path):
        mission_id = "mission-costs-non-object"
        worker_one = repo / "docs" / "specs" / mission_id / "workers" / "pkt-1"
        worker_two = repo / "docs" / "specs" / mission_id / "workers" / "pkt-2"
        worker_one.mkdir(parents=True)
        worker_two.mkdir(parents=True)

        (worker_one / "builder_report.json").write_text('["unexpected"]', encoding="utf-8")
        (worker_two / "builder_report.json").write_text(
            json.dumps(
                {
                    "adapter": "codex_exec",
                    "metadata": {
                        "turn_status": "success",
                        "usage": {"input_tokens": 50, "output_tokens": 10},
                        "cost_usd": 0.02,
                    },
                }
            ),
            encoding="utf-8",
        )

        response = client.get(f"/api/missions/{mission_id}/costs")

        assert response.status_code == 200
        payload = response.json()
        assert payload["summary"]["workers"] == 1
        assert payload["summary"]["input_tokens"] == 50
        assert payload["summary"]["output_tokens"] == 10
        assert payload["summary"]["cost_usd"] == 0.02
        assert [worker["packet_id"] for worker in payload["workers"]] == ["pkt-2"]

    def test_packet_transcript_endpoint_groups_tool_events_into_bursts(self, client, repo: Path):
        mission_id = "mission-transcript-burst"
        packet_id = "pkt-2"
        telemetry = repo / "docs" / "specs" / mission_id / "workers" / packet_id / "telemetry"
        telemetry.mkdir(parents=True)

        (telemetry / "events.jsonl").write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "timestamp": "2026-03-25T00:11:45Z",
                            "event_type": "tool_call_started",
                            "message": "running ruff",
                        }
                    ),
                    json.dumps(
                        {
                            "timestamp": "2026-03-25T00:11:46Z",
                            "event_type": "tool_call_completed",
                            "message": "ruff clean",
                        }
                    ),
                    json.dumps(
                        {
                            "timestamp": "2026-03-25T00:11:47Z",
                            "event_type": "tool_call_completed",
                            "message": "pytest passed",
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        r = client.get(f"/api/missions/{mission_id}/packets/{packet_id}/transcript")
        assert r.status_code == 200
        data = r.json()
        assert data["summary"]["block_counts"] == {"command_burst": 1}
        assert data["blocks"] == [
            {
                "block_type": "command_burst",
                "emphasis": "burst",
                "timestamp": "2026-03-25T00:11:45Z",
                "title": "3 tool events",
                "body": "running ruff • ruff clean • pytest passed",
                "source_path": f"docs/specs/{mission_id}/workers/{packet_id}/telemetry/events.jsonl",
                "details": {
                    "item_count": 3,
                    "event_types": [
                        "tool_call_started",
                        "tool_call_completed",
                        "tool_call_completed",
                    ],
                },
                "jump_targets": [
                    {
                        "kind": "source",
                        "label": "Events stream",
                        "path": f"docs/specs/{mission_id}/workers/{packet_id}/telemetry/events.jsonl",
                        "href": f"/artifacts/docs/specs/{mission_id}/workers/{packet_id}/telemetry/events.jsonl",
                    }
                ],
                "items": [
                    {
                        "block_type": "tool",
                        "emphasis": "tool",
                        "timestamp": "2026-03-25T00:11:45Z",
                        "title": "running ruff",
                        "body": "tool_call_started",
                        "source_path": f"docs/specs/{mission_id}/workers/{packet_id}/telemetry/events.jsonl",
                        "details": {
                            "timestamp": "2026-03-25T00:11:45Z",
                            "event_type": "tool_call_started",
                            "message": "running ruff",
                        },
                        "jump_targets": [
                            {
                                "kind": "source",
                                "label": "Events stream",
                                "path": f"docs/specs/{mission_id}/workers/{packet_id}/telemetry/events.jsonl",
                                "href": f"/artifacts/docs/specs/{mission_id}/workers/{packet_id}/telemetry/events.jsonl",
                            }
                        ],
                    },
                    {
                        "block_type": "tool",
                        "emphasis": "tool",
                        "timestamp": "2026-03-25T00:11:46Z",
                        "title": "ruff clean",
                        "body": "tool_call_completed",
                        "source_path": f"docs/specs/{mission_id}/workers/{packet_id}/telemetry/events.jsonl",
                        "details": {
                            "timestamp": "2026-03-25T00:11:46Z",
                            "event_type": "tool_call_completed",
                            "message": "ruff clean",
                        },
                        "jump_targets": [
                            {
                                "kind": "source",
                                "label": "Events stream",
                                "path": f"docs/specs/{mission_id}/workers/{packet_id}/telemetry/events.jsonl",
                                "href": f"/artifacts/docs/specs/{mission_id}/workers/{packet_id}/telemetry/events.jsonl",
                            }
                        ],
                    },
                    {
                        "block_type": "tool",
                        "emphasis": "tool",
                        "timestamp": "2026-03-25T00:11:47Z",
                        "title": "pytest passed",
                        "body": "tool_call_completed",
                        "source_path": f"docs/specs/{mission_id}/workers/{packet_id}/telemetry/events.jsonl",
                        "details": {
                            "timestamp": "2026-03-25T00:11:47Z",
                            "event_type": "tool_call_completed",
                            "message": "pytest passed",
                        },
                        "jump_targets": [
                            {
                                "kind": "source",
                                "label": "Events stream",
                                "path": f"docs/specs/{mission_id}/workers/{packet_id}/telemetry/events.jsonl",
                                "href": f"/artifacts/docs/specs/{mission_id}/workers/{packet_id}/telemetry/events.jsonl",
                            }
                        ],
                    },
                ],
            }
        ]

    def test_packet_transcript_endpoint_exposes_evidence_details(self, client, repo: Path):
        mission_id = "mission-transcript-evidence-details"
        packet_id = "pkt-9"
        telemetry = repo / "docs" / "specs" / mission_id / "workers" / packet_id / "telemetry"
        round_dir = repo / "docs" / "specs" / mission_id / "rounds" / "round-03"
        telemetry.mkdir(parents=True)
        round_dir.mkdir(parents=True)

        (telemetry / "incoming_events.jsonl").write_text(
            json.dumps(
                {
                    "ts": "2026-03-25T00:11:40Z",
                    "kind": "assistant_message",
                    "excerpt": "Implementing transcript payload details.",
                    "message": "Implementing transcript payload details.",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (round_dir / "round_summary.json").write_text(
            json.dumps(
                {
                    "round_id": 3,
                    "wave_id": 1,
                    "status": "decided",
                    "started_at": "2026-03-25T00:12:10Z",
                    "completed_at": "2026-03-25T00:12:30Z",
                    "worker_results": [
                        {
                            "packet_id": packet_id,
                            "title": "Build transcript payload depth",
                            "report_path": f"docs/specs/{mission_id}/workers/{packet_id}/builder_report.json",
                            "succeeded": True,
                        }
                    ],
                    "decision": {
                        "action": "ask_human",
                        "reason_code": "needs_review",
                        "summary": "Need approval before shipping transcript changes.",
                        "confidence": 0.74,
                        "affected_workers": [packet_id],
                        "artifacts": {},
                        "session_ops": {"reuse": [], "spawn": [], "cancel": []},
                        "blocking_questions": ["Approve transcript changes?"],
                    },
                }
            ),
            encoding="utf-8",
        )
        (round_dir / "visual_evaluation.json").write_text(
            json.dumps(
                {
                    "evaluator": "playwright",
                    "summary": "Visual QA found a spacing regression.",
                    "confidence": 0.81,
                    "findings": [{"severity": "blocking", "message": "Header overlaps metrics."}],
                    "artifacts": {
                        "dashboard": f"docs/specs/{mission_id}/rounds/round-03/visual/dashboard.png"
                    },
                }
            ),
            encoding="utf-8",
        )

        response = client.get(f"/api/missions/{mission_id}/packets/{packet_id}/transcript")
        assert response.status_code == 200
        data = response.json()
        assert data["blocks"][0]["details"] == {
            "ts": "2026-03-25T00:11:40Z",
            "kind": "assistant_message",
            "excerpt": "Implementing transcript payload details.",
            "message": "Implementing transcript payload details.",
        }
        assert data["blocks"][0]["emphasis"] == "narrative"
        assert data["blocks"][-2]["details"] == {
            "reason_code": "needs_review",
            "confidence": 0.74,
            "blocking_questions": ["Approve transcript changes?"],
        }
        assert data["blocks"][-2]["emphasis"] == "decision"
        assert data["blocks"][-1]["details"] == {
            "confidence": 0.81,
            "findings": [{"severity": "blocking", "message": "Header overlaps metrics."}],
            "artifacts": {
                "dashboard": f"docs/specs/{mission_id}/rounds/round-03/visual/dashboard.png"
            },
        }
        assert data["blocks"][-1]["emphasis"] == "alert"

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
        assert r.status_code == 404
        data = r.json()
        assert data == {"error": "Mission not found"}

    def test_approve_existing_mission_starts_tracking_and_auto_advances(
        self,
        client,
        repo: Path,
        monkeypatch,
    ):
        mission_id = "mission-approve-existing"
        specs = repo / "docs" / "specs" / mission_id
        specs.mkdir(parents=True)
        (specs / "mission.json").write_text(
            json.dumps(
                {
                    "mission_id": mission_id,
                    "title": "Approve Existing Mission",
                    "status": "approved",
                    "spec_path": f"docs/specs/{mission_id}/spec.md",
                    "acceptance_criteria": [],
                    "constraints": [],
                    "interface_contracts": [],
                    "created_at": "2026-03-25T00:00:00+00:00",
                    "approved_at": "2026-03-25T00:05:00+00:00",
                    "completed_at": None,
                }
            ),
            encoding="utf-8",
        )
        (specs / "spec.md").write_text("# Approve Existing Mission\n", encoding="utf-8")

        calls: list[tuple[str, str]] = []

        class FakeState:
            def to_dict(self) -> dict[str, str]:
                return {"mission_id": mission_id, "phase": "planning"}

        class FakeLifecycleManager:
            def begin_tracking(self, tracked_mission_id: str) -> None:
                calls.append(("begin_tracking", tracked_mission_id))

            def auto_advance(self, tracked_mission_id: str) -> FakeState:
                calls.append(("auto_advance", tracked_mission_id))
                return FakeState()

        monkeypatch.setattr(
            "spec_orch.dashboard.routes.dashboard_app._get_lifecycle_manager",
            lambda _root: FakeLifecycleManager(),
        )

        response = client.post(f"/api/missions/{mission_id}/approve")

        assert response.status_code == 200
        assert response.json() == {
            "ok": True,
            "state": {"mission_id": mission_id, "phase": "planning"},
        }
        assert calls == [
            ("begin_tracking", mission_id),
            ("auto_advance", mission_id),
        ]

    def test_retry_existing_mission_auto_advances(
        self,
        client,
        monkeypatch,
    ):
        mission_id = "mission-retry-existing"
        calls: list[tuple[str, str]] = []

        class FakeState:
            def __init__(self, phase: str) -> None:
                self.phase = phase

            def to_dict(self) -> dict[str, str]:
                return {"mission_id": mission_id, "phase": self.phase}

        class FakeLifecycleManager:
            def retry(self, tracked_mission_id: str) -> FakeState:
                calls.append(("retry", tracked_mission_id))
                return FakeState("approved")

            def auto_advance(self, tracked_mission_id: str) -> FakeState:
                calls.append(("auto_advance", tracked_mission_id))
                return FakeState("planning")

        monkeypatch.setattr(
            "spec_orch.dashboard.routes.dashboard_app._get_lifecycle_manager",
            lambda _root: FakeLifecycleManager(),
        )

        response = client.post(f"/api/missions/{mission_id}/retry")

        assert response.status_code == 200
        assert response.json() == {
            "ok": True,
            "state": {"mission_id": mission_id, "phase": "planning"},
        }
        assert calls == [
            ("retry", mission_id),
            ("auto_advance", mission_id),
        ]

    def test_retry_existing_mission_falls_back_to_get_state_after_auto_advance(
        self,
        client,
        monkeypatch,
    ):
        mission_id = "mission-retry-fallback"
        calls: list[tuple[str, str]] = []

        class FakeState:
            def __init__(self, phase: str) -> None:
                self.phase = phase

            def to_dict(self) -> dict[str, str]:
                return {"mission_id": mission_id, "phase": self.phase}

        class FakeLifecycleManager:
            def retry(self, tracked_mission_id: str) -> FakeState:
                calls.append(("retry", tracked_mission_id))
                return FakeState("approved")

            def auto_advance(self, tracked_mission_id: str) -> None:
                calls.append(("auto_advance", tracked_mission_id))
                return None

            def get_state(self, tracked_mission_id: str) -> FakeState:
                calls.append(("get_state", tracked_mission_id))
                return FakeState("planning")

        monkeypatch.setattr(
            "spec_orch.dashboard.routes.dashboard_app._get_lifecycle_manager",
            lambda _root: FakeLifecycleManager(),
        )

        response = client.post(f"/api/missions/{mission_id}/retry")

        assert response.status_code == 200
        assert response.json() == {
            "ok": True,
            "state": {"mission_id": mission_id, "phase": "planning"},
        }
        assert calls == [
            ("retry", mission_id),
            ("auto_advance", mission_id),
            ("get_state", mission_id),
        ]

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

    def test_approval_action_endpoint_injects_guidance(self, client, repo: Path, monkeypatch):
        mission_id = "mission-approval-action"
        issue_id = "SON-9001"
        specs = repo / "docs" / "specs" / mission_id
        round_dir = specs / "rounds" / "round-01"
        specs.mkdir(parents=True)
        round_dir.mkdir(parents=True)

        (specs / "mission.json").write_text(
            json.dumps(
                {
                    "mission_id": mission_id,
                    "title": "Approval Action Mission",
                    "status": "approved",
                    "spec_path": f"docs/specs/{mission_id}/spec.md",
                    "acceptance_criteria": [],
                    "constraints": [],
                    "interface_contracts": [],
                    "created_at": "2026-03-25T00:00:00+00:00",
                    "approved_at": "2026-03-25T00:05:00+00:00",
                    "completed_at": None,
                }
            ),
            encoding="utf-8",
        )
        (specs / "spec.md").write_text("# Approval Action Mission\n", encoding="utf-8")
        (round_dir / "round_summary.json").write_text(
            json.dumps(
                {
                    "round_id": 1,
                    "wave_id": 0,
                    "status": "decided",
                    "started_at": "2026-03-25T00:10:00+00:00",
                    "completed_at": "2026-03-25T00:11:00+00:00",
                    "worker_results": [],
                    "decision": {
                        "action": "ask_human",
                        "reason_code": "needs_approval",
                        "summary": "Approve rollout after QA.",
                        "confidence": 0.8,
                        "affected_workers": [],
                        "artifacts": {},
                        "session_ops": {"reuse": [], "spawn": [], "cancel": []},
                        "blocking_questions": ["Approve rollout after QA?"],
                    },
                }
            ),
            encoding="utf-8",
        )
        (repo / ".spec_orch_runs" / "lifecycle_state.json").write_text(
            json.dumps(
                {
                    mission_id: {
                        "mission_id": mission_id,
                        "phase": "executing",
                        "issue_ids": [issue_id],
                        "completed_issues": [],
                        "error": None,
                        "updated_at": "2026-03-25T00:11:30+00:00",
                        "current_round": 1,
                        "round_orchestrator_state": {
                            "paused": True,
                            "blocking_questions": ["Approve rollout after QA?"],
                        },
                    }
                }
            ),
            encoding="utf-8",
        )

        calls: list[tuple[str, str, str]] = []

        class FakeLifecycleManager:
            def get_state(self, tracked_mission_id: str):
                assert tracked_mission_id == mission_id
                return type(
                    "State",
                    (),
                    {"issue_ids": [issue_id], "completed_issues": []},
                )()

            def inject_btw(self, issue_id: str, message: str, channel: str) -> bool:
                calls.append((issue_id, message, channel))
                return True

        monkeypatch.setattr(
            "spec_orch.dashboard.routes.dashboard_app._get_lifecycle_manager",
            lambda _root: FakeLifecycleManager(),
        )

        response = client.post(
            f"/api/missions/{mission_id}/approval-action",
            content='{"action_key": "approve"}',
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload == {
            "ok": True,
            "message": "@approve Approve rollout after QA?",
            "action_key": "approve",
            "action": {
                "timestamp": payload["action"]["timestamp"],
                "action_key": "approve",
                "label": "Approve",
                "message": "@approve Approve rollout after QA?",
                "channel": "web-dashboard",
                "status": "applied",
                "effect": "approval_granted",
            },
        }
        assert calls == [(issue_id, "@approve Approve rollout after QA?", "web-dashboard")]
        history_path = repo / "docs" / "specs" / mission_id / "operator" / "approval_actions.jsonl"
        history = [
            json.loads(line)
            for line in history_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(history) == 1
        assert history[0]["action_key"] == "approve"
        assert history[0]["message"] == "@approve Approve rollout after QA?"
        assert history[0]["channel"] == "web-dashboard"
        assert history[0]["status"] == "applied"
        assert history[0]["effect"] == "approval_granted"

    def test_approval_action_endpoint_records_not_applied_status_when_injection_returns_false(
        self,
        client,
        repo: Path,
        monkeypatch,
    ):
        mission_id = "mission-approval-soft-fail"
        issue_id = "SON-9002"
        specs = repo / "docs" / "specs" / mission_id
        round_dir = specs / "rounds" / "round-01"
        specs.mkdir(parents=True)
        round_dir.mkdir(parents=True)

        (specs / "mission.json").write_text(
            json.dumps(
                {
                    "mission_id": mission_id,
                    "title": "Approval Soft Fail",
                    "status": "approved",
                    "spec_path": f"docs/specs/{mission_id}/spec.md",
                    "acceptance_criteria": [],
                    "constraints": [],
                    "interface_contracts": [],
                    "created_at": "2026-03-25T00:00:00+00:00",
                    "approved_at": "2026-03-25T00:05:00+00:00",
                    "completed_at": None,
                }
            ),
            encoding="utf-8",
        )
        (specs / "spec.md").write_text("# Approval Soft Fail\n", encoding="utf-8")
        (round_dir / "round_summary.json").write_text(
            json.dumps(
                {
                    "round_id": 1,
                    "wave_id": 0,
                    "status": "decided",
                    "started_at": "2026-03-25T00:10:00+00:00",
                    "completed_at": "2026-03-25T00:11:00+00:00",
                    "worker_results": [],
                    "decision": {
                        "action": "ask_human",
                        "reason_code": "needs_approval",
                        "summary": "Approve rollout after QA.",
                        "confidence": 0.8,
                        "affected_workers": [],
                        "artifacts": {},
                        "session_ops": {"reuse": [], "spawn": [], "cancel": []},
                        "blocking_questions": ["Approve rollout after QA?"],
                    },
                }
            ),
            encoding="utf-8",
        )
        (repo / ".spec_orch_runs" / "lifecycle_state.json").write_text(
            json.dumps(
                {
                    mission_id: {
                        "mission_id": mission_id,
                        "phase": "executing",
                        "issue_ids": [issue_id],
                        "completed_issues": [],
                        "error": None,
                        "updated_at": "2026-03-25T00:11:30+00:00",
                        "current_round": 1,
                        "round_orchestrator_state": {
                            "paused": True,
                            "blocking_questions": ["Approve rollout after QA?"],
                        },
                    }
                }
            ),
            encoding="utf-8",
        )

        class FakeLifecycleManager:
            def get_state(self, tracked_mission_id: str):
                assert tracked_mission_id == mission_id
                return type(
                    "State",
                    (),
                    {"issue_ids": [issue_id], "completed_issues": []},
                )()

            def inject_btw(self, injected_issue_id: str, message: str, channel: str) -> bool:
                assert injected_issue_id == issue_id
                assert message == "@approve Approve rollout after QA?"
                assert channel == "web-dashboard"
                return False

        monkeypatch.setattr(
            "spec_orch.dashboard.routes.dashboard_app._get_lifecycle_manager",
            lambda _root: FakeLifecycleManager(),
        )

        response = client.post(
            f"/api/missions/{mission_id}/approval-action",
            content='{"action_key": "approve"}',
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is False
        assert payload["action"]["status"] == "not_applied"
        assert payload["action"]["effect"] == "approval_granted"

    def test_approval_action_endpoint_records_failed_status_when_injection_raises(
        self,
        client,
        repo: Path,
        monkeypatch,
    ):
        mission_id = "mission-approval-hard-fail"
        issue_id = "SON-9003"
        specs = repo / "docs" / "specs" / mission_id
        round_dir = specs / "rounds" / "round-01"
        specs.mkdir(parents=True)
        round_dir.mkdir(parents=True)

        (specs / "mission.json").write_text(
            json.dumps(
                {
                    "mission_id": mission_id,
                    "title": "Approval Hard Fail",
                    "status": "approved",
                    "spec_path": f"docs/specs/{mission_id}/spec.md",
                    "acceptance_criteria": [],
                    "constraints": [],
                    "interface_contracts": [],
                    "created_at": "2026-03-25T00:00:00+00:00",
                    "approved_at": "2026-03-25T00:05:00+00:00",
                    "completed_at": None,
                }
            ),
            encoding="utf-8",
        )
        (specs / "spec.md").write_text("# Approval Hard Fail\n", encoding="utf-8")
        (round_dir / "round_summary.json").write_text(
            json.dumps(
                {
                    "round_id": 1,
                    "wave_id": 0,
                    "status": "decided",
                    "started_at": "2026-03-25T00:10:00+00:00",
                    "completed_at": "2026-03-25T00:11:00+00:00",
                    "worker_results": [],
                    "decision": {
                        "action": "ask_human",
                        "reason_code": "needs_approval",
                        "summary": "Approve rollout after QA.",
                        "confidence": 0.8,
                        "affected_workers": [],
                        "artifacts": {},
                        "session_ops": {"reuse": [], "spawn": [], "cancel": []},
                        "blocking_questions": ["Approve rollout after QA?"],
                    },
                }
            ),
            encoding="utf-8",
        )
        (repo / ".spec_orch_runs" / "lifecycle_state.json").write_text(
            json.dumps(
                {
                    mission_id: {
                        "mission_id": mission_id,
                        "phase": "executing",
                        "issue_ids": [issue_id],
                        "completed_issues": [],
                        "error": None,
                        "updated_at": "2026-03-25T00:11:30+00:00",
                        "current_round": 1,
                        "round_orchestrator_state": {
                            "paused": True,
                            "blocking_questions": ["Approve rollout after QA?"],
                        },
                    }
                }
            ),
            encoding="utf-8",
        )

        class FakeLifecycleManager:
            def get_state(self, tracked_mission_id: str):
                assert tracked_mission_id == mission_id
                return type(
                    "State",
                    (),
                    {"issue_ids": [issue_id], "completed_issues": []},
                )()

            def inject_btw(self, issue_id: str, message: str, channel: str) -> bool:
                raise RuntimeError("injection exploded")

        monkeypatch.setattr(
            "spec_orch.dashboard.routes.dashboard_app._get_lifecycle_manager",
            lambda _root: FakeLifecycleManager(),
        )

        response = client.post(
            f"/api/missions/{mission_id}/approval-action",
            content='{"action_key": "approve"}',
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 500
        payload = response.json()
        assert payload["error"] == "Approval action failed"
        assert payload["action"]["status"] == "failed"
        history_path = repo / "docs" / "specs" / mission_id / "operator" / "approval_actions.jsonl"
        history = [
            json.loads(line)
            for line in history_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert history[0]["status"] == "failed"

    def test_visual_qa_endpoint_ignores_non_numeric_round_directories(self, client, repo: Path):
        mission_id = "mission-visual-invalid-round"
        specs = repo / "docs" / "specs" / mission_id
        valid_round_dir = specs / "rounds" / "round-01"
        invalid_round_dir = specs / "rounds" / "round-latest"
        valid_round_dir.mkdir(parents=True)
        invalid_round_dir.mkdir(parents=True)
        (valid_round_dir / "visual_evaluation.json").write_text(
            json.dumps(
                {
                    "summary": "Looks good",
                    "confidence": 0.9,
                    "findings": [],
                    "artifacts": {},
                }
            ),
            encoding="utf-8",
        )
        (invalid_round_dir / "visual_evaluation.json").write_text(
            json.dumps(
                {
                    "summary": "Should be ignored",
                    "confidence": 0.1,
                    "findings": [{"severity": "blocking", "message": "bad dir"}],
                    "artifacts": {},
                }
            ),
            encoding="utf-8",
        )

        response = client.get(f"/api/missions/{mission_id}/visual-qa")
        assert response.status_code == 200
        payload = response.json()
        assert payload["summary"]["total_rounds"] == 1
        assert payload["rounds"][0]["round_id"] == 1

    def test_visual_qa_endpoint_tolerates_unexpected_json_shapes(self, client, repo: Path):
        mission_id = "mission-visual-weird-shapes"
        round_dir = repo / "docs" / "specs" / mission_id / "rounds" / "round-02"
        round_dir.mkdir(parents=True)
        (round_dir / "round_summary.json").write_text('["unexpected"]', encoding="utf-8")
        (round_dir / "visual_evaluation.json").write_text(
            json.dumps(
                {
                    "summary": "Malformed visual payload",
                    "confidence": 0.3,
                    "findings": ["not-a-dict"],
                    "artifacts": ["not-a-mapping"],
                }
            ),
            encoding="utf-8",
        )

        response = client.get(f"/api/missions/{mission_id}/visual-qa")

        assert response.status_code == 200
        payload = response.json()
        assert payload["mission_id"] == mission_id
        assert payload["summary"]["total_rounds"] == 1
        assert payload["rounds"][0]["findings"] == []
        assert payload["rounds"][0]["artifacts"] == {}
        assert payload["rounds"][0]["gallery"] == []

    def test_mission_detail_endpoint_includes_approval_history(self, client, repo: Path):
        mission_id = "mission-approval-history"
        specs = repo / "docs" / "specs" / mission_id
        round_dir = specs / "rounds" / "round-01"
        operator_dir = specs / "operator"
        specs.mkdir(parents=True)
        round_dir.mkdir(parents=True)
        operator_dir.mkdir(parents=True)

        (specs / "mission.json").write_text(
            json.dumps(
                {
                    "mission_id": mission_id,
                    "title": "Approval History Mission",
                    "status": "approved",
                    "spec_path": f"docs/specs/{mission_id}/spec.md",
                    "acceptance_criteria": [],
                    "constraints": [],
                    "interface_contracts": [],
                    "created_at": "2026-03-25T00:00:00+00:00",
                    "approved_at": "2026-03-25T00:05:00+00:00",
                    "completed_at": None,
                }
            ),
            encoding="utf-8",
        )
        (specs / "spec.md").write_text("# Approval History Mission\n", encoding="utf-8")
        (round_dir / "round_summary.json").write_text(
            json.dumps(
                {
                    "round_id": 1,
                    "wave_id": 0,
                    "status": "decided",
                    "started_at": "2026-03-25T00:10:00+00:00",
                    "completed_at": "2026-03-25T00:11:00+00:00",
                    "worker_results": [],
                    "decision": {
                        "action": "ask_human",
                        "reason_code": "needs_approval",
                        "summary": "Approve rollout after QA.",
                        "confidence": 0.8,
                        "affected_workers": [],
                        "artifacts": {},
                        "session_ops": {"reuse": [], "spawn": [], "cancel": []},
                        "blocking_questions": ["Approve rollout after QA?"],
                    },
                }
            ),
            encoding="utf-8",
        )
        (operator_dir / "approval_actions.jsonl").write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "timestamp": "2026-03-25T00:12:00+00:00",
                            "action_key": "ask_followup",
                            "label": "Ask follow-up",
                            "message": "@follow-up I need more detail before approving this round.",
                            "channel": "web-dashboard",
                            "status": "sent",
                            "effect": "followup_requested",
                        }
                    ),
                    json.dumps(
                        {
                            "timestamp": "2026-03-25T00:13:00+00:00",
                            "action_key": "approve",
                            "label": "Approve",
                            "message": "@approve Approve rollout after QA?",
                            "channel": "web-dashboard",
                            "status": "sent",
                            "effect": "approval_granted",
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        response = client.get(f"/api/missions/{mission_id}/detail")
        assert response.status_code == 200
        data = response.json()
        assert data["approval_history"] == [
            {
                "timestamp": "2026-03-25T00:13:00+00:00",
                "action_key": "approve",
                "label": "Approve",
                "message": "@approve Approve rollout after QA?",
                "channel": "web-dashboard",
                "status": "sent",
                "effect": "approval_granted",
            },
            {
                "timestamp": "2026-03-25T00:12:00+00:00",
                "action_key": "ask_followup",
                "label": "Ask follow-up",
                "message": "@follow-up I need more detail before approving this round.",
                "channel": "web-dashboard",
                "status": "sent",
                "effect": "followup_requested",
            },
        ]
        assert data["approval_state"] == {
            "status": "approval_granted",
            "summary": "Operator approved this round",
        }

    def test_homepage(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "spec-orch" in r.text.lower()
        assert "/static/operator-console.css" in r.text
        assert "/static/operator-console.js" in r.text
        assert 'id="operator-shell"' in r.text
        assert 'id="inbox-attention-chip"' in r.text
        assert 'id="mission-list"' in r.text
        assert 'id="inbox-list"' in r.text
        assert 'id="mission-detail-view"' in r.text
        assert 'id="operator-context-rail"' in r.text
        assert 'id="transcript-filter-bar"' in r.text
        assert 'id="transcript-inspector"' in r.text
        assert 'id="packet-transcript-view"' in r.text
        assert 'id="card-${escAttr(m.mission_id)}"' in r.text
        assert 'data-mid="${escAttr(m.mission_id)}"' in r.text
        assert "onclick='selectMission(${safeJsArg(m.mission_id)})'" in r.text

    def test_static_operator_console_assets(self, client):
        css = client.get("/static/operator-console.css")
        assert css.status_code == 200
        assert "text/css" in css.headers.get("content-type", "")

        js = client.get("/static/operator-console.js")
        assert js.status_code == 200
        assert "javascript" in js.headers.get("content-type", "")
        assert "window.SpecOrchOperatorConsole" in js.text
        assert "renderTranscriptDetails" in js.text
        assert "renderDetailValue" in js.text
        assert "renderArtifactLinks" in js.text
        assert "renderRoundContext" in js.text
        assert "buildMissionSubtitle" in js.text
        assert "renderApprovalWorkspace" in js.text
        assert "renderApprovalQueue" in js.text
        assert "renderTranscriptPreview" in js.text
        assert "renderTranscriptInspector" in js.text
        assert "renderActionButtons" in js.text
        assert "renderVisualQaPanel" in js.text
        assert "renderCostsPanel" in js.text
        assert "function escAttr" in js.text
        assert "function safeJsArg" in js.text
        assert "safeJsArg," in js.text
        assert "navigateOperatorRoute(${safeJsArg(route)})" in js.text
        assert "approveGo(${safeJsArg(missionId)})" in js.text
        assert "retryMission(${safeJsArg(missionId)})" in js.text
        assert "openDiscuss(${safeJsArg(missionId)})" in js.text
        assert "selectPacket(${safeJsArg(packet?.packet_id)})" in js.text
        assert 'href="/artifacts/${escAttr(value)}"' in js.text
        assert 'href="${escAttr(target.href)}"' in js.text
        assert (
            "triggerApprovalAction(${safeJsArg(missionId)}, ${safeJsArg(action?.key || '')})"
            in js.text
        )
        assert (
            "openDiscussPreset(${safeJsArg(missionId)}, ${safeJsArg((approvalRequest?.actions || [])[0]?.message || '')})"
            in js.text
        )
        assert "focusMissionFromBatch(${safeJsArg(batchState.focusMissionId)})" in js.text
        assert "focusMissionFromBatch(${safeJsArg(batchState.nextPendingMissionId)})" in js.text
        assert "${visualQa?.review_route || summary.focus_transcript_route ? `" in js.text
        assert "${incident?.suggested_action?.route || incident?.transcript_route ? `" in js.text

    def test_favicon_route_returns_no_content(self, client):
        response = client.get("/favicon.ico")
        assert response.status_code == 204
        assert response.content == b""

    def test_artifacts_route_restricts_access_to_artifact_roots(self, client, repo: Path):
        artifact_dir = repo / "docs" / "specs" / "mission-artifacts" / "rounds" / "round-01"
        artifact_dir.mkdir(parents=True)
        allowed_file = artifact_dir / "visual_evaluation.json"
        allowed_file.write_text("{}", encoding="utf-8")
        blocked_file = repo / "spec-orch.toml"
        blocked_file.write_text("[builder]\nadapter = 'codex_exec'\n", encoding="utf-8")

        allowed = client.get(
            "/artifacts/docs/specs/mission-artifacts/rounds/round-01/visual_evaluation.json"
        )
        blocked = client.get("/artifacts/spec-orch.toml")

        assert allowed.status_code == 200
        assert blocked.status_code == 404

    def test_websocket_route_registers_websocket_param(self, repo: Path):
        from spec_orch.dashboard import create_app

        app = create_app(repo)
        ws_route = next(
            route for route in app.router.routes if getattr(route, "path", None) == "/ws"
        )
        dependant = ws_route.dependant
        assert dependant.websocket_param_name == "websocket"
        assert dependant.query_params == []

    def test_websocket_streams_event_bus_updates(self, client):
        bus = get_event_bus()

        with client.websocket_connect("/ws") as websocket:
            bus.publish(
                Event(
                    topic=EventTopic.ISSUE_STATE,
                    payload={"issue_id": "SON-WS", "state": "building"},
                    source="test",
                )
            )
            payload = websocket.receive_json()

        assert payload["topic"] == "issue.state"
        assert payload["payload"] == {"issue_id": "SON-WS", "state": "building"}
        assert payload["source"] == "test"

    def test_websocket_disconnect_cleans_up_async_queue(self, client):
        bus = get_event_bus()
        before = len(bus._async_queues)

        with client.websocket_connect("/ws"):
            assert len(bus._async_queues) == before + 1

        assert len(bus._async_queues) == before

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
