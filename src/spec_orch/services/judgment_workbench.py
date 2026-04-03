from __future__ import annotations

from pathlib import Path
from typing import Any

from spec_orch.services.judgment_substrate import build_mission_judgment_substrate


def _empty_overview() -> dict[str, Any]:
    return {
        "base_run_mode": "",
        "judgment_class": "",
        "review_state": "",
        "compare_state": "inactive",
        "candidate_finding_count": 0,
        "confirmed_issue_count": 0,
        "observation_count": 0,
        "recommended_next_step": "",
        "evidence_summary": "",
    }


def _empty_evidence_panel() -> dict[str, Any]:
    return {
        "bundle_kind": "",
        "route_count": 0,
        "step_count": 0,
        "artifact_count": 0,
        "coverage_status": "",
        "coverage_gaps": [],
        "evidence_summary": "",
    }


def _empty_compare_view() -> dict[str, Any]:
    return {
        "compare_state": "inactive",
        "baseline_ref": "",
        "drift_summary": "No comparison baseline was active for this review.",
        "artifact_drift_count": 0,
        "judgment_drift_summary": "No judgment drift recorded.",
    }


def _empty_surface_pack_panel() -> dict[str, Any]:
    return {
        "surface_name": "",
        "active_axes": [],
        "known_routes": [],
        "graph_profiles": [],
        "baseline_refs": [],
    }


def build_mission_judgment_workbench(repo_root: Path, mission_id: str) -> dict[str, Any]:
    substrate = build_mission_judgment_substrate(repo_root, mission_id)
    latest_review = substrate.get("latest_review")
    review_route = f"/?mission={mission_id}&mode=missions&tab=judgment"
    acceptance_review_route = f"/?mission={mission_id}&mode=missions&tab=acceptance"
    if not isinstance(latest_review, dict):
        return {
            "mission_id": mission_id,
            "summary": substrate.get("summary", {}),
            "overview": _empty_overview(),
            "evidence_panel": _empty_evidence_panel(),
            "judgment_timeline": [],
            "candidate_queue": [],
            "compare_view": _empty_compare_view(),
            "surface_pack_panel": _empty_surface_pack_panel(),
            "structural_judgment": {},
            "latest_review": None,
            "reviews": substrate.get("reviews", []),
            "review_route": review_route,
            "acceptance_review_route": acceptance_review_route,
        }
    return {
        "mission_id": mission_id,
        "summary": substrate.get("summary", {}),
        "overview": substrate.get("overview", _empty_overview()),
        "evidence_panel": latest_review.get("evidence_panel", _empty_evidence_panel()),
        "judgment_timeline": latest_review.get("judgment_timeline", []),
        "candidate_queue": latest_review.get("candidate_queue", []),
        "compare_view": latest_review.get("compare_view", _empty_compare_view()),
        "surface_pack_panel": latest_review.get(
            "surface_pack_panel",
            _empty_surface_pack_panel(),
        ),
        "structural_judgment": latest_review.get("structural_judgment", {}),
        "latest_review": latest_review,
        "reviews": substrate.get("reviews", []),
        "review_route": review_route,
        "acceptance_review_route": acceptance_review_route,
    }


def build_judgment_workbench(repo_root: Path) -> dict[str, Any]:
    workspaces: list[dict[str, Any]] = []
    candidate_queue: list[dict[str, Any]] = []
    compare_watch: list[dict[str, Any]] = []
    structural_watch: list[dict[str, Any]] = []

    specs_root = Path(repo_root) / "docs" / "specs"
    if specs_root.exists():
        for mission_root in sorted(specs_root.glob("*")):
            if not mission_root.is_dir():
                continue
            mission_id = mission_root.name
            payload = build_mission_judgment_workbench(repo_root, mission_id)
            latest_review = payload.get("latest_review")
            if not isinstance(latest_review, dict):
                continue
            overview = payload.get("overview", {})
            queue = payload.get("candidate_queue", [])
            compare_view = payload.get("compare_view", {})
            structural_judgment = payload.get("structural_judgment", {})
            candidate_findings = latest_review.get("candidate_findings", [])
            workspace_entry = {
                "workspace_id": mission_id,
                "base_run_mode": overview.get("base_run_mode", ""),
                "judgment_class": overview.get("judgment_class", ""),
                "review_state": overview.get("review_state", ""),
                "compare_state": overview.get("compare_state", "inactive"),
                "candidate_finding_count": overview.get("candidate_finding_count", 0),
                "confirmed_issue_count": overview.get("confirmed_issue_count", 0),
                "observation_count": overview.get("observation_count", 0),
                "recommended_next_step": overview.get("recommended_next_step", ""),
                "evidence_summary": overview.get("evidence_summary", ""),
                "quality_signal": str(structural_judgment.get("quality_signal", "")),
                "bottleneck": str(structural_judgment.get("bottleneck", "")),
                "candidate_finding_ids": [
                    str(item.get("candidate_finding", {}).get("candidate_finding_id", ""))
                    for item in candidate_findings
                    if isinstance(item, dict)
                ],
                "review_route": payload.get("review_route", ""),
            }
            workspaces.append(workspace_entry)
            for item in queue if isinstance(queue, list) else []:
                if not isinstance(item, dict):
                    continue
                candidate_queue.append(
                    {
                        "workspace_id": mission_id,
                        "review_route": payload.get("review_route", ""),
                        **item,
                    }
                )
            if str(compare_view.get("compare_state", "")) == "active":
                compare_watch.append(
                    {
                        "workspace_id": mission_id,
                        "baseline_ref": str(compare_view.get("baseline_ref", "")),
                        "compare_state": "active",
                        "artifact_drift_count": int(
                            compare_view.get("artifact_drift_count", 0) or 0
                        ),
                        "review_route": payload.get("review_route", ""),
                    }
                )
            if isinstance(structural_judgment, dict) and structural_judgment:
                structural_watch.append(
                    {
                        "workspace_id": mission_id,
                        "quality_signal": str(structural_judgment.get("quality_signal", "")),
                        "bottleneck": str(structural_judgment.get("bottleneck", "")),
                        "rule_violation_count": len(
                            structural_judgment.get("rule_violations", [])
                            if isinstance(structural_judgment.get("rule_violations", []), list)
                            else []
                        ),
                        "baseline_ref": str(
                            structural_judgment.get("baseline_diff", {}).get("baseline_ref", "")
                        ),
                        "review_route": payload.get("review_route", ""),
                    }
                )

    summary = {
        "workspace_count": len(workspaces),
        "reviewed_count": len(workspaces),
        "candidate_finding_count": sum(
            int(item.get("candidate_finding_count", 0) or 0) for item in workspaces
        ),
        "confirmed_issue_count": sum(
            int(item.get("confirmed_issue_count", 0) or 0) for item in workspaces
        ),
        "compare_active_count": sum(
            1 for item in workspaces if str(item.get("compare_state", "")) == "active"
        ),
        "structural_regression_count": sum(
            1 for item in workspaces if str(item.get("quality_signal", "")) == "regression"
        ),
        "bottlenecked_workspace_count": sum(
            1 for item in workspaces if str(item.get("bottleneck", "")) not in {"", "none"}
        ),
    }
    return {
        "summary": summary,
        "workspaces": workspaces,
        "candidate_queue": candidate_queue,
        "compare_watch": compare_watch,
        "structural_watch": structural_watch,
        "review_route": "/?mode=judgment",
    }


__all__ = ["build_judgment_workbench", "build_mission_judgment_workbench"]
