"""Tests for Dashboard API endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest

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

    def test_lifecycle_endpoint(self, client):
        r = client.get("/api/lifecycle")
        assert r.status_code == 200
        assert isinstance(r.json(), dict)

    def test_evolution_endpoint(self, client):
        r = client.get("/api/evolution")
        assert r.status_code == 200
        data = r.json()
        assert "prompt_variants" in data

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

    def test_runs_endpoint(self, client):
        r = client.get("/api/runs")
        assert r.status_code == 200
        assert isinstance(r.json(), list)
