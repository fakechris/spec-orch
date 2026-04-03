from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(slots=True)
class CanonicalAcceptance:
    success_conditions: list[str] = field(default_factory=list)
    failure_conditions: list[str] = field(default_factory=list)
    verification_expectations: list[str] = field(default_factory=list)
    human_judgment_required: list[str] = field(default_factory=list)
    priority_routes_or_surfaces: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, list[str]]:
        return asdict(self)


@dataclass(slots=True)
class CanonicalIssue:
    issue_id: str
    title: str
    problem: str
    goal: str
    constraints: list[str] = field(default_factory=list)
    acceptance: CanonicalAcceptance = field(default_factory=CanonicalAcceptance)
    evidence_expectations: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    current_plan_hint: str = ""
    origin: str = ""
    source_refs: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["acceptance"] = self.acceptance.to_dict()
        return payload
