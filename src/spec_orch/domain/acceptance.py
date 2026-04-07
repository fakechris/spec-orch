"""Acceptance-related domain models."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


def _coerce_confidence_score(value: Any, *, default: float = 0.0) -> float:
    def _sanitize(number: float) -> float:
        return number if math.isfinite(number) and 0.0 <= number <= 1.0 else default

    if isinstance(value, bool):
        return _sanitize(float(value))
    if isinstance(value, (int, float)):
        return _sanitize(float(value))
    if isinstance(value, str):
        normalized = value.strip().lower()
        if not normalized:
            return default
        mapped = {"high": 0.9, "medium": 0.7, "low": 0.3}.get(normalized)
        if mapped is not None:
            return _sanitize(mapped)
        try:
            return _sanitize(float(normalized))
        except ValueError:
            return default
    return default


@dataclass
class AcceptanceFinding:
    severity: str
    summary: str
    details: str = ""
    expected: str = ""
    actual: str = ""
    route: str = ""
    artifact_paths: dict[str, str] = field(default_factory=dict)
    critique_axis: str = ""
    operator_task: str = ""
    why_it_matters: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "summary": self.summary,
            "details": self.details,
            "expected": self.expected,
            "actual": self.actual,
            "route": self.route,
            "artifact_paths": self.artifact_paths,
            "critique_axis": self.critique_axis,
            "operator_task": self.operator_task,
            "why_it_matters": self.why_it_matters,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AcceptanceFinding:
        return cls(
            severity=data.get("severity", ""),
            summary=data.get("summary", ""),
            details=data.get("details", ""),
            expected=data.get("expected", ""),
            actual=data.get("actual", ""),
            route=data.get("route", ""),
            artifact_paths=data.get("artifact_paths", {}),
            critique_axis=data.get("critique_axis", ""),
            operator_task=data.get("operator_task", ""),
            why_it_matters=data.get("why_it_matters", ""),
        )


class AcceptanceMode(StrEnum):
    FEATURE_SCOPED = "feature_scoped"
    IMPACT_SWEEP = "impact_sweep"
    WORKFLOW = "workflow"
    EXPLORATORY = "exploratory"


@dataclass
class AcceptanceInteractionStep:
    action: str
    target: str
    description: str = ""
    value: str = ""
    timeout_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "target": self.target,
            "description": self.description,
            "value": self.value,
            "timeout_ms": self.timeout_ms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AcceptanceInteractionStep:
        raw_timeout = data.get("timeout_ms", 0)
        try:
            timeout_ms = int(raw_timeout)
        except (TypeError, ValueError):
            timeout_ms = 0
        return cls(
            action=data.get("action", ""),
            target=data.get("target", ""),
            description=data.get("description", ""),
            value=str(data.get("value", "") or ""),
            timeout_ms=max(timeout_ms, 0),
        )


@dataclass
class AcceptanceCampaign:
    mode: AcceptanceMode
    goal: str
    primary_routes: list[str] = field(default_factory=list)
    related_routes: list[str] = field(default_factory=list)
    interaction_plans: dict[str, list[AcceptanceInteractionStep]] = field(default_factory=dict)
    coverage_expectations: list[str] = field(default_factory=list)
    required_interactions: list[str] = field(default_factory=list)
    min_primary_routes: int = 0
    related_route_budget: int = 0
    interaction_budget: str = ""
    filing_policy: str = ""
    exploration_budget: str = ""
    seed_routes: list[str] = field(default_factory=list)
    allowed_expansions: list[str] = field(default_factory=list)
    critique_focus: list[str] = field(default_factory=list)
    stop_conditions: list[str] = field(default_factory=list)
    evidence_budget: str = ""
    functional_plan: list[str] = field(default_factory=list)
    adversarial_plan: list[str] = field(default_factory=list)
    coverage_gaps: list[str] = field(default_factory=list)
    merged_plan: list[str] = field(default_factory=list)

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        if value is None:
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "goal": self.goal,
            "primary_routes": self.primary_routes,
            "related_routes": self.related_routes,
            "interaction_plans": {
                route: [step.to_dict() for step in steps]
                for route, steps in self.interaction_plans.items()
            },
            "coverage_expectations": self.coverage_expectations,
            "required_interactions": self.required_interactions,
            "min_primary_routes": self.min_primary_routes,
            "related_route_budget": self.related_route_budget,
            "interaction_budget": self.interaction_budget,
            "filing_policy": self.filing_policy,
            "exploration_budget": self.exploration_budget,
            "seed_routes": self.seed_routes,
            "allowed_expansions": self.allowed_expansions,
            "critique_focus": self.critique_focus,
            "stop_conditions": self.stop_conditions,
            "evidence_budget": self.evidence_budget,
            "functional_plan": self.functional_plan,
            "adversarial_plan": self.adversarial_plan,
            "coverage_gaps": self.coverage_gaps,
            "merged_plan": self.merged_plan,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AcceptanceCampaign:
        def _coerce_str_list(value: Any) -> list[str]:
            if isinstance(value, str):
                stripped = value.strip()
                return [stripped] if stripped else []
            if not isinstance(value, list):
                return []
            return [str(item) for item in value if isinstance(item, str) and item.strip()]

        return cls(
            mode=AcceptanceMode(data.get("mode", AcceptanceMode.EXPLORATORY.value)),
            goal=data.get("goal", ""),
            primary_routes=data.get("primary_routes", []),
            related_routes=data.get("related_routes", []),
            interaction_plans={
                route: [
                    AcceptanceInteractionStep.from_dict(step)
                    for step in steps
                    if isinstance(step, dict)
                ]
                for route, steps in data.get("interaction_plans", {}).items()
                if isinstance(route, str) and isinstance(steps, list)
            },
            coverage_expectations=data.get("coverage_expectations", []),
            required_interactions=data.get("required_interactions", []),
            min_primary_routes=cls._safe_int(data.get("min_primary_routes", 0)),
            related_route_budget=cls._safe_int(data.get("related_route_budget", 0)),
            interaction_budget=data.get("interaction_budget", ""),
            filing_policy=data.get("filing_policy", ""),
            exploration_budget=data.get("exploration_budget", ""),
            seed_routes=_coerce_str_list(data.get("seed_routes", [])),
            allowed_expansions=_coerce_str_list(data.get("allowed_expansions", [])),
            critique_focus=_coerce_str_list(data.get("critique_focus", [])),
            stop_conditions=_coerce_str_list(data.get("stop_conditions", [])),
            evidence_budget=data.get("evidence_budget", ""),
            functional_plan=_coerce_str_list(data.get("functional_plan", [])),
            adversarial_plan=_coerce_str_list(data.get("adversarial_plan", [])),
            coverage_gaps=_coerce_str_list(data.get("coverage_gaps", [])),
            merged_plan=_coerce_str_list(data.get("merged_plan", [])),
        )


@dataclass
class AcceptanceIssueProposal:
    title: str
    summary: str
    severity: str
    confidence: float = 0.0
    repro_steps: list[str] = field(default_factory=list)
    expected: str = ""
    actual: str = ""
    route: str = ""
    artifact_paths: dict[str, str] = field(default_factory=dict)
    critique_axis: str = ""
    operator_task: str = ""
    why_it_matters: str = ""
    hold_reason: str = ""
    linear_issue_id: str = ""
    filing_status: str = ""
    filing_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "summary": self.summary,
            "severity": self.severity,
            "confidence": self.confidence,
            "repro_steps": self.repro_steps,
            "expected": self.expected,
            "actual": self.actual,
            "route": self.route,
            "artifact_paths": self.artifact_paths,
            "critique_axis": self.critique_axis,
            "operator_task": self.operator_task,
            "why_it_matters": self.why_it_matters,
            "hold_reason": self.hold_reason,
            "linear_issue_id": self.linear_issue_id,
            "filing_status": self.filing_status,
            "filing_error": self.filing_error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AcceptanceIssueProposal:
        return cls(
            title=data.get("title", ""),
            summary=data.get("summary", ""),
            severity=data.get("severity", ""),
            confidence=_coerce_confidence_score(data.get("confidence", 0.0)),
            repro_steps=data.get("repro_steps", []),
            expected=data.get("expected", ""),
            actual=data.get("actual", ""),
            route=data.get("route", ""),
            artifact_paths=data.get("artifact_paths", {}),
            critique_axis=data.get("critique_axis", ""),
            operator_task=data.get("operator_task", ""),
            why_it_matters=data.get("why_it_matters", ""),
            hold_reason=data.get("hold_reason", ""),
            linear_issue_id=data.get("linear_issue_id", ""),
            filing_status=data.get("filing_status", ""),
            filing_error=data.get("filing_error", ""),
        )


@dataclass
class AcceptanceReviewResult:
    status: str
    summary: str
    confidence: float
    evaluator: str
    findings: list[AcceptanceFinding] = field(default_factory=list)
    issue_proposals: list[AcceptanceIssueProposal] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)
    tested_routes: list[str] = field(default_factory=list)
    acceptance_mode: str = ""
    coverage_status: str = ""
    untested_expected_routes: list[str] = field(default_factory=list)
    recommended_next_step: str = ""
    campaign: AcceptanceCampaign | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "status": self.status,
            "summary": self.summary,
            "confidence": self.confidence,
            "evaluator": self.evaluator,
            "findings": [finding.to_dict() for finding in self.findings],
            "issue_proposals": [proposal.to_dict() for proposal in self.issue_proposals],
            "artifacts": self.artifacts,
            "tested_routes": self.tested_routes,
            "acceptance_mode": self.acceptance_mode,
            "coverage_status": self.coverage_status,
            "untested_expected_routes": self.untested_expected_routes,
            "recommended_next_step": self.recommended_next_step,
        }
        if self.campaign is not None:
            payload["campaign"] = self.campaign.to_dict()
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AcceptanceReviewResult:
        return cls(
            status=data.get("status", ""),
            summary=data.get("summary", ""),
            confidence=_coerce_confidence_score(data.get("confidence", 0.0)),
            evaluator=data.get("evaluator", ""),
            findings=[
                AcceptanceFinding.from_dict(item)
                for item in data.get("findings", [])
                if isinstance(item, dict)
            ],
            issue_proposals=[
                AcceptanceIssueProposal.from_dict(item)
                for item in data.get("issue_proposals", [])
                if isinstance(item, dict)
            ],
            artifacts=data.get("artifacts", {}),
            tested_routes=data.get("tested_routes", []),
            acceptance_mode=data.get("acceptance_mode", ""),
            coverage_status=data.get("coverage_status", ""),
            untested_expected_routes=data.get("untested_expected_routes", []),
            recommended_next_step=data.get("recommended_next_step", ""),
            campaign=(
                AcceptanceCampaign.from_dict(data["campaign"])
                if isinstance(data.get("campaign"), dict)
                else None
            ),
        )
