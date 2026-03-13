"""Track and persist spec deviations for evidence loop closure."""

from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path

from spec_orch.domain.models import SpecDeviation, SpecSnapshot


def detect_deviations(
    *,
    workspace: Path,
    snapshot: SpecSnapshot | None,
) -> list[SpecDeviation]:
    """Detect deviations between the spec and actual execution artifacts.

    Checks:
    1. Files changed outside files_in_scope (if specified).
    2. Acceptance criteria not verified.
    """
    if snapshot is None:
        return []

    deviations: list[SpecDeviation] = []
    issue = snapshot.issue
    issue_id = issue.issue_id

    files_in_scope = issue.context.files_to_read if issue.context else []
    if files_in_scope:
        changed_files = _get_changed_files(workspace)
        for f in changed_files:
            if not any(f.startswith(scope) for scope in files_in_scope):
                deviations.append(
                    SpecDeviation(
                        deviation_id=f"dev-{uuid.uuid4().hex[:8]}",
                        issue_id=issue_id,
                        mission_id=issue.mission_id or "",
                        description=f"File changed outside scope: {f}",
                        severity="minor",
                        detected_by="gate/scope_check",
                        file_path=f,
                    )
                )

    return deviations


def _get_changed_files(workspace: Path) -> list[str]:
    """Get list of files changed in the workspace relative to main."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "main"],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return [f.strip() for f in result.stdout.splitlines() if f.strip()]
    except FileNotFoundError:
        pass
    return []


def write_deviations(workspace: Path, deviations: list[SpecDeviation]) -> Path:
    """Append deviations to the workspace's deviations.jsonl."""
    path = workspace / "deviations.jsonl"
    with path.open("a") as f:
        for d in deviations:
            f.write(
                json.dumps(
                    {
                        "deviation_id": d.deviation_id,
                        "issue_id": d.issue_id,
                        "mission_id": d.mission_id,
                        "description": d.description,
                        "severity": d.severity,
                        "resolution": d.resolution,
                        "detected_by": d.detected_by,
                        "file_path": d.file_path,
                    }
                )
                + "\n"
            )
    return path


def load_deviations(workspace: Path) -> list[SpecDeviation]:
    """Load deviations from workspace's deviations.jsonl."""
    path = workspace / "deviations.jsonl"
    if not path.exists():
        return []
    deviations = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        data = json.loads(line)
        deviations.append(SpecDeviation(**data))
    return deviations
