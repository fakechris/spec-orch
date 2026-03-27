from __future__ import annotations

import importlib.util
import json
import os
import threading
import tomllib
from pathlib import Path
from typing import Any

from spec_orch.services.lifecycle_manager import MissionLifecycleManager
from spec_orch.services.linear_client import LinearClient
from spec_orch.services.mission_service import MissionService
from spec_orch.services.promotion_service import load_plan

_RUNNER_LOCK = threading.Lock()
_ACTIVE_RUNNERS: dict[str, threading.Thread] = {}


def _load_raw_config(repo_root: Path) -> dict[str, Any]:
    config_path = repo_root / "spec-orch.toml"
    if not config_path.exists():
        return {}
    try:
        with config_path.open("rb") as handle:
            raw = tomllib.load(handle)
    except (FileNotFoundError, tomllib.TOMLDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _get_linear_settings(repo_root: Path) -> tuple[str, str]:
    raw = _load_raw_config(repo_root)
    linear_cfg = raw.get("linear", {})
    if not isinstance(linear_cfg, dict):
        linear_cfg = {}
    token_env = str(linear_cfg.get("token_env", "SPEC_ORCH_LINEAR_TOKEN"))
    team_key = str(linear_cfg.get("team_key", "SON"))
    return token_env, team_key


def _operator_dir(repo_root: Path, mission_id: str) -> Path:
    path = repo_root / "docs" / "specs" / mission_id / "operator"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _launch_meta_path(repo_root: Path, mission_id: str) -> Path:
    return _operator_dir(repo_root, mission_id) / "launch.json"


def _read_launch_metadata(repo_root: Path, mission_id: str) -> dict[str, Any]:
    path = _launch_meta_path(repo_root, mission_id)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_launch_metadata(
    repo_root: Path,
    mission_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    current = _read_launch_metadata(repo_root, mission_id)
    current.update(payload)
    _launch_meta_path(repo_root, mission_id).write_text(
        json.dumps(current, indent=2) + "\n",
        encoding="utf-8",
    )
    return current


def _build_spec_markdown(
    *,
    title: str,
    intent: str,
    acceptance_criteria: list[str],
    constraints: list[str],
) -> str:
    return (
        f"# {title}\n\n"
        "## Intent\n\n"
        f"{intent.strip() or '<!-- describe the user value -->'}\n\n"
        "## Acceptance Criteria\n\n"
        + "".join(f"- {item}\n" for item in acceptance_criteria)
        + "\n## Constraints\n\n"
        + "".join(f"- {item}\n" for item in constraints)
        + "\n## Interface Contracts\n\n"
        "<!-- frozen APIs / schemas -->\n"
    )


def _gather_launcher_readiness(repo_root: Path) -> dict[str, Any]:
    raw = _load_raw_config(repo_root)
    planner_cfg = raw.get("planner", {}) if isinstance(raw.get("planner", {}), dict) else {}
    supervisor_cfg = (
        raw.get("supervisor", {}) if isinstance(raw.get("supervisor", {}), dict) else {}
    )
    builder_cfg = raw.get("builder", {}) if isinstance(raw.get("builder", {}), dict) else {}
    token_env, _team_key = _get_linear_settings(repo_root)

    planner_key = ""
    if planner_cfg.get("api_key_env"):
        planner_key = os.environ.get(str(planner_cfg["api_key_env"]), "")

    supervisor_key = ""
    if supervisor_cfg.get("api_key_env"):
        supervisor_key = os.environ.get(str(supervisor_cfg["api_key_env"]), "")

    dashboard_deps = all(
        importlib.util.find_spec(module) is not None
        for module in ("fastapi", "uvicorn", "websockets")
    )

    return {
        "config_present": (repo_root / "spec-orch.toml").exists(),
        "dashboard": {"ready": dashboard_deps},
        "linear": {
            "ready": bool(os.environ.get(token_env, "")),
            "token_env": token_env,
        },
        "planner": {
            "ready": bool(planner_cfg.get("model")) and bool(planner_key),
            "model": planner_cfg.get("model"),
        },
        "supervisor": {
            "ready": bool(supervisor_cfg.get("model")) and bool(supervisor_key),
            "model": supervisor_cfg.get("model"),
        },
        "builder": {
            "ready": bool(builder_cfg.get("adapter")),
            "adapter": builder_cfg.get("adapter"),
        },
    }


def _create_mission_draft(repo_root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    title = str(payload.get("title", "")).strip()
    if not title:
        raise ValueError("Mission title is required")
    mission_id = str(payload.get("mission_id", "")).strip() or None
    acceptance_criteria = [
        str(item).strip() for item in payload.get("acceptance_criteria", []) if str(item).strip()
    ]
    constraints = [
        str(item).strip() for item in payload.get("constraints", []) if str(item).strip()
    ]
    intent = str(payload.get("intent", "")).strip()

    svc = MissionService(repo_root)
    mission = svc.create_mission(
        title,
        mission_id=mission_id,
        acceptance_criteria=acceptance_criteria or None,
        constraints=constraints or None,
    )
    spec_path = repo_root / mission.spec_path
    spec_path.write_text(
        _build_spec_markdown(
            title=mission.title,
            intent=intent,
            acceptance_criteria=acceptance_criteria,
            constraints=constraints,
        ),
        encoding="utf-8",
    )
    return {
        "mission_id": mission.mission_id,
        "title": mission.title,
        "status": mission.status.value,
        "spec_path": mission.spec_path,
    }


def _generate_plan_for_mission(repo_root: Path, mission_id: str) -> dict[str, Any]:
    # Reuse the existing lifecycle planning implementation instead of shelling out to CLI.
    mgr = MissionLifecycleManager(repo_root)
    return mgr._run_plan(mission_id)


def _approve_and_plan_mission(repo_root: Path, mission_id: str) -> dict[str, Any]:
    svc = MissionService(repo_root)
    mission = svc.approve_mission(mission_id)
    plan = _generate_plan_for_mission(repo_root, mission_id)
    return {
        "mission_id": mission.mission_id,
        "approved_at": mission.approved_at,
        "status": mission.status.value,
        "plan": plan,
    }


def _mission_binding_description(mission_id: str, description: str) -> str:
    description = description.strip()
    mission_line = f"mission: {mission_id}"
    if mission_line in description:
        return description
    if description:
        return f"{mission_line}\n\n{description}"
    return mission_line


def _create_linear_issue_for_mission(
    repo_root: Path,
    mission_id: str,
    *,
    title: str,
    description: str,
) -> dict[str, Any]:
    token_env, team_key = _get_linear_settings(repo_root)
    client = LinearClient(token_env=token_env)
    try:
        team = client.query(
            """
            query($key: String!) {
              teams(filter: { key: { eq: $key } }) { nodes { id key name } }
            }
            """,
            {"key": team_key},
        )["teams"]["nodes"][0]
        payload = client.query(
            """
            mutation($teamId: String!, $title: String!, $description: String!) {
              issueCreate(input: {
                teamId: $teamId,
                title: $title,
                description: $description
              }) {
                success
                issue { id identifier title url }
              }
            }
            """,
            {
                "teamId": team["id"],
                "title": title,
                "description": _mission_binding_description(mission_id, description),
            },
        )["issueCreate"]["issue"]
        launch_meta = _write_launch_metadata(
            repo_root,
            mission_id,
            {
                "linear_issue": payload,
                "linear_team_key": team_key,
            },
        )
        return {"mission_id": mission_id, "linear_issue": payload, "launch": launch_meta}
    finally:
        client.close()


def _bind_linear_issue_to_mission(
    repo_root: Path,
    mission_id: str,
    linear_issue_id: str,
) -> dict[str, Any]:
    token_env, team_key = _get_linear_settings(repo_root)
    client = LinearClient(token_env=token_env)
    try:
        issue = client.query(
            """
            query($id: String!) {
              issue(id: $id) { id identifier title description url }
            }
            """,
            {"id": linear_issue_id},
        ).get("issue")
        if not issue:
            raise ValueError(f"Linear issue not found: {linear_issue_id}")

        next_description = _mission_binding_description(mission_id, issue.get("description") or "")
        client.query(
            """
            mutation($id: String!, $description: String!) {
              issueUpdate(id: $id, input: { description: $description }) {
                success
                issue { id identifier title url description }
              }
            }
            """,
            {"id": issue["id"], "description": next_description},
        )
        launch_meta = _write_launch_metadata(
            repo_root,
            mission_id,
            {
                "linear_issue": {
                    "id": issue["id"],
                    "identifier": issue["identifier"],
                    "title": issue["title"],
                    "url": issue.get("url"),
                },
                "linear_team_key": team_key,
            },
        )
        return {
            "mission_id": mission_id,
            "linear_issue": launch_meta["linear_issue"],
            "launch": launch_meta,
        }
    finally:
        client.close()


def _launch_mission(repo_root: Path, mission_id: str) -> dict[str, Any]:
    readiness = _gather_launcher_readiness(repo_root)
    if not readiness.get("supervisor", {}).get("ready"):
        raise ValueError(
            "Supervisor not ready. Configure [supervisor] in spec-orch.toml before launching."
        )
    mgr = MissionLifecycleManager(repo_root)
    plan_path = repo_root / "docs" / "specs" / mission_id / "plan.json"
    if plan_path.exists():
        plan = load_plan(plan_path)
        issue_ids = [
            packet.linear_issue_id or packet.title
            for wave in plan.waves
            for packet in wave.work_packets
        ]
        mgr.plan_complete(mission_id, issue_ids)
        state = mgr.auto_advance(mission_id)
    else:
        mgr.begin_tracking(mission_id)
        state = mgr.auto_advance(mission_id)
    if state is None:
        get_state = getattr(mgr, "get_state", None)
        state = get_state(mission_id) if callable(get_state) else None
    if state is None:
        raise RuntimeError("Mission did not return lifecycle state")
    launch_meta = _write_launch_metadata(
        repo_root,
        mission_id,
        {
            "last_launch": {
                "state": state.to_dict(),
            }
        },
    )
    started_background = False
    if state.to_dict().get("phase") == "executing":
        started_background = _start_background_mission_runner(repo_root, mission_id)
        launch_meta = _write_launch_metadata(
            repo_root,
            mission_id,
            {
                "runner": {
                    "status": "running" if started_background else "already_running",
                }
            },
        )
    return {
        "mission_id": mission_id,
        "state": state.to_dict(),
        "launch": launch_meta,
        "background_runner_started": started_background,
    }


def _build_execution_lifecycle_manager(repo_root: Path) -> MissionLifecycleManager:
    from spec_orch.services.daemon import DaemonConfig, SpecOrchDaemon

    config = DaemonConfig.from_toml(repo_root / "spec-orch.toml")
    daemon = SpecOrchDaemon(config=config, repo_root=repo_root)
    return daemon._lifecycle_manager


def _run_mission_in_background(repo_root: Path, mission_id: str) -> None:
    try:
        mgr = _build_execution_lifecycle_manager(repo_root)
        state = mgr.auto_advance(mission_id)
        payload: dict[str, Any] = {
            "runner": {
                "status": "finished",
            }
        }
        if state is not None:
            payload["runner"]["state"] = state.to_dict()
        _write_launch_metadata(repo_root, mission_id, payload)
    except Exception as exc:
        _write_launch_metadata(
            repo_root,
            mission_id,
            {
                "runner": {
                    "status": "failed",
                    "error": str(exc),
                }
            },
        )
    finally:
        with _RUNNER_LOCK:
            _ACTIVE_RUNNERS.pop(mission_id, None)


def _start_background_mission_runner(repo_root: Path, mission_id: str) -> bool:
    with _RUNNER_LOCK:
        existing = _ACTIVE_RUNNERS.get(mission_id)
        if existing is not None and existing.is_alive():
            return False
        thread = threading.Thread(
            target=_run_mission_in_background,
            args=(repo_root, mission_id),
            name=f"spec-orch-mission-{mission_id}",
            daemon=True,
        )
        _ACTIVE_RUNNERS[mission_id] = thread
        thread.start()
        return True
