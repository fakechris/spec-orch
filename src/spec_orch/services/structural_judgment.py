from __future__ import annotations

from typing import Any


def _coerce_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _coerce_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _rule_family_for_rule(rule_id: str) -> str:
    mapping = {
        "review_failed": "semantic_review",
        "coverage_incomplete": "coverage",
        "candidate_repro_pending": "candidate_repro",
        "baseline_drift_detected": "baseline_diff",
        "evidence_missing": "evidence",
    }
    return mapping.get(rule_id, "other")


def build_structural_judgment(
    *,
    workspace_id: str,
    review_status: str,
    coverage_status: str,
    untested_expected_routes: list[str],
    candidate_queue: list[dict[str, Any]],
    compare_view: dict[str, Any],
    evidence_panel: dict[str, Any],
    overview: dict[str, Any],
) -> dict[str, Any]:
    normalized_candidate_queue = [item for item in candidate_queue if isinstance(item, dict)]
    normalized_compare_view = _coerce_mapping(compare_view)
    normalized_evidence_panel = _coerce_mapping(evidence_panel)
    normalized_overview = _coerce_mapping(overview)
    normalized_status = str(review_status or "").strip().lower()
    normalized_coverage = str(coverage_status or "").strip().lower()
    pending_candidate_count = sum(
        1
        for item in normalized_candidate_queue
        if str(item.get("repro_status", "")).strip().lower()
        in {"needs_repro", "not_reproduced", "pending"}
    )
    confirmed_issue_count = _coerce_int(normalized_overview.get("confirmed_issue_count", 0))
    candidate_finding_count = _coerce_int(normalized_overview.get("candidate_finding_count", 0))
    observation_count = _coerce_int(normalized_overview.get("observation_count", 0))
    route_count = _coerce_int(normalized_evidence_panel.get("route_count", 0))
    artifact_count = _coerce_int(normalized_evidence_panel.get("artifact_count", 0))
    compare_state = str(normalized_compare_view.get("compare_state", "inactive") or "inactive")
    baseline_ref = (
        str(normalized_compare_view.get("baseline_ref", "")).strip()
        if isinstance(normalized_compare_view.get("baseline_ref", ""), str)
        else ""
    )
    artifact_drift_count = _coerce_int(normalized_compare_view.get("artifact_drift_count", 0))

    rule_violations: list[dict[str, Any]] = []
    if normalized_status == "fail":
        rule_violations.append(
            {
                "rule_id": "review_failed",
                "severity": "high",
                "summary": "Semantic review already marked this workspace as failing.",
                "details": {
                    "review_status": normalized_status,
                    "confirmed_issue_count": confirmed_issue_count,
                },
            }
        )
    if normalized_coverage and normalized_coverage != "complete":
        rule_violations.append(
            {
                "rule_id": "coverage_incomplete",
                "severity": "medium",
                "summary": "Expected routes remain untested.",
                "details": {
                    "coverage_status": normalized_coverage,
                    "untested_route_count": len(untested_expected_routes),
                },
            }
        )
    if pending_candidate_count:
        rule_violations.append(
            {
                "rule_id": "candidate_repro_pending",
                "severity": "medium",
                "summary": "Candidate findings still need repro before promotion.",
                "details": {
                    "pending_candidate_count": pending_candidate_count,
                },
            }
        )
    if compare_state == "active" and artifact_drift_count > 0:
        rule_violations.append(
            {
                "rule_id": "baseline_drift_detected",
                "severity": "medium",
                "summary": "Compare overlay detected baseline drift artifacts.",
                "details": {
                    "artifact_drift_count": artifact_drift_count,
                    "baseline_ref": baseline_ref,
                },
            }
        )
    if route_count == 0 or artifact_count == 0:
        rule_violations.append(
            {
                "rule_id": "evidence_missing",
                "severity": "high",
                "summary": "Structural evidence is incomplete for deterministic review.",
                "details": {
                    "route_count": route_count,
                    "artifact_count": artifact_count,
                },
            }
        )

    has_high_severity = any(item["severity"] == "high" for item in rule_violations)
    quality_signal = (
        "regression"
        if normalized_status == "fail" or has_high_severity
        else "watch"
        if rule_violations
        else "stable"
    )
    bottleneck = "none"
    for rule_id, value in (
        ("evidence_missing", "evidence_missing"),
        ("review_failed", "confirmed_issue"),
        ("candidate_repro_pending", "candidate_repro_pending"),
        ("coverage_incomplete", "coverage_gap"),
        ("baseline_drift_detected", "baseline_drift"),
    ):
        if any(item["rule_id"] == rule_id for item in rule_violations):
            bottleneck = value
            break
    primary_rule_id = next((item["rule_id"] for item in rule_violations), "")
    for rule_id, value in (
        ("evidence_missing", "evidence_missing"),
        ("review_failed", "review_failed"),
        ("candidate_repro_pending", "candidate_repro_pending"),
        ("coverage_incomplete", "coverage_incomplete"),
        ("baseline_drift_detected", "baseline_drift_detected"),
    ):
        if any(item["rule_id"] == rule_id for item in rule_violations):
            primary_rule_id = value
            break
    primary_rule_family = _rule_family_for_rule(primary_rule_id)
    rule_family_counts = {
        "semantic_review": 0,
        "coverage": 0,
        "candidate_repro": 0,
        "baseline_diff": 0,
        "evidence": 0,
    }
    for item in rule_violations:
        rule_family = _rule_family_for_rule(str(item.get("rule_id", "")).strip())
        if rule_family in rule_family_counts:
            rule_family_counts[rule_family] += 1
    active_families = [family for family, count in rule_family_counts.items() if count > 0]
    drift_summary = "No comparison baseline was active."
    drift_hotspots: list[str] = []
    if compare_state == "active" and artifact_drift_count > 0:
        drift_summary = (
            f"{artifact_drift_count} structural drift artifact(s) detected against "
            f"{baseline_ref or 'the active baseline'}."
        )
        drift_hotspots = ["artifact_drift"]
    elif compare_state == "active":
        drift_summary = f"Baseline {baseline_ref or 'active baseline'} compared cleanly."

    drift_status = (
        "drift_detected"
        if compare_state == "active" and artifact_drift_count > 0
        else ("compared_clean" if compare_state == "active" else "not_compared")
    )
    return {
        "structural_judgment_id": f"{workspace_id}:structural",
        "workspace_id": workspace_id,
        "quality_signal": quality_signal,
        "bottleneck": bottleneck,
        "rule_violations": rule_violations,
        "baseline_diff": {
            "compare_state": compare_state,
            "baseline_ref": baseline_ref,
            "artifact_drift_count": artifact_drift_count,
            "drift_status": drift_status,
            "drift_summary": drift_summary,
            "drift_hotspots": drift_hotspots,
        },
        "rule_family_counts": rule_family_counts,
        "bottleneck_breakdown": {
            "primary": bottleneck,
            "primary_rule": primary_rule_id,
            "primary_rule_family": primary_rule_family,
            "blocking_rules": [primary_rule_id] if primary_rule_id else [],
            "supporting_rules": [
                str(item.get("rule_id", "")).strip()
                for item in rule_violations
                if (
                    str(item.get("rule_id", "")).strip()
                    and str(item.get("rule_id", "")).strip() != primary_rule_id
                )
            ],
        },
        "structural_signal_summary": {
            "active_rule_count": len(rule_violations),
            "active_family_count": len(active_families),
            "primary_rule_family": primary_rule_family,
            "signal_summary": (
                "No deterministic structural signals are active."
                if not active_families
                else (
                    f"{len(rule_violations)} rule(s) active across "
                    + ", ".join(active_families)
                    + "."
                )
            ),
        },
        "current_state": {
            "review_status": normalized_status,
            "coverage_status": normalized_coverage,
            "candidate_finding_count": candidate_finding_count,
            "confirmed_issue_count": confirmed_issue_count,
            "observation_count": observation_count,
            "route_count": route_count,
            "artifact_count": artifact_count,
        },
    }


__all__ = ["build_structural_judgment"]
