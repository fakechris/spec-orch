"""Task Contract schema and generation.

A Task Contract is a structured declaration of:
- What a task is supposed to achieve (intent)
- What boundaries the executing agent must stay within
- How to verify completion
- Risk assessment for the task

Contracts are generated from Issues and can be serialized to YAML
for human review or machine consumption.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class TaskContract:
    """Structured task contract for agent-spec boundary enforcement."""

    contract_id: str
    issue_id: str
    intent: str
    risk_level: str = "medium"
    allowed_paths: list[str] = field(default_factory=list)
    forbidden_paths: list[str] = field(default_factory=list)
    completion_criteria: list[str] = field(default_factory=list)
    verification_commands: dict[str, list[str]] = field(default_factory=dict)
    boundaries: list[str] = field(default_factory=list)
    risk_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "issue_id": self.issue_id,
            "intent": self.intent,
            "risk_level": self.risk_level,
            "allowed_paths": self.allowed_paths,
            "forbidden_paths": self.forbidden_paths,
            "completion_criteria": self.completion_criteria,
            "verification_commands": self.verification_commands,
            "boundaries": self.boundaries,
            "risk_notes": self.risk_notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskContract:
        return cls(
            contract_id=data.get("contract_id", ""),
            issue_id=data.get("issue_id", ""),
            intent=data.get("intent", ""),
            risk_level=data.get("risk_level", "medium"),
            allowed_paths=data.get("allowed_paths", []),
            forbidden_paths=data.get("forbidden_paths", []),
            completion_criteria=data.get("completion_criteria", []),
            verification_commands=data.get("verification_commands", {}),
            boundaries=data.get("boundaries", []),
            risk_notes=data.get("risk_notes", []),
        )

    def validate(self) -> list[str]:
        """Validate the contract, returning a list of error messages."""
        errors: list[str] = []
        if not self.contract_id:
            errors.append("contract_id is required")
        if not self.issue_id:
            errors.append("issue_id is required")
        if not self.intent:
            errors.append("intent is required")
        if self.risk_level not in ("low", "medium", "high", "critical"):
            errors.append(f"risk_level must be low/medium/high/critical, got {self.risk_level!r}")
        if not self.completion_criteria:
            errors.append("at least one completion criterion is required")
        return errors


_HIGH_RISK_PATTERNS = re.compile(
    r"(database|migration|auth|security|payment|deploy|infra|production)",
    re.IGNORECASE,
)
_LOW_RISK_PATTERNS = re.compile(
    r"(doc|readme|comment|typo|rename|format|style|lint)",
    re.IGNORECASE,
)
_CRITICAL_FILE_PATTERNS = re.compile(
    r"(migrations?/|\.env|secrets?|auth|security|deploy|docker|k8s|terraform)",
    re.IGNORECASE,
)


def assess_risk_level(
    *,
    title: str,
    summary: str,
    files_in_scope: list[str],
    run_class: str = "",
) -> str:
    """Assess risk level based on issue metadata and file scope.

    Returns one of: low, medium, high, critical
    """
    combined = f"{title} {summary} {run_class}"

    critical_file_count = sum(1 for f in files_in_scope if _CRITICAL_FILE_PATTERNS.search(f))
    if critical_file_count >= 2:
        return "critical"

    if _HIGH_RISK_PATTERNS.search(combined):
        if critical_file_count > 0:
            return "critical"
        return "high"

    if _LOW_RISK_PATTERNS.search(combined) and not files_in_scope:
        return "low"

    if _LOW_RISK_PATTERNS.search(combined) and len(files_in_scope) <= 3:
        return "low"

    if len(files_in_scope) > 10:
        return "high"

    return "medium"


def generate_contract_from_issue(
    issue: Any,
    *,
    contract_id: str | None = None,
) -> TaskContract:
    """Generate a TaskContract from an Issue object."""
    from spec_orch.domain.models import Issue

    if not isinstance(issue, Issue):
        raise TypeError(f"Expected Issue, got {type(issue).__name__}")

    cid = contract_id or f"contract-{issue.issue_id}"
    files = list(issue.context.files_to_read) if issue.context.files_to_read else []

    risk = assess_risk_level(
        title=issue.title,
        summary=issue.summary,
        files_in_scope=files,
        run_class=issue.run_class or "",
    )

    criteria = list(issue.acceptance_criteria) if issue.acceptance_criteria else []
    if not criteria:
        criteria = ["Implementation matches the issue description"]

    verification = dict(issue.verification_commands) if issue.verification_commands else {}

    boundaries = list(issue.context.constraints) if issue.context.constraints else []

    risk_notes: list[str] = []
    if risk in ("high", "critical"):
        risk_notes.append(f"Risk level assessed as {risk} — extra review recommended")
    if any(_CRITICAL_FILE_PATTERNS.search(f) for f in files):
        risk_notes.append("Touches security/infrastructure-sensitive files")

    return TaskContract(
        contract_id=cid,
        issue_id=issue.issue_id,
        intent=issue.builder_prompt or issue.summary or issue.title,
        risk_level=risk,
        allowed_paths=files,
        forbidden_paths=[],
        completion_criteria=criteria,
        verification_commands=verification,
        boundaries=boundaries,
        risk_notes=risk_notes,
    )
