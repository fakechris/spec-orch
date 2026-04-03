from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from spec_orch.services.execution_workbench import build_mission_execution_workbench
from spec_orch.services.judgment_workbench import build_mission_judgment_workbench
from spec_orch.services.learning_workbench import build_mission_learning_workbench

_SOURCE_RUN_ORDER = {
    "issue_start": 0,
    "dashboard_ui": 1,
    "mission_start": 2,
    "exploratory": 3,
}


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


def _source_run_identity(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    for key in ("report_path", "round_dir", "run_id", "mission_id", "issue_id"):
        value = str(item.get(key, "")).strip()
        if value:
            return value
    return ""


def _compare_source_runs(
    current_runs: dict[str, Any],
    previous_runs: dict[str, Any],
) -> tuple[dict[str, dict[str, str]], str, dict[str, int], list[str]]:
    compare: dict[str, dict[str, str]] = {}
    summary_parts: list[str] = []
    counts = {"advanced": 0, "stayed": 0, "new": 0, "missing": 0}
    focus: list[str] = []
    all_keys = sorted(
        set(current_runs) | set(previous_runs),
        key=lambda key: (_SOURCE_RUN_ORDER.get(key, 99), key),
    )
    for key in all_keys:
        current_id = _source_run_identity(current_runs.get(key))
        previous_id = _source_run_identity(previous_runs.get(key))
        if current_id and previous_id:
            status = "stayed" if current_id == previous_id else "advanced"
        elif current_id:
            status = "new"
        elif previous_id:
            status = "missing"
        else:
            continue
        compare[key] = {
            "status": status,
            "current": current_id,
            "previous": previous_id,
        }
        counts[status] = counts.get(status, 0) + 1
        if status != "stayed":
            label = f"{key} {status}"
            summary_parts.append(label)
            focus.append(label)
    if not compare:
        summary = "no source runs recorded"
    else:
        summary = "; ".join(summary_parts) if summary_parts else "all source runs stayed"
    return compare, summary, counts, focus


def _storyline_headline(item: dict[str, Any]) -> str:
    workspace_count = len(item.get("workspace_ids", []))
    workspace_label = (
        "1 linked workspace" if workspace_count == 1 else f"{workspace_count} linked workspaces"
    )
    compare_focus = [entry for entry in item.get("compare_focus", []) if isinstance(entry, str)]
    if compare_focus:
        return "; ".join([workspace_label, *compare_focus])
    return workspace_label


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
        manifest_payload = (
            _load_json(bundle_dir / "manifest.json") if bundle_dir is not None else None
        )
        source_runs_payload = (
            _load_json(bundle_dir / "source_runs.json") if bundle_dir is not None else None
        )
        findings = (
            findings_payload.get("findings", []) if isinstance(findings_payload, dict) else []
        )
        source_runs = source_runs_payload if isinstance(source_runs_payload, dict) else {}
        workspace_ids = sorted(
            {
                str(item.get("mission_id", "")).strip()
                for item in source_runs.values()
                if isinstance(item, dict) and str(item.get("mission_id", "")).strip()
            }
        )
        lineage_payload = (
            manifest_payload.get("lineage", {}) if isinstance(manifest_payload, dict) else {}
        )
        if not isinstance(lineage_payload, dict):
            lineage_payload = {}
        lineage_notes = lineage_payload.get("notes", [])
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
                "workspace_ids": workspace_ids,
                "lineage_notes": [item for item in lineage_notes if isinstance(item, str)],
                "_source_runs": source_runs,
            }
        )
    timeline.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
    for index, item in enumerate(timeline):
        previous = timeline[index + 1] if index + 1 < len(timeline) else None
        previous_runs = previous.get("_source_runs", {}) if isinstance(previous, dict) else {}
        compare, compare_summary, compare_counts, compare_focus = _compare_source_runs(
            item.get("_source_runs", {}), previous_runs if isinstance(previous_runs, dict) else {}
        )
        item["compare_target_release_id"] = (
            str(previous.get("release_id", "")) if isinstance(previous, dict) else ""
        )
        item["source_run_compare"] = compare
        item["compare_counts"] = compare_counts
        item["compare_focus"] = compare_focus
        item["source_run_compare_summary"] = compare_summary
        item["storyline_headline"] = _storyline_headline(item)
    for item in timeline:
        item.pop("_source_runs", None)
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


def _turning_points(
    *,
    structural_signal: str,
    compare_summary: str,
    learning_decision: str,
) -> list[dict[str, str]]:
    points: list[dict[str, str]] = []
    if structural_signal and structural_signal not in {"stable", "healthy", "pass"}:
        summary = (
            "Structural regression remained visible."
            if structural_signal == "regression"
            else f"Structural {structural_signal} remained visible."
        )
        points.append({"kind": "structural", "summary": summary})
    if compare_summary and compare_summary != "all source runs stayed":
        points.append({"kind": "compare", "summary": compare_summary})
    if learning_decision and learning_decision not in {"hold", "pending", ""}:
        points.append(
            {"kind": "learning", "summary": f"Learning decision moved to {learning_decision}."}
        )
    return points


def _next_pivot(
    *,
    routes: dict[str, str],
    turning_points: list[dict[str, str]],
    structural_signal: str,
    learning_decision: str,
) -> dict[str, str]:
    if turning_points:
        top = turning_points[0]
        kind = str(top.get("kind", ""))
        reason = str(top.get("summary", ""))
        if kind in {"structural", "compare"}:
            return {
                "label": "Open judgment workbench",
                "reason": reason,
                "route": str(routes.get("judgment", "")),
            }
        if kind == "learning":
            return {
                "label": "Open learning workbench",
                "reason": reason,
                "route": str(routes.get("learning", "")),
            }
    if structural_signal:
        return {
            "label": "Open judgment workbench",
            "reason": f"Structural signal: {structural_signal}.",
            "route": str(routes.get("judgment", "")),
        }
    if learning_decision:
        return {
            "label": "Open learning workbench",
            "reason": f"Learning decision: {learning_decision}.",
            "route": str(routes.get("learning", "")),
        }
    return {
        "label": "Open execution workbench",
        "reason": "Execution status is the next best pivot.",
        "route": str(routes.get("execution", "")),
    }


def _workspace_storylines(repo_root: Path) -> list[dict[str, Any]]:
    releases = _load_release_index(repo_root)
    release_timeline = _release_timeline(repo_root, releases)
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
        linked_releases = [
            item for item in release_timeline if mission_id in item.get("workspace_ids", [])
        ]
        latest_release = linked_releases[0] if linked_releases else None
        release_journey = [
            {
                "release_id": str(item.get("release_id", "")),
                "release_label": str(item.get("release_label", "")),
                "created_at": str(item.get("created_at", "")),
                "overall_status": str(item.get("overall_status", "")),
                "compare_target_release_id": str(item.get("compare_target_release_id", "")),
                "summary_artifact_path": str(item.get("summary_artifact_path", "")),
                "source_run_compare_summary": str(item.get("source_run_compare_summary", "")),
                "storyline_headline": str(item.get("storyline_headline", "")),
                "compare_focus": list(item.get("compare_focus", [])),
                "lineage_notes": list(item.get("lineage_notes", [])),
            }
            for item in reversed(linked_releases)
        ]
        learning_decisions = learning.get("promotion_policy", {}).get("decisions", [])
        first_learning_decision = (
            learning_decisions[0]
            if isinstance(learning_decisions, list) and learning_decisions
            else {}
        )
        structural_judgment = judgment.get("structural_judgment", {})
        execution_overview = execution.get("overview", {})
        structural_signal = str(structural_judgment.get("quality_signal", ""))
        learning_decision = str(first_learning_decision.get("action", ""))
        compare_summary = (
            str(latest_release.get("source_run_compare_summary", "")) if latest_release else ""
        )
        routes = {
            "overview": f"/?mission={mission_id}&mode=missions&tab=overview",
            "execution": f"/?mission={mission_id}&mode=missions&tab=execution",
            "judgment": f"/?mission={mission_id}&mode=missions&tab=judgment",
            "learning": f"/?mission={mission_id}&mode=missions&tab=learning",
        }
        turning_points = _turning_points(
            structural_signal=structural_signal,
            compare_summary=compare_summary,
            learning_decision=learning_decision,
        )
        storylines.append(
            {
                "workspace_id": mission_id,
                "title": str(mission_payload.get("title", mission_id)),
                "status": str(mission_payload.get("status", "")),
                "narrative": _workspace_narrative(execution, judgment, learning),
                "journey_summary": (
                    f"{len(release_journey)} archived releases; latest "
                    f"{str(latest_release.get('release_id', '')) if latest_release else 'none'}"
                ),
                "release_journey": release_journey,
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
                "turning_points": turning_points,
                "next_pivot": _next_pivot(
                    routes=routes,
                    turning_points=turning_points,
                    structural_signal=structural_signal,
                    learning_decision=learning_decision,
                ),
                "governance_story": {
                    "execution": {
                        "admission_decision_count": int(
                            execution_overview.get("admission_decision_count", 0) or 0
                        ),
                        "pressure_signal_count": int(
                            execution_overview.get("pressure_signal_count", 0) or 0
                        ),
                        "current_phase": str(execution_overview.get("current_phase", "")),
                    },
                    "structural": {
                        "quality_signal": structural_signal,
                        "bottleneck": str(structural_judgment.get("bottleneck", "")),
                        "baseline_ref": str(
                            structural_judgment.get("baseline_diff", {}).get("baseline_ref", "")
                        ),
                    },
                    "learning": {
                        "promotion_decision": learning_decision,
                        "promotion_state": str(first_learning_decision.get("promotion_state", "")),
                        "linked_release_count": len(linked_releases),
                    },
                },
                "lineage_drilldown": {
                    "latest_release_id": (
                        str(latest_release.get("release_id", "")) if latest_release else ""
                    ),
                    "compare_target_release_id": (
                        str(latest_release.get("compare_target_release_id", ""))
                        if latest_release
                        else ""
                    ),
                    "latest_release_summary_artifact": (
                        str(latest_release.get("summary_artifact_path", ""))
                        if latest_release
                        else ""
                    ),
                    "source_run_compare_summary": (
                        str(latest_release.get("source_run_compare_summary", ""))
                        if latest_release
                        else ""
                    ),
                    "compare_counts": (
                        dict(latest_release.get("compare_counts", {})) if latest_release else {}
                    ),
                    "compare_focus": (
                        list(latest_release.get("compare_focus", [])) if latest_release else []
                    ),
                    "latest_release_notes": (
                        list(latest_release.get("lineage_notes", [])) if latest_release else []
                    ),
                },
                "routes": routes,
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


def _watchlist(storylines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    watchlist: list[dict[str, Any]] = []
    for item in storylines:
        structural_signal = str(
            item.get("governance_story", {}).get("structural", {}).get("quality_signal", "")
        ).strip()
        compare_focus = [
            entry
            for entry in item.get("lineage_drilldown", {}).get("compare_focus", [])
            if isinstance(entry, str)
        ]
        learning_decision = str(
            item.get("governance_story", {}).get("learning", {}).get("promotion_decision", "")
        ).strip()
        if structural_signal and structural_signal not in {"stable", "healthy", "pass"}:
            focus = (
                "structural regression"
                if structural_signal == "regression"
                else f"structural {structural_signal}"
            )
        elif compare_focus:
            focus = compare_focus[0]
        elif learning_decision:
            focus = f"learning {learning_decision}"
        else:
            focus = "workspace lineage"
        priority_score = 1
        priority_reasons: list[str] = []
        if structural_signal == "regression":
            priority_score += 5
            priority_reasons.append("Structural regression")
        elif structural_signal and structural_signal not in {"stable", "healthy", "pass"}:
            priority_score += 3
            priority_reasons.append(f"Structural {structural_signal}")
        advanced_count = len(compare_focus)
        if advanced_count:
            priority_score += min(advanced_count, 3)
            priority_reasons.append("advanced source-run drift")
        if learning_decision and learning_decision not in {"hold", "pending", ""}:
            priority_score += 1
            priority_reasons.append(f"learning {learning_decision}")
        priority_reason = (
            " plus ".join(priority_reasons) + " keeps this workspace at the top."
            if priority_reasons
            else "Workspace lineage still needs operator attention."
        )
        watchlist.append(
            {
                "workspace_id": str(item.get("workspace_id", "")),
                "title": str(item.get("title", item.get("workspace_id", ""))),
                "focus": focus,
                "compare_focus": compare_focus,
                "journey_summary": str(item.get("journey_summary", "")),
                "priority_score": priority_score,
                "priority_reason": priority_reason[:1].upper() + priority_reason[1:],
                "latest_turning_point": str(
                    (item.get("turning_points", [{}]) or [{}])[0].get("summary", "")
                ),
                "route": str(item.get("routes", {}).get("judgment", "")),
            }
        )
    watchlist.sort(
        key=lambda item: (
            -int(item.get("priority_score", 0) or 0),
            str(item.get("workspace_id", "")),
        )
    )
    return watchlist


def _brief(
    release_timeline: list[dict[str, Any]],
    watchlist: list[dict[str, Any]],
    storylines: list[dict[str, Any]],
) -> dict[str, str]:
    advanced_check_count = sum(
        int(item.get("compare_counts", {}).get("advanced", 0) or 0) for item in release_timeline
    )
    latest_release_id = str(release_timeline[0].get("release_id", "")) if release_timeline else ""
    top_watch = watchlist[0] if watchlist else {}
    top_storyline = storylines[0] if storylines else {}
    next_pivot = top_storyline.get("next_pivot", {}) if isinstance(top_storyline, dict) else {}
    return {
        "headline": (
            f"{len(release_timeline)} releases archived; "
            f"{advanced_check_count} advanced checks; "
            f"{len(watchlist)} workspaces on watch"
        ),
        "latest_release_id": latest_release_id,
        "top_watch_focus": str(top_watch.get("focus", "")),
        "top_turning_point": str(top_watch.get("latest_turning_point", "")),
        "top_watch_reason": str(top_watch.get("priority_reason", "")),
        "next_route": str(next_pivot.get("route", "")),
        "next_route_label": str(next_pivot.get("label", "")),
    }


def build_showcase_workbench(repo_root: Path) -> dict[str, Any]:
    releases = _load_release_index(repo_root)
    release_timeline = _release_timeline(repo_root, releases)
    storylines = _workspace_storylines(repo_root)
    highlights = _highlights(release_timeline, storylines)
    watchlist = _watchlist(storylines)
    brief = _brief(release_timeline, watchlist, storylines)
    return {
        "summary": {
            "release_count": len(release_timeline),
            "passing_release_count": sum(
                1 for item in release_timeline if str(item.get("overall_status", "")) == "pass"
            ),
            "workspace_story_count": len(storylines),
            "highlight_count": len(highlights),
            "advanced_check_count": sum(
                int(item.get("compare_counts", {}).get("advanced", 0) or 0)
                for item in release_timeline
            ),
            "watchlist_count": len(watchlist),
        },
        "brief": brief,
        "release_timeline": release_timeline,
        "workspace_storylines": storylines,
        "highlights": highlights,
        "watchlist": watchlist,
        "review_route": "/?mode=showcase",
    }


__all__ = ["build_showcase_workbench"]
