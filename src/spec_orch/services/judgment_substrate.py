from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from spec_orch.acceptance_core.calibration import dashboard_surface_pack_v1
from spec_orch.acceptance_core.disposition import AcceptanceDisposition
from spec_orch.acceptance_core.models import build_acceptance_judgments
from spec_orch.domain.models import AcceptanceReviewResult
from spec_orch.services.operator_semantics import (
    compare_overlay_from_acceptance_review,
    evidence_bundle_from_acceptance_review,
    judgment_from_acceptance_judgment,
    judgment_timeline_entries_for_review,
    surface_pack_from_acceptance_surface_pack,
)
from spec_orch.services.structural_judgment import build_structural_judgment

logger = logging.getLogger(__name__)


def _review_overview(review_data: dict[str, Any]) -> dict[str, Any]:
    shared_judgments = review_data.get("shared_judgments", [])
    first = shared_judgments[0] if isinstance(shared_judgments, list) and shared_judgments else {}
    review_state = str(first.get("review_state", ""))
    if review_state == "promoted":
        review_state = "reviewed"
    counts = {
        "confirmed_issue_count": 0,
        "candidate_finding_count": 0,
        "observation_count": 0,
    }
    for judgment in shared_judgments if isinstance(shared_judgments, list) else []:
        judgment_class = str(judgment.get("judgment_class", "")).strip()
        if judgment_class == "confirmed_issue":
            counts["confirmed_issue_count"] += 1
        elif judgment_class == "candidate_finding":
            counts["candidate_finding_count"] += 1
        elif judgment_class == "observation":
            counts["observation_count"] += 1
    return {
        "base_run_mode": str(first.get("base_run_mode", "")),
        "judgment_class": str(first.get("judgment_class", "")),
        "review_state": review_state,
        "compare_state": str(review_data.get("compare_overlay", {}).get("compare_state", "")),
        "candidate_finding_count": counts["candidate_finding_count"],
        "confirmed_issue_count": counts["confirmed_issue_count"],
        "observation_count": counts["observation_count"],
        "recommended_next_step": str(
            review_data.get("recommended_next_step") or first.get("recommended_next_step", "")
        ),
        "evidence_summary": str(review_data.get("summary", "")),
    }


def _evidence_panel(review: AcceptanceReviewResult, review_data: dict[str, Any]) -> dict[str, Any]:
    artifacts = review.artifacts if isinstance(review.artifacts, dict) else {}
    artifact_count = 0
    if str(artifacts.get("acceptance_review", "")).strip():
        artifact_count += 1
    if str(artifacts.get("graph_run", "")).strip():
        artifact_count += 1
    step_artifacts = [
        str(item)
        for item in artifacts.get("step_artifacts", [])
        if isinstance(item, str) and item.strip()
    ]
    artifact_count += len(step_artifacts)
    evidence_bundle = review_data.get("evidence_bundle", {})
    return {
        "bundle_kind": str(evidence_bundle.get("bundle_kind", "")),
        "verification_origin": str(evidence_bundle.get("verification_origin", "")),
        "independence_status": str(evidence_bundle.get("independence_status", "")),
        "verifier_artifact_count": int(evidence_bundle.get("verifier_artifact_count", 0) or 0),
        "implementer_artifact_count": int(
            evidence_bundle.get("implementer_artifact_count", 0) or 0
        ),
        "route_count": len(evidence_bundle.get("route_refs", [])),
        "step_count": len(step_artifacts),
        "artifact_count": artifact_count,
        "coverage_status": str(review_data.get("coverage_status", "")),
        "coverage_gaps": [
            str(item)
            for item in review_data.get("untested_expected_routes", [])
            if str(item).strip()
        ],
        "evidence_summary": str(review_data.get("summary", "")),
    }


def _candidate_queue(review_data: dict[str, Any]) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    issue_proposals = review_data.get("issue_proposals", [])
    surface_name = str(review_data.get("surface_pack", {}).get("surface_name", ""))
    for judgment in review_data.get("shared_judgments", []):
        if not isinstance(judgment, dict) or judgment.get("judgment_class") != "candidate_finding":
            continue
        candidate = judgment.get("candidate_finding")
        if not isinstance(candidate, dict):
            continue
        proposal = None
        for item in issue_proposals if isinstance(issue_proposals, list) else []:
            if not isinstance(item, dict):
                continue
            if str(item.get("route", "")).strip() == str(candidate.get("route", "")).strip():
                proposal = item
                break
        claim = str((proposal or {}).get("title") or candidate.get("claim", ""))
        impact_if_true = str(
            (proposal or {}).get("severity") or candidate.get("impact_if_true", "")
        )
        queue.append(
            {
                "candidate_finding_id": str(candidate.get("finding_id", "")),
                "claim": claim,
                "surface": surface_name or str(candidate.get("surface", "")),
                "route": str(candidate.get("route", "")),
                "why_it_matters": str(candidate.get("why_it_matters", "")),
                "confidence": float(candidate.get("confidence", 0.0) or 0.0),
                "impact_if_true": impact_if_true,
                "repro_status": (
                    "needs_repro"
                    if str(judgment.get("review_state", "")) == "queued"
                    else str(candidate.get("repro_status", ""))
                ),
                "hold_reason": str(candidate.get("hold_reason", "")),
                "promotion_test": str(candidate.get("promotion_test", "")).strip()
                or "Promote once the recommended next step completes.",
                "recommended_next_step": str(
                    review_data.get("recommended_next_step")
                    or candidate.get("recommended_next_step")
                    or judgment.get("recommended_next_step", "")
                ),
            }
        )
    return queue


def _compare_view(review_data: dict[str, Any]) -> dict[str, Any]:
    compare_overlay = review_data.get("compare_overlay", {})
    compare_state = str(compare_overlay.get("compare_state", "inactive"))
    baseline_ref = str(compare_overlay.get("baseline_ref", ""))
    artifact_drift_refs = compare_overlay.get("artifact_drift_refs", [])
    artifact_drift_count = len(artifact_drift_refs if isinstance(artifact_drift_refs, list) else [])
    return {
        "compare_state": compare_state,
        "baseline_ref": baseline_ref,
        "drift_summary": (
            f"Baseline {baseline_ref} compared against current review."
            if compare_state == "active" and baseline_ref
            else "No comparison baseline was active for this review."
        ),
        "artifact_drift_count": artifact_drift_count,
        "judgment_drift_summary": (
            "Candidate findings were formed under compare overlay."
            if compare_state == "active"
            else "No judgment drift recorded."
        ),
    }


def _surface_pack_panel(review_data: dict[str, Any]) -> dict[str, Any]:
    surface_pack = review_data.get("surface_pack", {})
    surface_name = str(surface_pack.get("surface_name", ""))
    active_axes = list(surface_pack.get("active_axes", []))
    known_routes = list(surface_pack.get("known_routes", []))
    if surface_name == "dashboard":
        axis_map = {
            "evidence_discoverability": "information_scent",
            "task_continuity": "task_continuity",
            "operator_comprehension": "feedback_clarity",
        }
        active_axes = [axis_map[item] for item in active_axes if item in axis_map]
        known_routes = [
            "/",
            "/launcher",
            "/missions",
            "/missions?tab=transcript",
            "/missions?tab=judgment",
        ]
    return {
        "surface_name": surface_name,
        "active_axes": active_axes,
        "known_routes": known_routes,
        "graph_profiles": list(surface_pack.get("graph_profiles", [])),
        "baseline_refs": list(surface_pack.get("baseline_refs", [])),
    }


def build_mission_judgment_substrate(repo_root: Path, mission_id: str) -> dict[str, Any]:
    specs_dir = Path(repo_root) / "docs" / "specs" / mission_id
    rounds_dir = specs_dir / "rounds"
    review_route = f"/?mission={mission_id}&mode=missions&tab=judgment"
    if not rounds_dir.exists():
        return {
            "mission_id": mission_id,
            "summary": {
                "total_reviews": 0,
                "passes": 0,
                "warnings": 0,
                "failures": 0,
                "filed_issues": 0,
                "latest_confidence": 0.0,
            },
            "overview": {
                "base_run_mode": "",
                "judgment_class": "",
                "review_state": "",
                "compare_state": "inactive",
                "candidate_finding_count": 0,
                "confirmed_issue_count": 0,
                "observation_count": 0,
                "recommended_next_step": "",
                "evidence_summary": "",
            },
            "review_route": review_route,
            "latest_review": None,
            "reviews": [],
        }

    reviews: list[dict[str, Any]] = []
    round_dirs: list[tuple[int, Path]] = []
    for round_dir in rounds_dir.glob("round-*"):
        try:
            round_id = int(round_dir.name.split("-")[-1])
        except (TypeError, ValueError, IndexError):
            logger.warning("Skipping acceptance directory with invalid round suffix: %s", round_dir)
            continue
        round_dirs.append((round_id, round_dir))

    for round_id, round_dir in sorted(round_dirs, key=lambda item: item[0]):
        review_path = round_dir / "acceptance_review.json"
        if not review_path.exists():
            continue
        try:
            payload = json.loads(review_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                logger.warning("Ignoring malformed acceptance review payload: %s", review_path)
                continue
            review = AcceptanceReviewResult.from_dict(payload)
        except (OSError, ValueError, json.JSONDecodeError):
            continue

        review_data = review.to_dict()
        normalized_judgments = build_acceptance_judgments(review)
        judgments = [judgment.to_dict() for judgment in normalized_judgments]
        shared_judgment_models = [
            judgment_from_acceptance_judgment(judgment, workspace_id=mission_id)
            for judgment in normalized_judgments
        ]
        shared_judgments = [item.to_dict() for item in shared_judgment_models]
        for shared_judgment in shared_judgments:
            candidate = shared_judgment.get("candidate_finding")
            if isinstance(candidate, dict) and "candidate_finding_id" not in candidate:
                candidate["candidate_finding_id"] = str(candidate.get("finding_id", ""))
        evidence_bundle = evidence_bundle_from_acceptance_review(
            review,
            workspace_id=mission_id,
            round_id=round_id,
            artifact_path=str(review_path.relative_to(repo_root)),
        ).to_dict()
        compare_overlay = compare_overlay_from_acceptance_review(
            review,
            workspace_id=mission_id,
            judgments=shared_judgment_models,
        ).to_dict()
        graph_profile = str((review.artifacts or {}).get("graph_profile", "")).strip()
        baseline_refs = [
            judgment.candidate_finding.baseline_ref
            for judgment in shared_judgment_models
            if judgment.candidate_finding is not None and judgment.candidate_finding.baseline_ref
        ]
        if compare_overlay.get("baseline_ref"):
            baseline_refs.append(str(compare_overlay["baseline_ref"]))
        surface_pack_model = surface_pack_from_acceptance_surface_pack(
            dashboard_surface_pack_v1(mission_id),
            workspace_id=mission_id,
            graph_profiles=[graph_profile] if graph_profile else [],
            baseline_refs=baseline_refs,
        )
        surface_pack = surface_pack_model.to_dict()
        judgment_timeline = [
            item.to_dict()
            for item in judgment_timeline_entries_for_review(
                workspace_id=mission_id,
                round_id=round_id,
                review=review,
                judgments=shared_judgment_models,
                evidence_bundle=evidence_bundle_from_acceptance_review(
                    review,
                    workspace_id=mission_id,
                    round_id=round_id,
                    artifact_path=str(review_path.relative_to(repo_root)),
                ),
                compare_overlay=compare_overlay_from_acceptance_review(
                    review,
                    workspace_id=mission_id,
                    judgments=shared_judgment_models,
                ),
            )
        ]
        graph_artifacts = {
            "graph_run": review.artifacts.get("graph_run", ""),
            "graph_profile": graph_profile,
            "step_artifacts": list(review.artifacts.get("step_artifacts", []))
            if isinstance(review.artifacts.get("step_artifacts"), list)
            else [],
            "graph_transitions": list(review.artifacts.get("graph_transitions", []))
            if isinstance(review.artifacts.get("graph_transitions"), list)
            else [],
            "step_count": len(review.artifacts.get("step_artifacts", []))
            if isinstance(review.artifacts.get("step_artifacts"), list)
            else 0,
            "final_transition": str(review.artifacts.get("final_transition", "") or ""),
        }
        review_data.update(
            {
                "round_id": round_id,
                "artifact_path": str(review_path.relative_to(repo_root)),
                "judgments": judgments,
                "shared_judgments": shared_judgments,
                "evidence_bundle": evidence_bundle,
                "compare_overlay": compare_overlay,
                "surface_pack": surface_pack,
                "judgment_timeline": judgment_timeline,
                "graph_artifacts": graph_artifacts,
                "candidate_findings": [
                    judgment
                    for judgment in shared_judgments
                    if judgment.get("judgment_class") == "candidate_finding"
                ],
                "filed_issues": [
                    proposal.to_dict()
                    for proposal in review.issue_proposals
                    if proposal.linear_issue_id or proposal.filing_status == "filed"
                ],
                "disposition_vocab": [item.value for item in AcceptanceDisposition],
                "review_route": (
                    f"/?mission={mission_id}&mode=missions&tab=judgment&round={round_id}"
                ),
            }
        )
        review_data["evidence_panel"] = _evidence_panel(review, review_data)
        review_data["candidate_queue"] = _candidate_queue(review_data)
        review_data["compare_view"] = _compare_view(review_data)
        review_data["surface_pack_panel"] = _surface_pack_panel(review_data)
        review_data["structural_judgment"] = build_structural_judgment(
            workspace_id=mission_id,
            review_status=str(review_data.get("status", "")),
            coverage_status=str(review_data.get("coverage_status", "")),
            untested_expected_routes=[
                str(item)
                for item in review_data.get("untested_expected_routes", [])
                if str(item).strip()
            ],
            candidate_queue=review_data["candidate_queue"],
            compare_view=review_data["compare_view"],
            evidence_panel=review_data["evidence_panel"],
            overview=_review_overview(review_data),
        )
        reviews.append(review_data)

    summary = {
        "total_reviews": len(reviews),
        "passes": sum(1 for review in reviews if review.get("status") == "pass"),
        "warnings": sum(1 for review in reviews if review.get("status") == "warn"),
        "failures": sum(1 for review in reviews if review.get("status") == "fail"),
        "filed_issues": sum(len(review.get("filed_issues", [])) for review in reviews),
        "latest_confidence": float(reviews[-1].get("confidence", 0.0)) if reviews else 0.0,
    }
    return {
        "mission_id": mission_id,
        "summary": summary,
        "overview": _review_overview(reviews[-1]) if reviews else _review_overview({}),
        "review_route": review_route,
        "latest_review": reviews[-1] if reviews else None,
        "reviews": reviews,
    }


__all__ = ["build_mission_judgment_substrate"]
