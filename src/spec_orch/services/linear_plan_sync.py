from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from spec_orch.services.linear_mirror import (
    build_linear_mirror_document_from_workspace,
    merge_linear_mirror_section,
    parse_linear_mirror_section,
)


def build_linear_plan_sync(repo_root: Path, mission_id: str) -> dict[str, Any]:
    plan = _read_json_dict(repo_root / "docs" / "specs" / mission_id / "plan.json")
    launch = _read_json_dict(repo_root / "docs" / "specs" / mission_id / "operator" / "launch.json")

    status = str(plan.get("status", "missing")).strip() or "missing"
    waves = plan.get("waves", [])
    safe_waves = [wave for wave in waves if isinstance(wave, dict)]
    packet_count = 0
    linked_packet_count = 0
    for wave in safe_waves:
        packets = wave.get("work_packets", [])
        safe_packets = [packet for packet in packets if isinstance(packet, dict)]
        packet_count += len(safe_packets)
        linked_packet_count += sum(
            1 for packet in safe_packets if str(packet.get("linear_issue_id") or "").strip()
        )

    current_focus = ""
    if safe_waves:
        first_wave = safe_waves[0]
        wave_number = first_wave.get("wave_number", 0)
        wave_description = str(first_wave.get("description", "")).strip()
        current_focus = (f"W{wave_number} - {wave_description}").strip()

    launcher_path = ""
    metadata = launch.get("metadata", {})
    if isinstance(metadata, dict):
        launcher_path = str(metadata.get("launcher_path", "")).strip()

    summary: list[str] = [
        f"Plan status: {status}.",
        (
            f"Waves: {len(safe_waves)}; packets: {packet_count}; "
            f"Linear-linked packets: {linked_packet_count}."
        ),
    ]
    if current_focus:
        summary.append(f"Current focus: {current_focus}.")
    if launcher_path:
        summary.append(f"Launcher path: {launcher_path}.")

    return {
        "mission_id": mission_id,
        "plan_id": str(plan.get("plan_id", "")).strip(),
        "plan_state": status,
        "wave_count": len(safe_waves),
        "packet_count": packet_count,
        "linked_packet_count": linked_packet_count,
        "current_focus": current_focus,
        "launcher_path": launcher_path,
        "plan_summary": summary,
    }


def build_linear_mirror_for_mission(repo_root: Path, mission_id: str) -> dict[str, Any] | None:
    workspace = _read_json_dict(
        repo_root / "docs" / "specs" / mission_id / "operator" / "intake_workspace.json"
    )
    if not workspace:
        return None
    plan_sync = build_linear_plan_sync(repo_root, mission_id)
    governance_sync = build_linear_governance_sync(repo_root, mission_id)
    mirror = build_linear_mirror_document_from_workspace(
        workspace,
        plan_summary=plan_sync["plan_summary"],
    )
    mirror["plan_sync"] = plan_sync
    mirror["governance_sync"] = governance_sync
    next_action = _next_action_from_plan_state(str(plan_sync.get("plan_state", "")).strip())
    if next_action:
        mirror["next_action"] = next_action
    return mirror


def build_linear_governance_sync(repo_root: Path, mission_id: str) -> dict[str, str]:
    acceptance_status = _read_json_dict(
        repo_root / ".spec_orch" / "acceptance" / "stability_acceptance_status.json"
    )
    acceptance_summary = acceptance_status.get("summary", {})
    safe_acceptance_summary = acceptance_summary if isinstance(acceptance_summary, dict) else {}

    acceptance_index = _read_json_dict(repo_root / "docs" / "acceptance-history" / "index.json")
    releases = acceptance_index.get("releases", [])
    safe_releases = [item for item in releases if isinstance(item, dict)]
    latest_release = safe_releases[-1] if safe_releases else {}

    launch = _read_json_dict(repo_root / "docs" / "specs" / mission_id / "operator" / "launch.json")
    metadata = launch.get("metadata", {})
    safe_metadata = metadata if isinstance(metadata, dict) else {}

    return {
        "latest_acceptance_status": str(safe_acceptance_summary.get("overall_status", "")).strip(),
        "latest_release_id": str(latest_release.get("release_id", "")).strip(),
        "latest_release_bundle_path": str(latest_release.get("bundle_path", "")).strip(),
        "next_bottleneck": str(
            safe_metadata.get("next_bottleneck", "") or safe_metadata.get("bottleneck", "")
        ).strip(),
    }


def sync_linear_mission_mirrors(
    repo_root: Path,
    *,
    client: Any,
    mission_id: str | None = None,
) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for item in collect_linear_mission_mirror_drifts(
        repo_root,
        client=client,
        mission_id=mission_id,
    ):
        mission_mirror = item.get("desired_mirror")
        if not isinstance(mission_mirror, dict):
            continue
        linear_issue_id = str(item.get("linear_issue_id", "")).strip()
        if not linear_issue_id:
            continue
        current_description = str(item.get("current_description", "") or "")
        description = merge_linear_mirror_section(current_description, mission_mirror)
        client.update_issue_description(linear_issue_id, description=description)
        results.append(
            {
                "mission_id": str(item.get("mission_id", "")).strip(),
                "linear_issue_id": linear_issue_id,
                "linear_identifier": str(item.get("linear_identifier", "")).strip(),
            }
        )
    return results


def collect_linear_mission_mirror_drifts(
    repo_root: Path,
    *,
    client: Any,
    mission_id: str | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for current_mission_id, linear_issue_id, linear_identifier in _iter_bound_linear_missions(
        repo_root, mission_id
    ):
        desired_mirror = build_linear_mirror_for_mission(repo_root, current_mission_id)
        if desired_mirror is None:
            continue
        issue = client.query(
            """
            query($id: String!) {
              issue(id: $id) { id description }
            }
            """,
            {"id": linear_issue_id},
        ).get("issue")
        if not isinstance(issue, dict):
            continue
        current_description = str(issue.get("description") or "")
        current_mirror = parse_linear_mirror_section(current_description)
        status, reasons = _classify_mirror_drift(desired_mirror, current_mirror)
        results.append(
            {
                "mission_id": current_mission_id,
                "linear_issue_id": linear_issue_id,
                "linear_identifier": linear_identifier,
                "status": status,
                "reasons": reasons,
                "desired_mirror": desired_mirror,
                "current_description": current_description,
            }
        )
    return results


def _next_action_from_plan_state(plan_state: str) -> str:
    normalized = plan_state.strip().lower()
    if normalized == "draft":
        return "review_plan"
    if normalized == "approved":
        return "launch_mission"
    if normalized == "executing":
        return "track_execution"
    if normalized == "completed":
        return "review_execution"
    return ""


def _iter_bound_linear_missions(
    repo_root: Path,
    mission_id: str | None,
) -> list[tuple[str, str, str]]:
    specs_root = repo_root / "docs" / "specs"
    if not specs_root.exists():
        return []
    mission_dirs = [specs_root / mission_id] if mission_id else sorted(specs_root.iterdir())
    bound: list[tuple[str, str, str]] = []
    for mission_dir in mission_dirs:
        if not mission_dir.is_dir():
            continue
        launch = _read_json_dict(mission_dir / "operator" / "launch.json")
        linear_issue = launch.get("linear_issue", {})
        if not isinstance(linear_issue, dict):
            continue
        linear_issue_id = str(linear_issue.get("id", "")).strip()
        linear_identifier = str(linear_issue.get("identifier", "")).strip()
        if not linear_issue_id:
            continue
        bound.append((mission_dir.name, linear_issue_id, linear_identifier))
    return bound


def _classify_mirror_drift(
    desired_mirror: dict[str, Any],
    current_mirror: dict[str, Any] | None,
) -> tuple[str, list[str]]:
    if current_mirror is None:
        return ("missing_mirror", ["mirror block missing from Linear description"])

    reasons: list[str] = []
    desired_workspace_id = str(desired_mirror.get("workspace_id", "")).strip()
    current_workspace_id = str(current_mirror.get("workspace_id", "")).strip()
    if desired_workspace_id != current_workspace_id:
        reasons.append("workspace_id differs")

    desired_plan = desired_mirror.get("plan_sync", {})
    current_plan = current_mirror.get("plan_sync", {})
    safe_desired_plan = desired_plan if isinstance(desired_plan, dict) else {}
    safe_current_plan = current_plan if isinstance(current_plan, dict) else {}
    for key in (
        "plan_state",
        "current_focus",
        "wave_count",
        "packet_count",
        "linked_packet_count",
        "launcher_path",
    ):
        if safe_desired_plan.get(key) != safe_current_plan.get(key):
            reasons.append(f"plan_sync.{key} differs")

    if not reasons:
        return ("already_synced", [])
    if any(reason.startswith("workspace_id") for reason in reasons):
        return ("workspace_mismatch", reasons)
    return ("stale_plan_sync", reasons)


def _read_json_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}
