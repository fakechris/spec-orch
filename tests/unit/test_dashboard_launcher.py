from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "docs" / "specs").mkdir(parents=True)
    return tmp_path


def test_launcher_readiness_reports_missing_and_present_config(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from spec_orch.dashboard.launcher import _gather_launcher_readiness

    (repo / "spec-orch.toml").write_text(
        """
[linear]
token_env = "SPEC_ORCH_LINEAR_TOKEN"

[planner]
model = "MiniMax-M2.5"
api_key_env = "MINIMAX_API_KEY"

[supervisor]
model = "MiniMax-M2.5"
api_key_env = "MINIMAX_API_KEY"

[builder]
adapter = "acpx_codex"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("SPEC_ORCH_LINEAR_TOKEN", raising=False)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    missing = _gather_launcher_readiness(repo)
    assert missing["linear"]["ready"] is False
    assert missing["planner"]["ready"] is False
    assert missing["supervisor"]["ready"] is False
    assert missing["builder"]["ready"] is True

    monkeypatch.setenv("SPEC_ORCH_LINEAR_TOKEN", "lin_api_test")
    monkeypatch.setenv("MINIMAX_API_KEY", "sk-test")
    ready = _gather_launcher_readiness(repo)
    assert ready["linear"]["ready"] is True
    assert ready["planner"]["ready"] is True
    assert ready["supervisor"]["ready"] is True
    assert ready["builder"]["ready"] is True


def test_create_mission_draft_writes_meta_and_spec(repo: Path) -> None:
    from spec_orch.dashboard.launcher import _create_mission_draft

    result = _create_mission_draft(
        repo,
        {
            "title": "Launcher Smoke",
            "mission_id": "launcher-smoke",
            "intent": "Validate dashboard-first mission creation.",
            "acceptance_criteria": ["A visible mission draft exists."],
            "constraints": ["Keep scope tiny."],
        },
    )

    assert result["mission_id"] == "launcher-smoke"
    spec_path = repo / "docs" / "specs" / "launcher-smoke" / "spec.md"
    meta_path = repo / "docs" / "specs" / "launcher-smoke" / "mission.json"
    assert spec_path.exists()
    assert meta_path.exists()
    assert "Validate dashboard-first mission creation." in spec_path.read_text(encoding="utf-8")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["acceptance_criteria"] == ["A visible mission draft exists."]
    assert meta["constraints"] == ["Keep scope tiny."]


def test_approve_and_plan_mission_writes_plan_json(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from spec_orch.dashboard.launcher import _approve_and_plan_mission, _create_mission_draft

    _create_mission_draft(
        repo,
        {
            "title": "Plan Me",
            "mission_id": "plan-me",
            "intent": "Generate a simple plan.",
            "acceptance_criteria": [],
            "constraints": [],
        },
    )

    def fake_plan(root: Path, mission_id: str) -> dict:
        assert root == repo
        assert mission_id == "plan-me"
        plan_path = root / "docs" / "specs" / mission_id / "plan.json"
        payload = {
            "plan_id": "plan-1",
            "mission_id": mission_id,
            "status": "draft",
            "waves": [{"wave_number": 1, "description": "Wave 1", "work_packets": []}],
        }
        plan_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        return payload

    monkeypatch.setattr("spec_orch.dashboard.launcher._generate_plan_for_mission", fake_plan)

    result = _approve_and_plan_mission(repo, "plan-me")

    assert result["mission_id"] == "plan-me"
    assert result["plan"]["plan_id"] == "plan-1"
    assert (repo / "docs" / "specs" / "plan-me" / "plan.json").exists()


def test_create_linear_issue_for_mission_records_launch_metadata(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from spec_orch.dashboard.launcher import (
        _create_linear_issue_for_mission,
        _create_mission_draft,
    )

    _create_mission_draft(
        repo,
        {
            "title": "Linear Launch",
            "mission_id": "linear-launch",
            "intent": "Bind mission to Linear.",
            "acceptance_criteria": [],
            "constraints": [],
        },
    )

    class FakeLinearClient:
        def __init__(self, **_: object) -> None:
            pass

        def query(self, graphql: str, variables: dict | None = None) -> dict:
            if "teams(" in graphql:
                return {"teams": {"nodes": [{"id": "team-1", "key": "SON", "name": "Songwork"}]}}
            if "issueCreate" in graphql:
                return {
                    "issueCreate": {
                        "issue": {
                            "id": "issue-1",
                            "identifier": "SON-999",
                            "title": variables["title"],
                            "url": "https://linear.app/songwork/issue/SON-999/example",
                        }
                    }
                }
            raise AssertionError(graphql)

        def close(self) -> None:
            return None

    monkeypatch.setattr("spec_orch.dashboard.launcher.LinearClient", FakeLinearClient)

    result = _create_linear_issue_for_mission(
        repo,
        "linear-launch",
        title="Dogfood launcher run",
        description="Track this dogfood run.",
    )

    assert result["linear_issue"]["identifier"] == "SON-999"
    launch_path = repo / "docs" / "specs" / "linear-launch" / "operator" / "launch.json"
    assert launch_path.exists()
    launch_meta = json.loads(launch_path.read_text(encoding="utf-8"))
    assert launch_meta["linear_issue"]["identifier"] == "SON-999"


def test_launch_mission_uses_lifecycle_and_returns_state(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from spec_orch.dashboard.launcher import _launch_mission

    class FakeState:
        def __init__(self, phase: str) -> None:
            self.phase = phase

        def to_dict(self) -> dict[str, str]:
            return {"mission_id": "launch-me", "phase": self.phase}

    calls: list[tuple[str, str]] = []

    class FakeLifecycleManager:
        def __init__(self, _root: Path) -> None:
            return None

        def plan_complete(self, mission_id: str, issue_ids: list[str]) -> FakeState:
            calls.append(("plan_complete", mission_id))
            assert issue_ids == ["LOCAL-1"]
            return FakeState("planned")

        def auto_advance(self, mission_id: str) -> FakeState:
            calls.append(("auto_advance", mission_id))
            return FakeState("executing")

    plan_path = repo / "docs" / "specs" / "launch-me"
    plan_path.mkdir(parents=True)
    (repo / "spec-orch.toml").write_text(
        """
[supervisor]
model = "MiniMax-M2.7-highspeed"
api_key_env = "MINIMAX_API_KEY"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (plan_path / "plan.json").write_text(
        json.dumps(
            {
                "plan_id": "plan-1",
                "mission_id": "launch-me",
                "status": "draft",
                "waves": [
                    {
                        "wave_number": 1,
                        "description": "Wave",
                        "work_packets": [{"packet_id": "pkt-1", "title": "LOCAL-1"}],
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "spec_orch.dashboard.launcher.MissionLifecycleManager",
        FakeLifecycleManager,
    )
    launched: list[str] = []
    monkeypatch.setattr(
        "spec_orch.dashboard.launcher._start_background_mission_runner",
        lambda root, mission_id: launched.append(mission_id) or True,
    )

    result = _launch_mission(repo, "launch-me")

    assert result["state"]["phase"] == "executing"
    assert calls == [("plan_complete", "launch-me"), ("auto_advance", "launch-me")]
    assert launched == ["launch-me"]
