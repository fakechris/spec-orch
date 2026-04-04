from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from spec_orch.acceptance_core.calibration import (
    load_fixture_candidate_seed,
    load_fixture_graduation_events,
)
from spec_orch.services.evolution.promotion_registry import PromotionRegistry
from spec_orch.services.learning_promotion_policy import evaluate_learning_promotion
from spec_orch.services.memory.service import MemoryService


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _load_acceptance_history(repo_root: Path) -> list[dict[str, Any]]:
    payload = _load_json(repo_root / "docs" / "acceptance-history" / "index.json")
    if payload is None:
        return []
    releases = payload.get("releases", [])
    if not isinstance(releases, list):
        return []
    return [item for item in releases if isinstance(item, dict)]


def _load_release_source_runs(repo_root: Path, bundle_path: str) -> dict[str, Any] | None:
    if not bundle_path:
        return None
    payload = _load_json(repo_root / bundle_path / "source_runs.json")
    return payload if isinstance(payload, dict) else None


def _empty_verdict_counts() -> dict[str, int]:
    return {
        "promote": 0,
        "keep": 0,
        "discard": 0,
        "rollback": 0,
        "retire": 0,
    }


def _filter_by_mission(rows: list[dict[str, Any]], mission_id: str) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        metadata = row.get("metadata", {})
        if isinstance(metadata, dict) and str(metadata.get("mission_id", "")) == mission_id:
            filtered.append(row)
            continue
        if str(row.get("mission_id", "")) == mission_id:
            filtered.append(row)
    return filtered


def _load_fixture_candidates(repo_root: Path, mission_id: str) -> list[dict[str, Any]]:
    seed_dir = repo_root / "docs" / "specs" / mission_id / "operator" / "fixture_candidates"
    candidates: list[dict[str, Any]] = []
    for path in sorted(seed_dir.glob("*.json")):
        seed = load_fixture_candidate_seed(repo_root, mission_id=mission_id, seed_name=path.stem)
        candidates.append(
            {
                "mission_id": mission_id,
                "fixture_candidate_id": str(seed.get("seed_name", "")),
                "seed_name": str(seed.get("seed_name", "")),
                "stage": str(seed.get("stage", "")),
                "judgment_id": str(seed.get("event", {}).get("judgment_id", "")),
                "finding_id": str(seed.get("event", {}).get("finding_id", "")),
                "origin_finding_ref": str(seed.get("event", {}).get("finding_id", "")),
                "dedupe_key": str(seed.get("event", {}).get("dedupe_key", "")),
                "route": str(seed.get("event", {}).get("route", "")),
                "review_route": f"/?mission={mission_id}&mode=missions&tab=learning",
            }
        )
    return candidates


def _load_fixture_graduations(repo_root: Path, mission_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in load_fixture_graduation_events(repo_root, mission_id):
        rows.append(
            {
                "mission_id": mission_id,
                "judgment_id": str(item.get("judgment_id", "")),
                "finding_id": str(item.get("finding_id", "")),
                "stage": str(item.get("stage", "")),
                "summary": str(item.get("summary", "")),
                "repeat_count": int(item.get("repeat_count", 0) or 0),
                "dedupe_key": str(item.get("dedupe_key", "")),
                "route": str(item.get("route", "")),
                "review_route": f"/?mission={mission_id}&mode=missions&tab=learning",
            }
        )
    return rows


def _acceptance_patterns(
    findings: list[dict[str, Any]],
    mission_id: str,
) -> list[dict[str, Any]]:
    return [
        {
            "workspace_id": mission_id,
            "judgment_id": str(item.get("judgment_id", "")),
            "finding_id": str(item.get("finding_id", "")),
            "dedupe_key": str(item.get("dedupe_key", "")),
            "route": str(item.get("route", "")),
            "baseline_ref": str(item.get("baseline_ref", "")),
            "origin_step": str(item.get("origin_step", "")),
            "promotion_test": str(item.get("promotion_test", "")),
            "summary": str(item.get("summary", "")),
            "review_route": f"/?mission={mission_id}&mode=missions&tab=learning",
        }
        for item in findings
    ]


def _promotion_rows(
    repo_root: Path,
    *,
    journal: list[dict[str, Any]],
    mission_id: str | None = None,
) -> list[dict[str, Any]]:
    journal_by_proposal: dict[str, dict[str, Any]] = {}
    for row in journal:
        metadata = row.get("metadata", {})
        if not isinstance(metadata, dict):
            continue
        proposal_id = str(metadata.get("proposal_id", "")).strip()
        if proposal_id:
            journal_by_proposal[proposal_id] = row

    rows: list[dict[str, Any]] = []
    for record in PromotionRegistry(repo_root).load_records():
        journal_row = journal_by_proposal.get(record.proposal_id)
        metadata = journal_row.get("metadata", {}) if isinstance(journal_row, dict) else {}
        workspace_id = str(metadata.get("mission_id", "")) if isinstance(metadata, dict) else ""
        if mission_id is not None and workspace_id != mission_id:
            continue
        rows.append(
            {
                "promotion_id": record.promotion_id,
                "proposal_id": record.proposal_id,
                "workspace_id": record.workspace_id or workspace_id,
                "evolver_name": record.evolver_name,
                "change_type": record.change_type,
                "origin": record.origin,
                "status": record.status,
                "origin_finding_ref": record.origin_finding_ref
                or (
                    str(metadata.get("origin_finding_ref", ""))
                    if isinstance(metadata, dict)
                    else ""
                ),
                "origin_review_ref": record.origin_review_ref
                or (
                    str(metadata.get("origin_review_ref", "")) if isinstance(metadata, dict) else ""
                ),
                "promotion_target": record.promotion_target or "EvolutionProposalRef",
                "promotion_reason": record.promotion_reason,
                "discipline_verdict": record.discipline_verdict,
                "promotion_state": (
                    "promoted"
                    if record.status == "active"
                    else "retired"
                    if record.status in {"superseded", "retired"}
                    else record.status
                ),
                "evolution_ref_id": record.proposal_id,
                "reviewed_evidence_count": record.reviewed_evidence_count,
                "signal_origins": list(record.signal_origins),
                "created_at": record.created_at,
                "review_route": (
                    f"/?mission={workspace_id}&mode=missions&tab=learning"
                    if workspace_id
                    else "/?mode=learning"
                ),
            }
        )
    rows.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
    return rows


def _linked_release_rows(repo_root: Path, mission_id: str) -> list[dict[str, Any]]:
    linked: list[dict[str, Any]] = []
    for release in _load_acceptance_history(repo_root):
        bundle_path = str(release.get("bundle_path", ""))
        source_runs = _load_release_source_runs(repo_root, bundle_path)
        if source_runs is None:
            continue
        matched = False
        for item in source_runs.values():
            if not isinstance(item, dict):
                continue
            if str(item.get("mission_id", "")) == mission_id:
                matched = True
                break
        if matched:
            linked.append(release)
    return linked


def _promotion_policy_rows(
    findings: list[dict[str, Any]],
    *,
    fixture_candidates: list[dict[str, Any]],
    memory_refs: list[dict[str, Any]],
    promotions: list[dict[str, Any]],
    linked_releases: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    promoted_findings: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    for finding in findings:
        finding_id = str(finding.get("finding_id", ""))
        judgment_id = str(finding.get("judgment_id", ""))
        related_fixture_candidates = [
            item
            for item in fixture_candidates
            if str(item.get("origin_finding_ref", "")) == finding_id
        ]
        related_memory_refs = [
            item
            for item in memory_refs
            if str(item.get("origin_finding_ref", "")) == finding_id
            or str(item.get("origin_review_ref", "")) == judgment_id
        ]
        related_evolution_refs = [
            item
            for item in promotions
            if str(item.get("origin_finding_ref", "")) == finding_id
            or str(item.get("origin_review_ref", "")) == judgment_id
        ]
        decision = evaluate_learning_promotion(
            finding,
            fixture_candidates=related_fixture_candidates,
            memory_refs=related_memory_refs,
            evolution_refs=related_evolution_refs,
            archive_releases=linked_releases,
        )
        promoted_findings.append(decision["promoted_finding"])
        decisions.append(
            {
                "finding_id": finding_id,
                "judgment_id": judgment_id,
                **decision,
            }
        )
    verdict_counts = _empty_verdict_counts()
    summary = {
        "promote_count": sum(1 for item in decisions if item.get("action") == "promote"),
        "hold_count": sum(1 for item in decisions if item.get("action") == "hold"),
        "reject_count": sum(1 for item in decisions if item.get("action") == "reject"),
        "rollback_count": sum(1 for item in decisions if item.get("action") == "rollback"),
        "retire_count": sum(1 for item in decisions if item.get("action") == "retire"),
        "linked_release_count": len(linked_releases),
        "verdict_counts": verdict_counts,
    }
    for item in decisions:
        verdict = str(item.get("verdict", "")).strip()
        if verdict in verdict_counts:
            verdict_counts[verdict] += 1
    return promoted_findings, decisions, summary


def build_mission_learning_workbench(repo_root: Path, mission_id: str) -> dict[str, Any]:
    svc = MemoryService(repo_root=repo_root)
    findings = _filter_by_mission(svc.get_reviewed_acceptance_findings(top_k=50), mission_id)
    self_slice = _filter_by_mission(svc.get_active_learning_slice("self"), mission_id)
    delivery_slice = _filter_by_mission(svc.get_active_learning_slice("delivery"), mission_id)
    feedback_slice = _filter_by_mission(svc.get_active_learning_slice("feedback"), mission_id)
    journal = _filter_by_mission(svc.get_recent_evolution_journal(limit=50), mission_id)
    promotions = _promotion_rows(repo_root, journal=journal, mission_id=mission_id)
    patterns = _acceptance_patterns(findings, mission_id)
    memory_refs = svc.get_learning_memory_refs(mission_id)
    fixture_candidates = _load_fixture_candidates(repo_root, mission_id)
    fixture_graduations = _load_fixture_graduations(repo_root, mission_id)
    releases = _load_acceptance_history(repo_root)
    linked_releases = _linked_release_rows(repo_root, mission_id)
    promoted_findings, promotion_decisions, policy_summary = _promotion_policy_rows(
        findings,
        fixture_candidates=fixture_candidates,
        memory_refs=memory_refs,
        promotions=promotions,
        linked_releases=linked_releases,
    )
    return {
        "mission_id": mission_id,
        "overview": {
            "promoted_finding_count": len(findings),
            "fixture_candidate_count": len(fixture_candidates),
            "active_promotion_count": len(
                [item for item in promotions if item.get("status") == "active"]
            ),
            "evolution_event_count": len(journal),
            "archive_release_count": len(releases),
            "linked_release_count": len(linked_releases),
            "last_learning_summary": str(findings[0].get("summary", "")) if findings else "",
        },
        "promoted_findings": promoted_findings,
        "promotion_policy": {
            "summary": policy_summary,
            "decisions": promotion_decisions,
        },
        "promotion_timeline": promotions,
        "patterns": patterns,
        "fixture_registry": {
            "summary": {
                "candidate_count": len(fixture_candidates),
                "graduation_count": len(fixture_graduations),
            },
            "candidates": fixture_candidates,
            "graduations": fixture_graduations,
        },
        "memory_links": {
            "acceptance_findings": findings,
            "memory_refs": memory_refs,
            "learning_slices": {
                "self": self_slice,
                "delivery": delivery_slice,
                "feedback": feedback_slice,
            },
        },
        "evolution_registry": {
            "recent_journal": journal,
            "active_promotions": promotions,
        },
        "archive_lineage": {
            "releases": releases,
            "linked_releases": linked_releases,
            "raw_release_ids": [
                str(item.get("release_id", ""))
                for item in linked_releases
                if str(item.get("release_id", ""))
            ],
            "promoted_release_ids": [],
        },
        "review_route": f"/?mission={mission_id}&mode=missions&tab=learning",
    }


def build_learning_workbench(repo_root: Path) -> dict[str, Any]:
    repo_root = Path(repo_root)
    svc = MemoryService(repo_root=repo_root)
    workspaces: list[dict[str, Any]] = []
    patterns: list[dict[str, Any]] = []
    fixture_candidates: list[dict[str, Any]] = []
    fixture_graduations: list[dict[str, Any]] = []
    acceptance_findings: list[dict[str, Any]] = []
    memory_refs: list[dict[str, Any]] = []
    learning_slices: dict[str, list[dict[str, Any]]]
    learning_slices = {"self": [], "delivery": [], "feedback": []}
    verdict_counts = _empty_verdict_counts()

    for mission_root in sorted((repo_root / "docs" / "specs").glob("*")):
        if not mission_root.is_dir():
            continue
        mission_id = mission_root.name
        payload = build_mission_learning_workbench(repo_root, mission_id)
        overview = payload.get("overview", {})
        decisions = payload.get("promotion_policy", {}).get("decisions", [])
        first_decision = decisions[0] if isinstance(decisions, list) and decisions else {}
        workspaces.append(
            {
                "workspace_id": mission_id,
                "promoted_finding_count": int(overview.get("promoted_finding_count", 0) or 0),
                "fixture_candidate_count": int(overview.get("fixture_candidate_count", 0) or 0),
                "active_promotion_count": int(overview.get("active_promotion_count", 0) or 0),
                "promotion_decision": str(first_decision.get("action", "")),
                "promotion_verdict": str(first_decision.get("verdict", "")),
                "evolution_event_count": int(overview.get("evolution_event_count", 0) or 0),
                "last_learning_summary": str(overview.get("last_learning_summary", "")),
                "review_route": payload.get("review_route", ""),
            }
        )
        patterns.extend(payload.get("patterns", []))
        fixture_candidates.extend(payload.get("fixture_registry", {}).get("candidates", []))
        fixture_graduations.extend(payload.get("fixture_registry", {}).get("graduations", []))
        memory_links = payload.get("memory_links", {})
        acceptance_findings.extend(memory_links.get("acceptance_findings", []))
        memory_refs.extend(memory_links.get("memory_refs", []))
        slices = memory_links.get("learning_slices", {})
        for kind in learning_slices:
            learning_slices[kind].extend(slices.get(kind, []))
        policy_summary = payload.get("promotion_policy", {}).get("summary", {})
        if isinstance(policy_summary, dict):
            counts = policy_summary.get("verdict_counts", {})
            if isinstance(counts, dict):
                for key in verdict_counts:
                    verdict_counts[key] += int(counts.get(key, 0) or 0)

    recent_journal = svc.get_recent_evolution_journal(limit=50)
    promotions = _promotion_rows(repo_root, journal=recent_journal)
    releases = _load_acceptance_history(repo_root)
    linked_releases: list[dict[str, Any]] = []
    for workspace in workspaces:
        workspace_id = str(workspace.get("workspace_id", ""))
        linked_releases.extend(_linked_release_rows(repo_root, workspace_id))
    linked_by_release_id = {item.get("release_id"): item for item in linked_releases}
    unique_linked_releases = list(linked_by_release_id.values())
    return {
        "summary": {
            "workspace_count": len(workspaces),
            "promoted_finding_count": len(acceptance_findings),
            "fixture_candidate_count": len(fixture_candidates),
            "active_promotion_count": len(
                [item for item in promotions if item.get("status") == "active"]
            ),
            "archive_release_count": len(releases),
            "linked_release_count": len(unique_linked_releases),
            "verdict_counts": verdict_counts,
        },
        "workspaces": workspaces,
        "promotion_timeline": promotions,
        "patterns": patterns,
        "fixture_registry": {
            "summary": {
                "candidate_count": len(fixture_candidates),
                "graduation_count": len(fixture_graduations),
            },
            "candidates": fixture_candidates,
            "graduations": fixture_graduations,
        },
        "memory_links": {
            "acceptance_findings": acceptance_findings,
            "memory_refs": memory_refs,
            "learning_slices": learning_slices,
        },
        "evolution_registry": {
            "recent_journal": recent_journal,
            "active_promotions": promotions,
        },
        "archive_lineage": {
            "releases": releases,
            "linked_releases": unique_linked_releases,
        },
        "review_route": "/?mode=learning",
    }


__all__ = ["build_learning_workbench", "build_mission_learning_workbench"]
