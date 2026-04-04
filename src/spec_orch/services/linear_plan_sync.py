from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from spec_orch.services.linear_mirror import (
    build_linear_mirror_document_from_workspace,
    merge_linear_mirror_section,
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
    mirror = build_linear_mirror_document_from_workspace(
        workspace,
        plan_summary=plan_sync["plan_summary"],
    )
    mirror["plan_sync"] = plan_sync
    next_action = _next_action_from_plan_state(str(plan_sync.get("plan_state", "")).strip())
    if next_action:
        mirror["next_action"] = next_action
    return mirror


def sync_linear_mission_mirrors(
    repo_root: Path,
    *,
    client: Any,
    mission_id: str | None = None,
) -> list[dict[str, str]]:
    specs_root = repo_root / "docs" / "specs"
    results: list[dict[str, str]] = []
    if not specs_root.exists():
        return results

    mission_dirs = [specs_root / mission_id] if mission_id else sorted(specs_root.iterdir())
    for mission_dir in mission_dirs:
        if not mission_dir.is_dir():
            continue
        current_mission_id = mission_dir.name
        launch = _read_json_dict(mission_dir / "operator" / "launch.json")
        linear_issue = launch.get("linear_issue", {})
        if not isinstance(linear_issue, dict):
            continue
        linear_issue_id = str(linear_issue.get("id", "")).strip()
        linear_identifier = str(linear_issue.get("identifier", "")).strip()
        if not linear_issue_id:
            continue
        mirror = build_linear_mirror_for_mission(repo_root, current_mission_id)
        if mirror is None:
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
        description = merge_linear_mirror_section(str(issue.get("description") or ""), mirror)
        client.update_issue_description(linear_issue_id, description=description)
        results.append(
            {
                "mission_id": current_mission_id,
                "linear_issue_id": linear_issue_id,
                "linear_identifier": linear_identifier,
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


def _read_json_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}
