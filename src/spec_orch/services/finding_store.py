"""Persistent store for structured review Findings.

Findings are stored as one JSON object per line in
``workspace/findings.jsonl``, enabling append-only writes from multiple
review sources while keeping reads simple.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from spec_orch.domain.models import Finding, ReviewMeta


def _findings_path(workspace: Path) -> Path:
    return workspace / "findings.jsonl"


def append_finding(workspace: Path, finding: Finding) -> None:
    """Append a single Finding to the store."""
    path = _findings_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(_finding_to_dict(finding)) + "\n")


def append_findings(workspace: Path, findings: list[Finding]) -> None:
    """Append multiple Findings in one operation."""
    if not findings:
        return
    path = _findings_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for finding in findings:
            f.write(json.dumps(_finding_to_dict(finding)) + "\n")


def load_findings(workspace: Path) -> list[Finding]:
    """Load all persisted Findings."""
    path = _findings_path(workspace)
    if not path.exists():
        return []
    findings: list[Finding] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        findings.append(_finding_from_dict(json.loads(line)))
    return findings


def load_review_meta(workspace: Path) -> ReviewMeta:
    """Build a ReviewMeta from persisted findings and epoch counter."""
    findings = load_findings(workspace)
    epoch_path = workspace / "review_epoch.json"
    epoch = 0
    budget = 3
    if epoch_path.exists():
        data = json.loads(epoch_path.read_text())
        epoch = data.get("review_epoch", 0)
        budget = data.get("autofix_budget", 3)
    return ReviewMeta(
        review_epoch=epoch,
        autofix_budget=budget,
        findings=findings,
    )


def bump_review_epoch(workspace: Path, budget: int = 3) -> int:
    """Increment the review epoch counter and return the new value."""
    epoch_path = workspace / "review_epoch.json"
    epoch = 0
    if epoch_path.exists():
        data = json.loads(epoch_path.read_text())
        epoch = data.get("review_epoch", 0)
        budget = data.get("autofix_budget", budget)
    epoch += 1
    epoch_path.write_text(
        json.dumps({"review_epoch": epoch, "autofix_budget": budget}, indent=2) + "\n"
    )
    return epoch


def resolve_finding(workspace: Path, finding_id: str) -> bool:
    """Mark a finding as resolved. Returns True if found and updated."""
    findings = load_findings(workspace)
    updated = False
    for f in findings:
        if f.id == finding_id:
            f.resolved = True
            updated = True
    if updated:
        path = _findings_path(workspace)
        with path.open("w", encoding="utf-8") as fh:
            for f in findings:
                fh.write(json.dumps(_finding_to_dict(f)) + "\n")
    return updated


def fingerprint_from(
    source: str,
    description: str,
    file_path: str | None = None,
    line: int | None = None,
) -> str:
    """Generate a stable fingerprint for deduplication."""
    key = f"{source}:{file_path or ''}:{line or ''}:{description}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _finding_to_dict(f: Finding) -> dict:
    return {
        "id": f.id,
        "source": f.source,
        "severity": f.severity,
        "confidence": f.confidence,
        "scope": f.scope,
        "fingerprint": f.fingerprint,
        "description": f.description,
        "file_path": f.file_path,
        "line": f.line,
        "suggested_action": f.suggested_action,
        "resolved": f.resolved,
    }


def _finding_from_dict(d: dict) -> Finding:
    return Finding(
        id=d["id"],
        source=d["source"],
        severity=d["severity"],
        confidence=d.get("confidence", 0.5),
        scope=d.get("scope", "in_spec"),
        fingerprint=d["fingerprint"],
        description=d["description"],
        file_path=d.get("file_path"),
        line=d.get("line"),
        suggested_action=d.get("suggested_action"),
        resolved=d.get("resolved", False),
    )
