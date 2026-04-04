from __future__ import annotations

import importlib.util
import json
import threading
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from spec_orch.acceptance_core.calibration import dashboard_surface_pack_v1
from spec_orch.acceptance_core.routing import AcceptanceSurfacePackRef
from spec_orch.services.canonical_issue import canonical_issue_from_dashboard_payload
from spec_orch.services.fresh_verification import build_fresh_verification_commands
from spec_orch.services.intake_handoff import build_workspace_handoff
from spec_orch.services.lifecycle_manager import MissionLifecycleManager
from spec_orch.services.linear_client import LinearClient, resolve_linear_token
from spec_orch.services.linear_intake import (
    LinearAcceptanceDraft,
    LinearIntakeDocument,
    derive_linear_intake_state,
    has_blocking_open_questions,
)
from spec_orch.services.linear_mirror import merge_linear_mirror_section
from spec_orch.services.linear_plan_sync import build_linear_mirror_for_mission
from spec_orch.services.litellm_profile import resolve_role_litellm_settings
from spec_orch.services.mission_service import MissionService
from spec_orch.services.promotion_service import load_plan
from spec_orch.services.resource_loader import load_json_resource
from spec_orch.services.round_orchestrator import build_fresh_acpx_post_run_campaign

_RUNNER_LOCK = threading.Lock()
_ACTIVE_RUNNERS: dict[str, threading.Thread] = {}
_LAUNCH_META_LOCK = threading.Lock()
_FRESH_ACPX_VARIANT_RESOURCES: dict[str, dict[str, Any]] = {
    "default": {
        "resource_name": "fresh_acpx_mission_request.json",
        "launcher_path": "approve_plan_launch",
        "requires_linear": False,
    },
    "multi_packet": {
        "resource_name": "fresh_acpx_mission_request_multi_packet.json",
        "launcher_path": "approve_plan_launch",
        "requires_linear": False,
    },
    "linear_bound": {
        "resource_name": "fresh_acpx_mission_request_linear_bound.json",
        "launcher_path": "create_linear_issue_then_launch",
        "requires_linear": True,
    },
}


def _fresh_acpx_acceptance_surface_pack_ref(mission_id: str) -> AcceptanceSurfacePackRef:
    pack = dashboard_surface_pack_v1(mission_id)
    return AcceptanceSurfacePackRef(
        pack_key=pack.pack_key,
        subject_kind=pack.subject_kind,
        subject_id=pack.subject_id,
    )


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


def _intake_workspace_path(repo_root: Path, mission_id: str) -> Path:
    return _operator_dir(repo_root, mission_id) / "intake_workspace.json"


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
    with _LAUNCH_META_LOCK:
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


def _normalize_lines(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    return [str(item).strip() for item in items if str(item).strip()]


def _dashboard_intake_document_from_payload(payload: dict[str, Any]) -> LinearIntakeDocument:
    evidence_expectations = _normalize_lines(payload.get("evidence_expectations", []))
    verification_expectations = _normalize_lines(payload.get("verification_expectations", []))
    if not verification_expectations:
        verification_expectations = list(evidence_expectations)
    return LinearIntakeDocument(
        problem=str(payload.get("problem", "")).strip(),
        goal=str(payload.get("goal", "")).strip(),
        constraints=_normalize_lines(payload.get("constraints", [])),
        acceptance=LinearAcceptanceDraft(
            success_conditions=_normalize_lines(payload.get("acceptance_criteria", [])),
            verification_expectations=verification_expectations,
        ),
        evidence_expectations=evidence_expectations,
        open_questions=_normalize_lines(payload.get("open_questions", [])),
        current_system_understanding=str(payload.get("current_system_understanding", "")).strip(),
    )


def _dashboard_intake_missing_fields(document: LinearIntakeDocument) -> list[str]:
    missing: list[str] = []
    if not document.problem.strip():
        missing.append("problem")
    if not document.goal.strip():
        missing.append("goal")
    if not document.acceptance.success_conditions:
        missing.append("acceptance")
    if not document.acceptance.verification_expectations:
        missing.append("verification_expectations")
    return missing


def _handoff_state_for_dashboard_intake(document: LinearIntakeDocument) -> str:
    state = derive_linear_intake_state(document)
    if state.value in {"ready_for_workspace", "workspace_created"}:
        return state.value
    if document.problem.strip() and document.goal.strip():
        return "canonicalized"
    return "draft_only"


def _build_dashboard_intake_workspace(
    repo_root: Path,
    *,
    mission_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    document = _dashboard_intake_document_from_payload(payload)
    state = derive_linear_intake_state(document)
    missing_fields = _dashboard_intake_missing_fields(document)
    blocking_questions = [
        item for item in document.open_questions if item.strip().lower().startswith("[blocking]")
    ]
    is_ready = not missing_fields and not has_blocking_open_questions(document)
    handoff_state = _handoff_state_for_dashboard_intake(document)
    if is_ready:
        recommendation = "create_workspace"
    elif document.problem.strip() and document.goal.strip():
        recommendation = "write_back_to_linear"
    else:
        recommendation = "stay_in_intake"
    title = str(payload.get("title", "")).strip() or mission_id
    canonical_issue = canonical_issue_from_dashboard_payload(
        issue_id=mission_id,
        title=title,
        payload=payload,
    )
    handoff = build_workspace_handoff(canonical_issue, subject_kind="mission")
    return {
        "mission_id": mission_id,
        "origin": "dashboard",
        "state": state.value,
        "draft": {
            "title": title,
            "intent": str(payload.get("intent", "")).strip(),
            "problem": document.problem,
            "goal": document.goal,
            "constraints": list(document.constraints),
            "acceptance": {
                "success_conditions": list(document.acceptance.success_conditions),
                "verification_expectations": list(document.acceptance.verification_expectations),
            },
            "evidence_expectations": list(document.evidence_expectations),
            "open_questions": list(document.open_questions),
            "current_system_understanding": document.current_system_understanding,
        },
        "readiness": {
            "is_ready": is_ready,
            "missing_fields": missing_fields,
            "blocking_open_questions": blocking_questions,
            "recommendation": recommendation,
        },
        "canonical_issue": canonical_issue.to_dict(),
        "handoff": {
            **handoff,
            "state": handoff_state,
            "next_action": recommendation,
        },
    }


def _persist_dashboard_intake_workspace(
    repo_root: Path,
    *,
    mission_id: str,
    workspace: dict[str, Any],
) -> dict[str, Any]:
    _intake_workspace_path(repo_root, mission_id).write_text(
        json.dumps(workspace, indent=2) + "\n",
        encoding="utf-8",
    )
    return workspace


def _load_dashboard_intake_workspace(repo_root: Path, mission_id: str) -> dict[str, Any] | None:
    path = _intake_workspace_path(repo_root, mission_id)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _preview_dashboard_intake_workspace(repo_root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    raw_mission_id = payload.get("mission_id")
    mission_id = raw_mission_id.strip() if isinstance(raw_mission_id, str) else ""
    mission_id = mission_id or "draft-preview"
    return _build_dashboard_intake_workspace(
        repo_root,
        mission_id=mission_id,
        payload=payload,
    )


def _load_launcher_fixture(repo_root: Path, fixture_name: str) -> dict[str, Any]:
    return load_json_resource(resource_name=fixture_name, repo_root=repo_root)


def _resolve_fresh_acpx_variant(variant: str) -> dict[str, Any]:
    key = str(variant).strip().lower() or "default"
    if key not in _FRESH_ACPX_VARIANT_RESOURCES:
        raise ValueError(f"Unsupported fresh ACPX variant: {variant}")
    return {"variant": key, **_FRESH_ACPX_VARIANT_RESOURCES[key]}


def _is_fresh_acpx_mission(repo_root: Path, mission_id: str) -> bool:
    bootstrap_path = (
        repo_root / "docs" / "specs" / mission_id / "operator" / "mission_bootstrap.json"
    )
    if bootstrap_path.exists():
        try:
            payload = json.loads(bootstrap_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        if isinstance(payload, dict):
            if payload.get("execution_mode") == "fresh_acpx_mission":
                return True
            metadata = payload.get("metadata", {})
            if isinstance(metadata, dict) and metadata.get("fresh") is True:
                return True
    return mission_id.startswith("fresh-acpx-")


def _inject_fresh_plan_verification_commands(plan: dict[str, Any]) -> bool:
    changed = False
    for wave in plan.get("waves", []):
        if not isinstance(wave, dict):
            continue
        for packet in wave.get("work_packets", []):
            if not isinstance(packet, dict):
                continue
            current = packet.get("verification_commands", {})
            if isinstance(current, dict) and current:
                continue
            generated = build_fresh_verification_commands(list(packet.get("files_in_scope", [])))
            if generated:
                packet["verification_commands"] = generated
                changed = True
    return changed


def _merge_isolated_fresh_verification_packets(plan: dict[str, Any]) -> bool:
    changed = False
    for wave in plan.get("waves", []):
        if not isinstance(wave, dict):
            continue
        work_packets = wave.get("work_packets", [])
        if not isinstance(work_packets, list) or len(work_packets) < 2:
            continue
        normalized_packets: list[dict[str, Any]] = []
        for packet in work_packets:
            if not isinstance(packet, dict):
                normalized_packets.append(packet)
                continue
            if normalized_packets:
                previous = normalized_packets[-1]
                packet_files = list(packet.get("files_in_scope", []))
                previous_files = list(previous.get("files_in_scope", []))
                builder_prompt = str(packet.get("builder_prompt", ""))
                title = str(packet.get("title", "")).lower()
                verify_signals = (
                    "tsc" in builder_prompt.lower()
                    or "eslint" in builder_prompt.lower()
                    or "typecheck" in builder_prompt.lower()
                    or "lint" in builder_prompt.lower()
                    or "verify" in title
                    or bool(packet.get("depends_on"))
                )
                if (
                    packet_files
                    and previous_files
                    and set(packet_files).issubset(set(previous_files))
                    and verify_signals
                ):
                    previous_criteria = previous.setdefault("acceptance_criteria", [])
                    if isinstance(previous_criteria, list):
                        for item in packet.get("acceptance_criteria", []):
                            if item not in previous_criteria:
                                previous_criteria.append(item)
                    previous_commands = previous.setdefault("verification_commands", {})
                    if isinstance(previous_commands, dict):
                        for key, value in packet.get("verification_commands", {}).items():
                            previous_commands.setdefault(key, value)
                    changed = True
                    continue
            normalized_packets.append(packet)
        wave["work_packets"] = normalized_packets
    return changed


def _build_fresh_acpx_mission_request(
    repo_root: Path,
    *,
    variant: str = "default",
) -> dict[str, Any]:
    variant_config = _resolve_fresh_acpx_variant(variant)
    payload = _load_launcher_fixture(repo_root, str(variant_config["resource_name"]))
    mission_id_prefix = (
        str(payload.get("mission_id_prefix", "fresh-acpx-")).strip() or "fresh-acpx-"
    )
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    mission_id = f"{mission_id_prefix}{timestamp}-{uuid4().hex[:6]}"
    metadata = dict(payload.get("metadata", {}))
    metadata.update(
        {
            "fresh": True,
            "generated_at": datetime.now(UTC).isoformat(),
            "mission_id_prefix": mission_id_prefix,
            "fresh_variant": variant_config["variant"],
            "launcher_path": variant_config["launcher_path"],
            "requires_linear": bool(variant_config["requires_linear"]),
        }
    )
    campaign = build_fresh_acpx_post_run_campaign(repo_root, mission_id)
    return {
        "mission_id": mission_id,
        "title": str(payload.get("title", "Fresh ACPX Mission E2E Smoke")).strip()
        or "Fresh ACPX Mission E2E Smoke",
        "execution_mode": str(payload.get("execution_mode", "fresh_acpx_mission")).strip()
        or "fresh_acpx_mission",
        "local_only": bool(payload.get("local_only", True)),
        "safe_cleanup": bool(payload.get("safe_cleanup", True)),
        "intent": str(payload.get("intent", "Validate a brand-new ACPX mission path.")).strip()
        or "Validate a brand-new ACPX mission path.",
        "acceptance_criteria": list(payload.get("acceptance_criteria", [])),
        "constraints": list(payload.get("constraints", [])),
        "metadata": metadata,
        "post_run_campaign": campaign.to_dict(),
    }


def _gather_launcher_readiness(repo_root: Path) -> dict[str, Any]:
    raw = _load_raw_config(repo_root)
    planner_cfg = raw.get("planner", {}) if isinstance(raw.get("planner", {}), dict) else {}
    supervisor_cfg = (
        raw.get("supervisor", {}) if isinstance(raw.get("supervisor", {}), dict) else {}
    )
    builder_cfg = raw.get("builder", {}) if isinstance(raw.get("builder", {}), dict) else {}
    token_env, _team_key = _get_linear_settings(repo_root)
    valid_api_types = {"anthropic", "openai"}

    planner_settings = resolve_role_litellm_settings(
        raw,
        section_name="planner",
        default_model=str(planner_cfg.get("model", "")),
        default_api_type=str(planner_cfg.get("api_type", "anthropic")),
    )
    planner_api_type = str(planner_settings.get("api_type", "anthropic")).strip().lower()
    planner_api_type_valid = planner_api_type in valid_api_types
    planner_key = str(planner_settings.get("api_key") or "")
    planner_base = str(planner_settings.get("api_base") or "")

    supervisor_settings = resolve_role_litellm_settings(
        raw,
        section_name="supervisor",
        default_model=str(supervisor_cfg.get("model", "")),
        default_api_type=str(supervisor_cfg.get("api_type", "anthropic")),
    )
    supervisor_api_type = str(supervisor_settings.get("api_type", "anthropic")).strip().lower()
    supervisor_api_type_valid = supervisor_api_type in valid_api_types
    supervisor_key = str(supervisor_settings.get("api_key") or "")
    supervisor_base = str(supervisor_settings.get("api_base") or "")
    try:
        supervisor_max_rounds = int(supervisor_cfg.get("max_rounds", 0))
    except (TypeError, ValueError):
        supervisor_max_rounds = 0

    dashboard_deps = all(
        importlib.util.find_spec(module) is not None
        for module in ("fastapi", "uvicorn", "websockets")
    )

    return {
        "config_present": (repo_root / "spec-orch.toml").exists(),
        "dashboard": {"ready": dashboard_deps},
        "linear": {
            "ready": bool(resolve_linear_token(token_env=token_env)),
            "token_env": token_env,
        },
        "planner": {
            "ready": (
                planner_api_type_valid
                and bool(planner_settings.get("model"))
                and bool(planner_key)
                and bool(planner_base)
            ),
            "model": planner_settings.get("model"),
            "api_type": planner_api_type,
            "error": "" if planner_api_type_valid else "invalid api_type",
        },
        "supervisor": {
            "ready": (
                supervisor_api_type_valid
                and bool(supervisor_cfg.get("adapter"))
                and bool(supervisor_settings.get("model"))
                and bool(supervisor_key)
                and bool(supervisor_base)
                and 0 < supervisor_max_rounds <= 1000
            ),
            "model": supervisor_settings.get("model"),
            "api_type": supervisor_api_type,
            "error": "" if supervisor_api_type_valid else "invalid api_type",
        },
        "builder": {
            "ready": bool(builder_cfg.get("adapter")),
            "adapter": builder_cfg.get("adapter"),
        },
    }


def _create_mission_draft(repo_root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    raw_title = payload.get("title")
    title = raw_title.strip() if isinstance(raw_title, str) else ""
    if not title:
        raise ValueError("Mission title is required")
    raw_mission_id = payload.get("mission_id")
    mission_id_text = raw_mission_id.strip() if isinstance(raw_mission_id, str) else ""
    mission_id: str | None = mission_id_text or None
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
    intake_workspace = _persist_dashboard_intake_workspace(
        repo_root,
        mission_id=mission.mission_id,
        workspace=_build_dashboard_intake_workspace(
            repo_root,
            mission_id=mission.mission_id,
            payload=payload,
        ),
    )
    return {
        "mission_id": mission.mission_id,
        "title": mission.title,
        "status": mission.status.value,
        "spec_path": mission.spec_path,
        "intake_workspace": intake_workspace,
    }


def _generate_plan_for_mission(repo_root: Path, mission_id: str) -> dict[str, Any]:
    # Reuse the existing lifecycle planning implementation instead of shelling out to CLI.
    mgr = MissionLifecycleManager(repo_root)
    return mgr._run_plan(mission_id)


def _approve_and_plan_mission(repo_root: Path, mission_id: str) -> dict[str, Any]:
    svc = MissionService(repo_root)
    mission = svc.approve_mission(mission_id)
    plan = _generate_plan_for_mission(repo_root, mission_id)
    if _is_fresh_acpx_mission(repo_root, mission_id):
        changed = _inject_fresh_plan_verification_commands(plan)
        changed = _merge_isolated_fresh_verification_packets(plan) or changed
        if changed:
            (repo_root / "docs" / "specs" / mission_id / "plan.json").write_text(
                json.dumps(plan, indent=2) + "\n",
                encoding="utf-8",
            )
    try:
        _sync_linked_linear_issue_mirror(repo_root, mission_id)
    except Exception as exc:
        print(f"[launcher] {mission_id}: mirror sync skipped: {exc}")
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


def _description_with_linear_mirror(repo_root: Path, mission_id: str, description: str) -> str:
    bound = _mission_binding_description(mission_id, description)
    mirror = build_linear_mirror_for_mission(repo_root, mission_id)
    if not isinstance(mirror, dict):
        return bound
    return merge_linear_mirror_section(bound, mirror)


def _sync_linked_linear_issue_mirror(repo_root: Path, mission_id: str) -> None:
    launch_meta = _read_launch_metadata(repo_root, mission_id)
    linear_issue = launch_meta.get("linear_issue", {})
    if not isinstance(linear_issue, dict):
        return
    linear_issue_id = str(linear_issue.get("id", "")).strip()
    if not linear_issue_id:
        return
    token_env, _team_key = _get_linear_settings(repo_root)
    client = LinearClient(token_env=token_env)
    try:
        issue = client.query(
            """
            query($id: String!) {
              issue(id: $id) { id description }
            }
            """,
            {"id": linear_issue_id},
        ).get("issue")
        if not isinstance(issue, dict):
            return
        next_description = _description_with_linear_mirror(
            repo_root,
            mission_id,
            str(issue.get("description") or ""),
        )
        client.update_issue_description(linear_issue_id, description=next_description)
    finally:
        client.close()


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
        team_nodes = (
            client.query(
                """
            query($key: String!) {
              teams(filter: { key: { eq: $key } }) { nodes { id key name } }
            }
            """,
                {"key": team_key},
            )
            .get("teams", {})
            .get("nodes", [])
        )
        if not team_nodes:
            raise ValueError(f"Linear team not found for configured key: {team_key}")
        team = team_nodes[0]
        response = client.query(
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
                "description": _description_with_linear_mirror(repo_root, mission_id, description),
            },
        )
        issue_create = response.get("issueCreate") if isinstance(response, dict) else None
        issue_payload = issue_create if isinstance(issue_create, dict) else None
        payload = issue_payload.get("issue") if issue_payload else None
        if (
            not issue_payload
            or issue_payload.get("success") is not True
            or not isinstance(payload, dict)
        ):
            raise ValueError(f"Linear issue creation failed: {response!r}")
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

        next_description = _description_with_linear_mirror(
            repo_root,
            mission_id,
            issue.get("description") or "",
        )
        update_response = client.query(
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
        issue_update = (
            update_response.get("issueUpdate") if isinstance(update_response, dict) else None
        )
        if not isinstance(issue_update, dict) or issue_update.get("success") is not True:
            raise ValueError(f"Linear issue description update failed: {update_response!r}")
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


def _launch_mission(
    repo_root: Path,
    mission_id: str,
    *,
    allow_background_runner: bool = True,
) -> dict[str, Any]:
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
        if _daemon_is_active(repo_root):
            runner_status = "daemon_running"
        elif not allow_background_runner:
            runner_status = "foreground_required"
        else:
            started_background = _start_background_mission_runner(repo_root, mission_id)
            runner_status = "running" if started_background else "already_running"
        launch_meta = _write_launch_metadata(
            repo_root,
            mission_id,
            {
                "runner": {
                    "status": runner_status,
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


def _daemon_is_active(repo_root: Path) -> bool:
    from spec_orch.services.daemon import DaemonConfig, SpecOrchDaemon

    config = DaemonConfig.from_toml(repo_root / "spec-orch.toml")
    heartbeat = SpecOrchDaemon.read_heartbeat(repo_root, lockfile_dir=config.lockfile_dir)
    return str(heartbeat.get("status") or "") in {"starting", "healthy", "degraded"}


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
