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
api_base_env = "MINIMAX_ANTHROPIC_BASE_URL"

[supervisor]
adapter = "litellm"
model = "MiniMax-M2.5"
api_key_env = "MINIMAX_API_KEY"
api_base_env = "MINIMAX_ANTHROPIC_BASE_URL"
max_rounds = 12

[builder]
adapter = "acpx_codex"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("SPEC_ORCH_LINEAR_TOKEN", raising=False)
    monkeypatch.delenv("LINEAR_TOKEN", raising=False)
    monkeypatch.delenv("LINEAR_API_TOKEN", raising=False)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    monkeypatch.delenv("MINIMAX_ANTHROPIC_BASE_URL", raising=False)
    missing = _gather_launcher_readiness(repo)
    assert missing["linear"]["ready"] is False
    assert missing["planner"]["ready"] is False
    assert missing["supervisor"]["ready"] is False
    assert missing["builder"]["ready"] is True

    monkeypatch.setenv("SPEC_ORCH_LINEAR_TOKEN", "lin_api_test")
    monkeypatch.setenv("MINIMAX_API_KEY", "sk-test")
    monkeypatch.setenv("MINIMAX_ANTHROPIC_BASE_URL", "https://api.minimaxi.com/anthropic")
    ready = _gather_launcher_readiness(repo)
    assert ready["linear"]["ready"] is True
    assert ready["planner"]["ready"] is True
    assert ready["supervisor"]["ready"] is True
    assert ready["builder"]["ready"] is True


def test_launcher_readiness_requires_explicit_slot_envs_when_configured(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from spec_orch.dashboard.launcher import _gather_launcher_readiness

    (repo / "spec-orch.toml").write_text(
        """
[linear]
token_env = "SPEC_ORCH_LINEAR_TOKEN"

[planner]
model = "MiniMax-M2.7-highspeed"
api_type = "anthropic"
api_key_env = "SPEC_ORCH_LLM_API_KEY"
api_base_env = "SPEC_ORCH_LLM_API_BASE"

[supervisor]
adapter = "litellm"
model = "MiniMax-M2.7-highspeed"
api_type = "anthropic"
api_key_env = "SPEC_ORCH_LLM_API_KEY"
api_base_env = "SPEC_ORCH_LLM_API_BASE"
max_rounds = 12

[builder]
adapter = "acpx"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("SPEC_ORCH_LINEAR_TOKEN", "lin_api_test")
    monkeypatch.delenv("SPEC_ORCH_LLM_API_KEY", raising=False)
    monkeypatch.delenv("SPEC_ORCH_LLM_API_BASE", raising=False)
    monkeypatch.setenv("MINIMAX_API_KEY", "sk-minimax")
    monkeypatch.setenv("MINIMAX_ANTHROPIC_BASE_URL", "https://api.minimaxi.com/anthropic")

    readiness = _gather_launcher_readiness(repo)
    assert readiness["planner"]["ready"] is False
    assert readiness["supervisor"]["ready"] is False


def test_launcher_readiness_falls_back_to_linear_token_alias(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from spec_orch.dashboard.launcher import _gather_launcher_readiness

    (repo / "spec-orch.toml").write_text(
        """
[linear]
token_env = "SPEC_ORCH_LINEAR_TOKEN"

[planner]
model = "MiniMax-M2.7-highspeed"
api_type = "anthropic"
api_key_env = "SPEC_ORCH_LLM_API_KEY"
api_base_env = "SPEC_ORCH_LLM_API_BASE"

[supervisor]
adapter = "litellm"
model = "MiniMax-M2.7-highspeed"
api_type = "anthropic"
api_key_env = "SPEC_ORCH_LLM_API_KEY"
api_base_env = "SPEC_ORCH_LLM_API_BASE"
max_rounds = 12

[builder]
adapter = "acpx"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("SPEC_ORCH_LINEAR_TOKEN", raising=False)
    monkeypatch.setenv("LINEAR_TOKEN", "lin-fallback")
    monkeypatch.setenv("MINIMAX_API_KEY", "sk-minimax")
    monkeypatch.setenv("MINIMAX_ANTHROPIC_BASE_URL", "https://api.minimaxi.com/anthropic")

    readiness = _gather_launcher_readiness(repo)
    assert readiness["linear"]["ready"] is True
    assert readiness["linear"]["token_env"] == "SPEC_ORCH_LINEAR_TOKEN"


def test_launcher_readiness_rejects_invalid_api_types(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from spec_orch.dashboard.launcher import _gather_launcher_readiness

    (repo / "spec-orch.toml").write_text(
        """
[linear]
token_env = "SPEC_ORCH_LINEAR_TOKEN"

[planner]
model = "MiniMax-M2.7-highspeed"
api_type = "not-a-provider"
api_key_env = "MINIMAX_API_KEY"
api_base_env = "MINIMAX_ANTHROPIC_BASE_URL"

[supervisor]
adapter = "litellm"
model = "MiniMax-M2.7-highspeed"
api_type = "also-bad"
api_key_env = "MINIMAX_API_KEY"
api_base_env = "MINIMAX_ANTHROPIC_BASE_URL"
max_rounds = 12

[builder]
adapter = "acpx"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("SPEC_ORCH_LINEAR_TOKEN", "lin_api_test")
    monkeypatch.setenv("MINIMAX_API_KEY", "sk-minimax")
    monkeypatch.setenv("MINIMAX_ANTHROPIC_BASE_URL", "https://api.minimaxi.com/anthropic")

    readiness = _gather_launcher_readiness(repo)

    assert readiness["planner"]["ready"] is False
    assert readiness["planner"]["api_type"] == "not-a-provider"
    assert readiness["planner"]["error"] == "invalid api_type"
    assert readiness["supervisor"]["ready"] is False
    assert readiness["supervisor"]["api_type"] == "also-bad"
    assert readiness["supervisor"]["error"] == "invalid api_type"


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


def test_create_mission_draft_persists_dashboard_intake_workspace(repo: Path) -> None:
    from spec_orch.dashboard.launcher import _create_mission_draft

    result = _create_mission_draft(
        repo,
        {
            "title": "Dashboard Intake",
            "mission_id": "dashboard-intake",
            "problem": "Operators cannot preview canonical intake state from the dashboard.",
            "goal": "Make dashboard intake preview readiness before launch.",
            "intent": "Turn launcher into intake workspace v0.",
            "acceptance_criteria": [
                "Operators can see readiness before workspace handoff.",
                "Operators can inspect a canonical issue preview.",
            ],
            "constraints": ["Keep SON-410 schema lock for later."],
            "evidence_expectations": ["readiness panel", "canonical issue preview"],
            "open_questions": ["Should intake drafts support templates?"],
            "current_system_understanding": "Launcher owns mission drafting before execution.",
        },
    )

    workspace_path = (
        repo / "docs" / "specs" / "dashboard-intake" / "operator" / "intake_workspace.json"
    )
    assert workspace_path.exists()
    workspace = json.loads(workspace_path.read_text(encoding="utf-8"))
    assert result["intake_workspace"]["state"] == "ready_for_workspace"
    assert workspace["state"] == "ready_for_workspace"
    assert workspace["readiness"]["is_ready"] is True
    assert workspace["handoff"]["state"] == "ready_for_workspace"
    assert workspace["handoff"]["workspace"]["workspace_id"] == "dashboard-intake"
    assert workspace["handoff"]["workspace"]["active_execution"]["phase"] == "intake"
    assert workspace["handoff"]["active_execution"]["status"] == "pending"
    assert workspace["handoff"]["initial_judgment"]["status"] == "pending"
    assert workspace["handoff"]["learning_lineage"]["status"] == "pending"
    assert (
        workspace["canonical_issue"]["problem"]
        == "Operators cannot preview canonical intake state from the dashboard."
    )
    assert workspace["canonical_issue"]["acceptance"]["verification_expectations"] == [
        "readiness panel",
        "canonical issue preview",
    ]


def test_dashboard_intake_workspace_marks_missing_problem_and_goal_as_clarifying(
    repo: Path,
) -> None:
    from spec_orch.dashboard.launcher import _build_dashboard_intake_workspace

    workspace = _build_dashboard_intake_workspace(
        repo,
        mission_id="clarify-me",
        payload={
            "title": "Clarify Me",
            "intent": "Need more structure.",
            "acceptance_criteria": [],
            "constraints": [],
            "evidence_expectations": [],
            "open_questions": ["[blocking] What exact operator flow is in scope?"],
        },
    )

    assert workspace["state"] == "clarifying"
    assert workspace["readiness"]["is_ready"] is False
    assert "problem" in workspace["readiness"]["missing_fields"]
    assert "goal" in workspace["readiness"]["missing_fields"]
    assert workspace["handoff"]["state"] == "draft_only"


def test_dashboard_intake_workspace_can_be_loaded_for_existing_mission(repo: Path) -> None:
    from spec_orch.dashboard.launcher import (
        _create_mission_draft,
        _load_dashboard_intake_workspace,
    )

    _create_mission_draft(
        repo,
        {
            "title": "Existing Intake",
            "mission_id": "existing-intake",
            "problem": "Operators need a stable intake workspace.",
            "goal": "Preserve structured intake between launcher actions.",
            "intent": "Load persisted workspace.",
            "acceptance_criteria": ["The dashboard reloads the saved intake state."],
            "constraints": [],
            "evidence_expectations": ["persisted intake workspace"],
            "open_questions": [],
            "current_system_understanding": "Launcher persists operator draft state.",
        },
    )

    loaded = _load_dashboard_intake_workspace(repo, "existing-intake")

    assert loaded is not None
    assert loaded["mission_id"] == "existing-intake"
    assert (
        loaded["canonical_issue"]["goal"] == "Preserve structured intake between launcher actions."
    )


def test_build_fresh_acpx_mission_request_generates_unique_local_bootstrap(repo: Path) -> None:
    from spec_orch.dashboard.launcher import _build_fresh_acpx_mission_request

    first = _build_fresh_acpx_mission_request(repo)
    second = _build_fresh_acpx_mission_request(repo)

    assert first["execution_mode"] == "fresh_acpx_mission"
    assert first["local_only"] is True
    assert first["safe_cleanup"] is True
    assert first["mission_id"].startswith("fresh-acpx-")
    assert first["mission_id"] != second["mission_id"]
    assert first["metadata"]["fresh"] is True
    assert first["metadata"]["fresh_variant"] == "default"
    assert first["metadata"]["artifact_namespace"] == "fresh-acpx-mission-e2e"
    assert first["metadata"]["max_waves"] == 1
    assert first["metadata"]["max_packets"] == 2
    assert first["post_run_campaign"]["mode"] == "workflow"
    assert any("at most 2 work packets" in item for item in first["constraints"])
    assert any(
        first["mission_id"] in route for route in first["post_run_campaign"]["primary_routes"]
    )


def test_build_fresh_acpx_mission_request_supports_runtime_variants(repo: Path) -> None:
    from spec_orch.dashboard.launcher import _build_fresh_acpx_mission_request

    multi_packet = _build_fresh_acpx_mission_request(repo, variant="multi_packet")
    linear_bound = _build_fresh_acpx_mission_request(repo, variant="linear_bound")

    assert multi_packet["metadata"]["fresh_variant"] == "multi_packet"
    assert multi_packet["metadata"]["max_packets"] == 3
    assert multi_packet["metadata"]["launcher_path"] == "approve_plan_launch"
    assert linear_bound["metadata"]["fresh_variant"] == "linear_bound"
    assert linear_bound["metadata"]["launcher_path"] == "create_linear_issue_then_launch"
    assert linear_bound["metadata"]["requires_linear"] is True


def test_is_fresh_acpx_mission_requires_acpx_prefix_without_bootstrap(repo: Path) -> None:
    from spec_orch.dashboard.launcher import _is_fresh_acpx_mission

    assert _is_fresh_acpx_mission(repo, "fresh-acpx-smoke") is True
    assert _is_fresh_acpx_mission(repo, "fresh-homepage") is False
    assert (repo / "docs" / "specs" / "fresh-homepage" / "operator").exists() is False


def test_create_mission_draft_rejects_null_title_and_treats_null_mission_id_as_absent(
    repo: Path,
) -> None:
    from spec_orch.dashboard.launcher import _create_mission_draft

    with pytest.raises(ValueError, match="Mission title is required"):
        _create_mission_draft(
            repo,
            {
                "title": None,
                "mission_id": None,
                "intent": "Validate null handling.",
                "acceptance_criteria": [],
                "constraints": [],
            },
        )

    result = _create_mission_draft(
        repo,
        {
            "title": "Null Mission Id",
            "mission_id": None,
            "intent": "Validate null handling.",
            "acceptance_criteria": [],
            "constraints": [],
        },
    )

    assert result["mission_id"] != "None"
    assert not (repo / "docs" / "specs" / "None").exists()


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


def test_approve_and_plan_mission_syncs_bound_linear_issue_description(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from spec_orch.dashboard.launcher import (
        _approve_and_plan_mission,
        _create_mission_draft,
        _write_launch_metadata,
    )

    _create_mission_draft(
        repo,
        {
            "title": "Plan Me",
            "mission_id": "plan-me",
            "problem": "Linear drifts from the real execution plan.",
            "goal": "Sync the plan snapshot into the bound issue.",
            "intent": "Generate a simple plan.",
            "acceptance_criteria": ["The Linear issue shows a compact plan snapshot."],
            "constraints": [],
            "evidence_expectations": ["plan snapshot"],
        },
    )
    _write_launch_metadata(
        repo,
        "plan-me",
        {"linear_issue": {"id": "issue-1", "identifier": "SON-101", "title": "Plan Me"}},
    )

    def fake_plan(root: Path, mission_id: str) -> dict:
        plan_path = root / "docs" / "specs" / mission_id / "plan.json"
        payload = {
            "plan_id": "plan-1",
            "mission_id": mission_id,
            "status": "draft",
            "waves": [{"wave_number": 0, "description": "Wave 0", "work_packets": []}],
        }
        plan_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return payload

    captured_updates: list[str] = []

    class FakeLinearClient:
        def __init__(self, **_: object) -> None:
            pass

        def query(self, graphql: str, variables: dict | None = None) -> dict:
            if "query($id: String!)" in graphql:
                return {"issue": {"id": "issue-1", "description": "mission: plan-me"}}
            if "issueUpdate" in graphql:
                captured_updates.append(str(variables["description"]))
                return {
                    "issueUpdate": {
                        "success": True,
                        "issue": {"id": "issue-1", "description": str(variables["description"])},
                    }
                }
            raise AssertionError(graphql)

        def update_issue_description(self, issue_id: str, *, description: str) -> dict:
            assert issue_id == "issue-1"
            captured_updates.append(description)
            return {"success": True, "issue": {"id": issue_id, "description": description}}

        def close(self) -> None:
            return None

    monkeypatch.setattr("spec_orch.dashboard.launcher._generate_plan_for_mission", fake_plan)
    monkeypatch.setattr("spec_orch.dashboard.launcher.LinearClient", FakeLinearClient)

    _approve_and_plan_mission(repo, "plan-me")

    assert captured_updates
    assert '"plan_state": "draft"' in captured_updates[0]
    assert '"next_action": "review_plan"' in captured_updates[0]


def test_approve_and_plan_mission_injects_fresh_verification_commands(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from spec_orch.dashboard.launcher import _approve_and_plan_mission, _create_mission_draft

    mission_id = "fresh-acpx-plan"

    _create_mission_draft(
        repo,
        {
            "title": "Fresh Plan",
            "mission_id": mission_id,
            "intent": "Generate a fresh-acpx smoke plan.",
            "acceptance_criteria": [],
            "constraints": [],
        },
    )

    def fake_plan(root: Path, mission_id: str) -> dict:
        assert root == repo
        assert mission_id == "fresh-acpx-plan"
        payload = {
            "plan_id": "plan-fresh",
            "mission_id": mission_id,
            "status": "draft",
            "waves": [
                {
                    "wave_number": 0,
                    "description": "Fresh smoke",
                    "work_packets": [
                        {
                            "packet_id": "pkt-a",
                            "title": "Scaffold mission types",
                            "files_in_scope": ["src/contracts/mission_types.ts"],
                            "verification_commands": {},
                        },
                        {
                            "packet_id": "pkt-b",
                            "title": "Scaffold artifact types",
                            "files_in_scope": ["src/contracts/artifact_types.ts"],
                            "verification_commands": {},
                        },
                    ],
                }
            ],
        }
        (root / "docs" / "specs" / mission_id / "plan.json").write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )
        return payload

    monkeypatch.setattr("spec_orch.dashboard.launcher._generate_plan_for_mission", fake_plan)

    result = _approve_and_plan_mission(repo, mission_id)

    packet_commands = [
        packet["verification_commands"] for packet in result["plan"]["waves"][0]["work_packets"]
    ]
    assert all(commands for commands in packet_commands)
    persisted = json.loads(
        (repo / "docs" / "specs" / mission_id / "plan.json").read_text(encoding="utf-8")
    )
    persisted_commands = [
        packet["verification_commands"] for packet in persisted["waves"][0]["work_packets"]
    ]
    assert packet_commands == persisted_commands
    assert all(
        set(commands)
        >= {
            "scaffold_exists",
            "typescript_contract_tokens",
            "typescript_schema_surface",
            "typescript_typecheck",
            "typescript_lint_smoke",
            "typescript_import_smoke",
        }
        for commands in packet_commands
    )


def test_approve_and_plan_mission_merges_isolated_fresh_verification_packets(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from spec_orch.dashboard.launcher import _approve_and_plan_mission, _create_mission_draft

    mission_id = "fresh-acpx-merge-plan"

    _create_mission_draft(
        repo,
        {
            "title": "Fresh Merge Plan",
            "mission_id": mission_id,
            "intent": "Generate a fresh-acpx plan that would otherwise verify in a second workspace.",
            "acceptance_criteria": [],
            "constraints": [],
        },
    )

    def fake_plan(root: Path, mission_id: str) -> dict:
        payload = {
            "plan_id": "plan-fresh-merge",
            "mission_id": mission_id,
            "status": "draft",
            "waves": [
                {
                    "wave_number": 0,
                    "description": "Fresh smoke",
                    "work_packets": [
                        {
                            "packet_id": "contract-scaffold",
                            "title": "Scaffold TypeScript contract files",
                            "files_in_scope": [
                                "src/contracts/mission_types.ts",
                                "src/contracts/artifact_types.ts",
                            ],
                            "builder_prompt": "Create the two contract files.",
                            "verification_commands": {},
                        },
                        {
                            "packet_id": "contract-verification",
                            "title": "Verify the contracts compile",
                            "files_in_scope": [
                                "src/contracts/mission_types.ts",
                                "src/contracts/artifact_types.ts",
                            ],
                            "builder_prompt": "Run TypeScript compiler (tsc --noEmit) and ESLint on the newly created contract files.",
                            "verification_commands": {},
                        },
                    ],
                }
            ],
        }
        (root / "docs" / "specs" / mission_id / "plan.json").write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )
        return payload

    monkeypatch.setattr("spec_orch.dashboard.launcher._generate_plan_for_mission", fake_plan)

    result = _approve_and_plan_mission(repo, mission_id)

    packets = result["plan"]["waves"][0]["work_packets"]
    assert len(packets) == 1
    assert packets[0]["packet_id"] == "contract-scaffold"
    assert packets[0]["builder_prompt"] == "Create the two contract files."
    assert set(packets[0]["verification_commands"]) >= {
        "typescript_typecheck",
        "typescript_lint_smoke",
        "typescript_import_smoke",
    }


def test_approve_and_plan_mission_merges_verify_packet_named_for_lint_typecheck(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from spec_orch.dashboard.launcher import _approve_and_plan_mission, _create_mission_draft

    mission_id = "fresh-acpx-verify-name-plan"

    _create_mission_draft(
        repo,
        {
            "title": "Fresh Verify Name Plan",
            "mission_id": mission_id,
            "intent": "Generate a fresh-acpx plan with a separate verify packet.",
            "acceptance_criteria": [],
            "constraints": [],
        },
    )

    def fake_plan(root: Path, mission_id: str) -> dict:
        payload = {
            "plan_id": "plan-fresh-verify-name",
            "mission_id": mission_id,
            "status": "draft",
            "waves": [
                {
                    "wave_number": 0,
                    "description": "Fresh smoke",
                    "work_packets": [
                        {
                            "packet_id": "scaffold-contracts",
                            "title": "Scaffold TypeScript contract files",
                            "files_in_scope": [
                                "src/contracts/mission_types.ts",
                                "src/contracts/artifact_types.ts",
                            ],
                            "builder_prompt": "Create the contract files.",
                            "verification_commands": {},
                        },
                        {
                            "packet_id": "verify-contracts",
                            "title": "Verify contract files with lint and typecheck",
                            "files_in_scope": [
                                "src/contracts/mission_types.ts",
                                "src/contracts/artifact_types.ts",
                            ],
                            "depends_on": ["scaffold-contracts"],
                            "builder_prompt": "Run lint and TypeScript typecheck on the contract files.",
                            "verification_commands": {},
                        },
                    ],
                }
            ],
        }
        (root / "docs" / "specs" / mission_id / "plan.json").write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )
        return payload

    monkeypatch.setattr("spec_orch.dashboard.launcher._generate_plan_for_mission", fake_plan)

    result = _approve_and_plan_mission(repo, mission_id)

    packets = result["plan"]["waves"][0]["work_packets"]
    assert len(packets) == 1
    assert packets[0]["packet_id"] == "scaffold-contracts"
    assert packets[0]["builder_prompt"] == "Create the contract files."
    assert set(packets[0]["verification_commands"]) >= {
        "typescript_typecheck",
        "typescript_lint_smoke",
        "typescript_import_smoke",
    }


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
            "problem": "Linear issue state drifts from runtime truth.",
            "goal": "Create a new issue with the latest structured mirror.",
            "intent": "Bind mission to Linear.",
            "acceptance_criteria": ["The issue gets a structured mirror block."],
            "constraints": [],
            "evidence_expectations": ["structured mirror block"],
            "current_system_understanding": "Launcher owns mission drafting before execution.",
        },
    )

    captured_descriptions: list[str] = []

    class FakeLinearClient:
        def __init__(self, **_: object) -> None:
            pass

        def query(self, graphql: str, variables: dict | None = None) -> dict:
            if "teams(" in graphql:
                return {"teams": {"nodes": [{"id": "team-1", "key": "SON", "name": "Songwork"}]}}
            if "issueCreate" in graphql:
                captured_descriptions.append(str(variables["description"]))
                return {
                    "issueCreate": {
                        "success": True,
                        "issue": {
                            "id": "issue-1",
                            "identifier": "SON-999",
                            "title": variables["title"],
                            "url": "https://linear.app/songwork/issue/SON-999/example",
                        },
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
    assert captured_descriptions
    assert "## SpecOrch Mirror" in captured_descriptions[0]
    assert "create_workspace" in captured_descriptions[0]


def test_create_linear_issue_for_mission_requires_resolved_team(
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
                return {"teams": {"nodes": []}}
            raise AssertionError(graphql)

        def close(self) -> None:
            return None

    monkeypatch.setattr("spec_orch.dashboard.launcher.LinearClient", FakeLinearClient)

    with pytest.raises(ValueError, match="Linear team not found"):
        _create_linear_issue_for_mission(
            repo,
            "linear-launch",
            title="Dogfood launcher run",
            description="Track this dogfood run.",
        )


def test_bind_linear_issue_to_mission_validates_update_success(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from spec_orch.dashboard.launcher import (
        _bind_linear_issue_to_mission,
        _create_mission_draft,
    )

    _create_mission_draft(
        repo,
        {
            "title": "Linear Bind",
            "mission_id": "linear-bind",
            "intent": "Bind mission to existing issue.",
            "acceptance_criteria": [],
            "constraints": [],
        },
    )

    class FakeLinearClient:
        def __init__(self, **_: object) -> None:
            pass

        def query(self, graphql: str, variables: dict | None = None) -> dict:
            if "query($id: String!)" in graphql:
                return {
                    "issue": {
                        "id": "issue-1",
                        "identifier": "SON-123",
                        "title": "Existing issue",
                        "description": "hello",
                        "url": "https://linear.app/songwork/issue/SON-123/example",
                    }
                }
            if "issueUpdate" in graphql:
                return {"issueUpdate": {"success": False, "issue": None}}
            raise AssertionError(graphql)

        def close(self) -> None:
            return None

    monkeypatch.setattr("spec_orch.dashboard.launcher.LinearClient", FakeLinearClient)

    with pytest.raises(ValueError, match="Linear issue description update failed"):
        _bind_linear_issue_to_mission(repo, "linear-bind", "issue-1")


def test_bind_linear_issue_to_mission_appends_structured_linear_mirror(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from spec_orch.dashboard.launcher import (
        _bind_linear_issue_to_mission,
        _create_mission_draft,
    )

    _create_mission_draft(
        repo,
        {
            "title": "Linear Bind Success",
            "mission_id": "linear-bind-success",
            "problem": "Existing Linear issues drift from runtime truth.",
            "goal": "Rewrite the issue with a structured mirror.",
            "intent": "Bind mission to existing issue.",
            "acceptance_criteria": ["The issue gets the latest mirror block."],
            "constraints": [],
            "evidence_expectations": ["structured mirror block"],
            "current_system_understanding": "Launcher owns mission drafting before execution.",
        },
    )

    captured_updates: list[str] = []

    class FakeLinearClient:
        def __init__(self, **_: object) -> None:
            pass

        def query(self, graphql: str, variables: dict | None = None) -> dict:
            if "query($id: String!)" in graphql:
                return {
                    "issue": {
                        "id": "issue-1",
                        "identifier": "SON-123",
                        "title": "Existing issue",
                        "description": "hello",
                        "url": "https://linear.app/songwork/issue/SON-123/example",
                    }
                }
            if "issueUpdate" in graphql:
                captured_updates.append(str(variables["description"]))
                return {
                    "issueUpdate": {
                        "success": True,
                        "issue": {
                            "id": "issue-1",
                            "identifier": "SON-123",
                            "title": "Existing issue",
                            "url": "https://linear.app/songwork/issue/SON-123/example",
                            "description": str(variables["description"]),
                        },
                    }
                }
            raise AssertionError(graphql)

        def close(self) -> None:
            return None

    monkeypatch.setattr("spec_orch.dashboard.launcher.LinearClient", FakeLinearClient)

    result = _bind_linear_issue_to_mission(repo, "linear-bind-success", "issue-1")

    assert result["linear_issue"]["identifier"] == "SON-123"
    assert captured_updates
    assert "## SpecOrch Mirror" in captured_updates[0]
    assert "create_workspace" in captured_updates[0]


def test_create_linear_issue_for_mission_validates_mutation_success(
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
                return {"issueCreate": {"success": False, "issue": None}}
            raise AssertionError(graphql)

        def close(self) -> None:
            return None

    monkeypatch.setattr("spec_orch.dashboard.launcher.LinearClient", FakeLinearClient)

    with pytest.raises(ValueError, match="Linear issue creation failed"):
        _create_linear_issue_for_mission(
            repo,
            "linear-launch",
            title="Dogfood launcher run",
            description="Track this dogfood run.",
        )


def test_write_launch_metadata_uses_dedicated_lock(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from spec_orch.dashboard.launcher import _write_launch_metadata

    events: list[str] = []

    class RecordingLock:
        def __enter__(self) -> None:
            events.append("enter")
            return None

        def __exit__(self, exc_type, exc, tb) -> None:
            events.append("exit")
            return None

    monkeypatch.setattr("spec_orch.dashboard.launcher._LAUNCH_META_LOCK", RecordingLock())

    _write_launch_metadata(repo, "lock-me", {"runner": {"status": "running"}})

    assert events == ["enter", "exit"]


def test_launch_mission_uses_lifecycle_and_returns_state(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from spec_orch.dashboard.launcher import _launch_mission

    monkeypatch.setenv("MINIMAX_API_KEY", "sk-test")

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
adapter = "litellm"
model = "MiniMax-M2.7-highspeed"
api_key_env = "MINIMAX_API_KEY"
api_base_env = "MINIMAX_ANTHROPIC_BASE_URL"
max_rounds = 12
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MINIMAX_ANTHROPIC_BASE_URL", "https://api.minimaxi.com/anthropic")
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
    monkeypatch.setattr("spec_orch.dashboard.launcher._daemon_is_active", lambda root: False)

    result = _launch_mission(repo, "launch-me")

    assert result["state"]["phase"] == "executing"
    assert calls == [("plan_complete", "launch-me"), ("auto_advance", "launch-me")]
    assert launched == ["launch-me"]


def test_launch_mission_skips_background_runner_when_daemon_is_active(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from spec_orch.dashboard.launcher import _launch_mission

    monkeypatch.setenv("MINIMAX_API_KEY", "sk-test")
    monkeypatch.setenv("MINIMAX_ANTHROPIC_BASE_URL", "https://api.minimaxi.com/anthropic")

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
adapter = "litellm"
model = "MiniMax-M2.7-highspeed"
api_key_env = "MINIMAX_API_KEY"
api_base_env = "MINIMAX_ANTHROPIC_BASE_URL"
max_rounds = 12
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
    monkeypatch.setattr("spec_orch.dashboard.launcher._daemon_is_active", lambda root: True)

    result = _launch_mission(repo, "launch-me")

    assert result["state"]["phase"] == "executing"
    assert result["background_runner_started"] is False
    assert result["launch"]["runner"]["status"] == "daemon_running"
    assert calls == [("plan_complete", "launch-me"), ("auto_advance", "launch-me")]
    assert launched == []


def test_launch_mission_accepts_supervisor_default_model_chain(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from spec_orch.dashboard.launcher import _launch_mission

    monkeypatch.setenv("MINIMAX_API_KEY", "sk-test")
    monkeypatch.setenv("MINIMAX_ANTHROPIC_BASE_URL", "https://api.minimaxi.com/anthropic")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "fb-test")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://ark.cn-beijing.volces.com/api/coding")

    class FakeState:
        def __init__(self, phase: str) -> None:
            self.phase = phase

        def to_dict(self) -> dict[str, str]:
            return {"mission_id": "launch-me", "phase": self.phase}

    class FakeLifecycleManager:
        def __init__(self, _root: Path) -> None:
            return None

        def plan_complete(self, mission_id: str, issue_ids: list[str]) -> FakeState:
            assert mission_id == "launch-me"
            assert issue_ids == ["LOCAL-1"]
            return FakeState("planned")

        def auto_advance(self, mission_id: str) -> FakeState:
            assert mission_id == "launch-me"
            return FakeState("executing")

    plan_path = repo / "docs" / "specs" / "launch-me"
    plan_path.mkdir(parents=True)
    (repo / "spec-orch.toml").write_text(
        """
[llm]
default_model_chain = "default_reasoning"

[models.minimax_reasoning]
model = "MiniMax-M2.7-highspeed"
api_type = "anthropic"
api_key_env = "MINIMAX_API_KEY"
api_base_env = "MINIMAX_ANTHROPIC_BASE_URL"

[models.doubao_seed_code]
model = "doubao-seed-2.0-code"
api_type = "anthropic"
api_key_env = "ANTHROPIC_AUTH_TOKEN"
api_base_env = "ANTHROPIC_BASE_URL"

[model_chains.default_reasoning]
primary = "minimax_reasoning"
fallbacks = ["doubao_seed_code"]

[supervisor]
adapter = "litellm"
max_rounds = 12
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
    monkeypatch.setattr("spec_orch.dashboard.launcher._daemon_is_active", lambda root: False)
    monkeypatch.setattr(
        "spec_orch.dashboard.launcher._start_background_mission_runner",
        lambda root, mission_id: True,
    )

    result = _launch_mission(repo, "launch-me")

    assert result["state"]["phase"] == "executing"
