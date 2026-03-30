"""Canonical acceptance judgment ontology."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from spec_orch.domain.models import AcceptanceMode, AcceptanceReviewResult


class AcceptanceRunMode(StrEnum):
    VERIFY = "verify"
    REPLAY = "replay"
    EXPLORE = "explore"
    RECON = "recon"


class AcceptanceJudgmentClass(StrEnum):
    CONFIRMED_ISSUE = "confirmed_issue"
    CANDIDATE_FINDING = "candidate_finding"
    OBSERVATION = "observation"


class AcceptanceWorkflowState(StrEnum):
    QUEUED = "queued"
    REVIEWED = "reviewed"
    PROMOTED = "promoted"
    DISMISSED = "dismissed"
    ARCHIVED = "archived"


@dataclass(slots=True)
class CandidateFinding:
    claim: str
    finding_id: str = ""
    surface: str = ""
    route: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    confidence: float = 0.0
    impact_if_true: str = ""
    repro_status: str = ""
    hold_reason: str = ""
    promotion_test: str = ""
    recommended_next_step: str = ""
    dedupe_key: str = ""
    critique_axis: str = ""
    operator_task: str = ""
    why_it_matters: str = ""
    baseline_ref: str = ""
    origin_step: str = ""
    graph_profile: str = ""
    run_mode: str = ""
    compare_overlay: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "claim": self.claim,
            "surface": self.surface,
            "route": self.route,
            "evidence_refs": list(self.evidence_refs),
            "confidence": self.confidence,
            "impact_if_true": self.impact_if_true,
            "repro_status": self.repro_status,
            "hold_reason": self.hold_reason,
            "promotion_test": self.promotion_test,
            "recommended_next_step": self.recommended_next_step,
            "dedupe_key": self.dedupe_key,
            "critique_axis": self.critique_axis,
            "operator_task": self.operator_task,
            "why_it_matters": self.why_it_matters,
            "baseline_ref": self.baseline_ref,
            "origin_step": self.origin_step,
            "graph_profile": self.graph_profile,
            "run_mode": self.run_mode,
            "compare_overlay": self.compare_overlay,
        }


@dataclass(slots=True)
class AcceptanceObservation:
    summary: str
    route: str = ""
    details: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    critique_axis: str = ""
    operator_task: str = ""
    why_it_matters: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "route": self.route,
            "details": self.details,
            "evidence_refs": list(self.evidence_refs),
            "critique_axis": self.critique_axis,
            "operator_task": self.operator_task,
            "why_it_matters": self.why_it_matters,
        }


@dataclass(slots=True)
class AcceptanceJudgment:
    judgment_id: str
    judgment_class: AcceptanceJudgmentClass
    run_mode: AcceptanceRunMode
    workflow_state: AcceptanceWorkflowState
    summary: str
    confidence: float = 0.0
    candidate: CandidateFinding | None = None
    observation: AcceptanceObservation | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "judgment_id": self.judgment_id,
            "judgment_class": self.judgment_class.value,
            "run_mode": self.run_mode.value,
            "workflow_state": self.workflow_state.value,
            "summary": self.summary,
            "confidence": self.confidence,
            "candidate": self.candidate.to_dict() if self.candidate is not None else None,
            "observation": (self.observation.to_dict() if self.observation is not None else None),
        }


def run_mode_from_legacy_acceptance_mode(
    mode: AcceptanceMode | str | None,
) -> AcceptanceRunMode:
    normalized = mode.value if isinstance(mode, AcceptanceMode) else str(mode or "").strip().lower()
    mapping = {
        AcceptanceMode.FEATURE_SCOPED.value: AcceptanceRunMode.VERIFY,
        AcceptanceMode.IMPACT_SWEEP.value: AcceptanceRunMode.VERIFY,
        AcceptanceMode.WORKFLOW.value: AcceptanceRunMode.REPLAY,
        AcceptanceMode.EXPLORATORY.value: AcceptanceRunMode.EXPLORE,
    }
    return mapping.get(normalized, AcceptanceRunMode.RECON)


def build_acceptance_judgments(result: AcceptanceReviewResult) -> list[AcceptanceJudgment]:
    judgments: list[AcceptanceJudgment] = []
    run_mode = run_mode_from_legacy_acceptance_mode(result.acceptance_mode)

    for index, proposal in enumerate(result.issue_proposals):
        hold_reason = str(proposal.hold_reason or "").strip()
        filed = bool(proposal.linear_issue_id or proposal.filing_status == "filed")
        judgment_class = (
            AcceptanceJudgmentClass.CANDIDATE_FINDING
            if hold_reason
            else AcceptanceJudgmentClass.CONFIRMED_ISSUE
        )
        workflow_state = (
            AcceptanceWorkflowState.PROMOTED
            if filed
            else AcceptanceWorkflowState.QUEUED
            if hold_reason
            else AcceptanceWorkflowState.REVIEWED
        )
        candidate = CandidateFinding(
            finding_id=f"candidate:{index}",
            claim=proposal.summary or proposal.title,
            surface=proposal.critique_axis or "",
            route=proposal.route,
            evidence_refs=list(proposal.artifact_paths.values()),
            confidence=proposal.confidence,
            impact_if_true=proposal.why_it_matters,
            repro_status="filed" if filed else "credible",
            hold_reason=hold_reason,
            promotion_test="",
            recommended_next_step=proposal.hold_reason or proposal.filing_status or "",
            dedupe_key=proposal.route or proposal.title,
            critique_axis=proposal.critique_axis,
            operator_task=proposal.operator_task,
            why_it_matters=proposal.why_it_matters,
            baseline_ref=str(result.artifacts.get("baseline_ref") or ""),
            origin_step="issue_proposal",
            graph_profile=str(result.artifacts.get("graph_profile") or ""),
            run_mode=run_mode.value,
            compare_overlay=bool(result.artifacts.get("compare_overlay")),
        )
        judgments.append(
            AcceptanceJudgment(
                judgment_id=f"proposal:{index}",
                judgment_class=judgment_class,
                run_mode=run_mode,
                workflow_state=workflow_state,
                summary=proposal.summary or proposal.title,
                confidence=proposal.confidence,
                candidate=candidate,
            )
        )

    if judgments:
        return judgments

    for index, finding in enumerate(result.findings):
        judgments.append(
            AcceptanceJudgment(
                judgment_id=f"finding:{index}",
                judgment_class=AcceptanceJudgmentClass.OBSERVATION,
                run_mode=run_mode,
                workflow_state=AcceptanceWorkflowState.REVIEWED,
                summary=finding.summary,
                confidence=result.confidence,
                observation=AcceptanceObservation(
                    summary=finding.summary,
                    route=finding.route,
                    details=finding.details,
                    evidence_refs=list(finding.artifact_paths.values()),
                    critique_axis=finding.critique_axis,
                    operator_task=finding.operator_task,
                    why_it_matters=finding.why_it_matters,
                ),
            )
        )

    return judgments


__all__ = [
    "AcceptanceJudgment",
    "AcceptanceJudgmentClass",
    "AcceptanceObservation",
    "AcceptanceRunMode",
    "AcceptanceWorkflowState",
    "CandidateFinding",
    "build_acceptance_judgments",
    "run_mode_from_legacy_acceptance_mode",
]
