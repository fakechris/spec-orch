from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from spec_orch.services.execution_workbench import build_mission_execution_workbench
from spec_orch.services.judgment_workbench import build_mission_judgment_workbench
from spec_orch.services.learning_workbench import build_mission_learning_workbench


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _load_release_index(repo_root: Path) -> list[dict[str, Any]]:
    payload = _load_json(repo_root / "docs" / "acceptance-history" / "index.json")
    if payload is None:
        return []
    releases = payload.get("releases", [])
    if not isinstance(releases, list):
        return []
    return [item for item in releases if isinstance(item, dict)]


def _bundle_dir(repo_root: Path, release: dict[str, Any]) -> Path | None:
    bundle_path = str(release.get("bundle_path", "")).strip()
    if not bundle_path:
        return None
    path = repo_root / bundle_path
    return path if path.exists() else None


def _release_timeline(repo_root: Path, releases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    timeline: list[dict[str, Any]] = []
    for release in releases:
        bundle_dir = _bundle_dir(repo_root, release)
        bundle_path = str(release.get("bundle_path", "")).strip()
        summary_artifact_path = f"{bundle_path}/summary.md" if bundle_path else ""
        status_artifact_path = f"{bundle_path}/status.json" if bundle_path else ""
        source_runs_artifact_path = f"{bundle_path}/source_runs.json" if bundle_path else ""
        artifacts_artifact_path = f"{bundle_path}/artifacts.json" if bundle_path else ""
        findings_artifact_path = f"{bundle_path}/findings.json" if bundle_path else ""
        findings_payload = (
            _load_json(bundle_dir / "findings.json") if bundle_dir is not None else None
        )
        findings = (
            findings_payload.get("findings", []) if isinstance(findings_payload, dict) else []
        )
        timeline.append(
            {
                "release_id": str(release.get("release_id", "")),
                "release_label": str(release.get("release_label", "")),
                "created_at": str(release.get("created_at", "")),
                "git_commit": str(release.get("git_commit", "")),
                "overall_status": str(release.get("overall_status", "")),
                "findings_count": int(release.get("findings_count", 0) or len(findings)),
                "issue_proposal_count": int(release.get("issue_proposal_count", 0) or 0),
                "bundle_path": bundle_path,
                "summary_artifact_path": summary_artifact_path,
                "status_artifact_path": status_artifact_path,
                "source_runs_artifact_path": source_runs_artifact_path,
                "artifacts_artifact_path": artifacts_artifact_path,
                "findings_artifact_path": findings_artifact_path,
            }
        )
    timeline.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
    return timeline


def _workspace_narrative(
    execution: dict[str, Any],
    judgment: dict[str, Any],
    learning: dict[str, Any],
) -> str:
    execution_overview = execution.get("overview", {})
    judgment_overview = judgment.get("overview", {})
    learning_overview = learning.get("overview", {})
    parts = []
    execution_reason = str(execution_overview.get("last_event_summary", "")).strip()
    execution_phase = str(execution_overview.get("current_phase", "")).strip()
    if execution_phase or execution_reason:
        parts.append(
            "Execution "
            + " ".join(token for token in [execution_phase, execution_reason] if token).strip()
        )
    evidence_summary = str(judgment_overview.get("evidence_summary", "")).strip()
    recommended_next_step = str(judgment_overview.get("recommended_next_step", "")).strip()
    if evidence_summary or recommended_next_step:
        parts.append("Judgment " + (evidence_summary or recommended_next_step))
    learning_summary = str(learning_overview.get("last_learning_summary", "")).strip()
    if learning_summary:
        parts.append("Learning " + learning_summary)
    return ". ".join(part.rstrip(".") for part in parts if part).strip()


def _workspace_storylines(repo_root: Path) -> list[dict[str, Any]]:
    storylines: list[dict[str, Any]] = []
    specs_root = repo_root / "docs" / "specs"
    if not specs_root.exists():
        return storylines
    for mission_root in sorted(specs_root.glob("*")):
        if not mission_root.is_dir():
            continue
        mission_payload = _load_json(mission_root / "mission.json")
        if mission_payload is None:
            continue
        mission_id = str(mission_payload.get("mission_id", mission_root.name))
        execution = build_mission_execution_workbench(repo_root, mission_id, [])
        judgment = build_mission_judgment_workbench(repo_root, mission_id)
        learning = build_mission_learning_workbench(repo_root, mission_id)
        storylines.append(
            {
                "workspace_id": mission_id,
                "title": str(mission_payload.get("title", mission_id)),
                "status": str(mission_payload.get("status", "")),
                "narrative": _workspace_narrative(execution, judgment, learning),
                "execution_summary": {
                    "current_phase": str(execution.get("overview", {}).get("current_phase", "")),
                    "last_event_summary": str(
                        execution.get("overview", {}).get("last_event_summary", "")
                    ),
                },
                "judgment_summary": {
                    "judgment_class": str(judgment.get("overview", {}).get("judgment_class", "")),
                    "candidate_finding_count": int(
                        judgment.get("overview", {}).get("candidate_finding_count", 0) or 0
                    ),
                },
                "learning_summary": {
                    "promoted_finding_count": int(
                        learning.get("overview", {}).get("promoted_finding_count", 0) or 0
                    ),
                    "last_learning_summary": str(
                        learning.get("overview", {}).get("last_learning_summary", "")
                    ),
                },
                "routes": {
                    "overview": f"/?mission={mission_id}&mode=missions&tab=overview",
                    "execution": f"/?mission={mission_id}&mode=missions&tab=execution",
                    "judgment": f"/?mission={mission_id}&mode=missions&tab=judgment",
                    "learning": f"/?mission={mission_id}&mode=missions&tab=learning",
                },
            }
        )
    storylines.sort(key=lambda item: str(item.get("workspace_id", "")))
    return storylines


def _highlights(
    release_timeline: list[dict[str, Any]],
    storylines: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    highlights: list[dict[str, Any]] = []
    if release_timeline:
        latest = release_timeline[0]
        highlights.append(
            {
                "kind": "release",
                "title": str(latest.get("release_label", "")),
                "summary": (
                    f"{latest.get('overall_status', 'unknown')} · "
                    f"{latest.get('findings_count', 0)} findings · "
                    f"{latest.get('issue_proposal_count', 0)} proposals"
                ),
                "route": f"/artifacts/{latest.get('summary_artifact_path', '')}",
            }
        )
    if storylines:
        workspace = storylines[0]
        highlights.append(
            {
                "kind": "workspace",
                "title": str(workspace.get("title", workspace.get("workspace_id", ""))),
                "summary": str(workspace.get("narrative", "")),
                "route": str(workspace.get("routes", {}).get("judgment", "")),
            }
        )
    return highlights


def build_showcase_workbench(repo_root: Path) -> dict[str, Any]:
    releases = _load_release_index(repo_root)
    release_timeline = _release_timeline(repo_root, releases)
    storylines = _workspace_storylines(repo_root)
    highlights = _highlights(release_timeline, storylines)
    return {
        "summary": {
            "release_count": len(release_timeline),
            "passing_release_count": sum(
                1 for item in release_timeline if str(item.get("overall_status", "")) == "pass"
            ),
            "workspace_story_count": len(storylines),
            "highlight_count": len(highlights),
        },
        "release_timeline": release_timeline,
        "workspace_storylines": storylines,
        "highlights": highlights,
        "review_route": "/?mode=showcase",
    }


__all__ = ["build_showcase_workbench"]
