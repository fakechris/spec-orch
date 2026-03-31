from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from spec_orch.runtime_core.readers import read_issue_execution_attempt
from spec_orch.services.workspace_service import WorkspaceService


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _dataclass_payload(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    return value


def write_issue_start_acceptance_report(
    *,
    repo_root: Path,
    issue_id: str,
    fixture_issue_id: str,
    preflight_report: dict[str, Any],
) -> dict[str, str]:
    repo_root = Path(repo_root).resolve()
    workspace = WorkspaceService(repo_root=repo_root).issue_workspace_path(issue_id)
    attempt = read_issue_execution_attempt(workspace)

    status = "fail"
    if (
        isinstance(preflight_report.get("summary"), dict)
        and int(preflight_report["summary"].get("fail", 0)) == 0
        and attempt is not None
        and str(attempt.outcome.status) == "succeeded"
    ):
        status = "pass"

    payload = {
        "status": status,
        "issue_id": issue_id,
        "fixture_issue_id": fixture_issue_id,
        "workspace": str(workspace),
        "preflight": preflight_report,
        "attempt": _dataclass_payload(attempt) if attempt is not None else None,
    }
    report_dir = repo_root / ".spec_orch" / "acceptance"
    json_path = report_dir / "issue_start_smoke.json"
    md_path = report_dir / "issue_start_smoke.md"
    _write_json(json_path, payload)
    md_path.write_text(
        "\n".join(
            [
                "# Issue-Start Acceptance Smoke",
                "",
                f"- Status: `{status}`",
                f"- Issue: `{issue_id}`",
                f"- Fixture issue: `{fixture_issue_id}`",
                f"- Workspace: `{workspace}`",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return {"json_path": str(json_path), "markdown_path": str(md_path)}


def write_mission_start_acceptance_report(
    *,
    repo_root: Path,
    mission_id: str,
    launch_mode: str,
    variant: str,
    round_dir: Path,
) -> dict[str, str]:
    repo_root = Path(repo_root).resolve()
    round_dir = Path(round_dir).resolve()
    fresh_report = _read_json_object(round_dir / "fresh_acpx_mission_e2e_report.json")
    acceptance_review = fresh_report.get("acceptance_review", {})
    review_status = ""
    if isinstance(acceptance_review, dict):
        review_status = str(acceptance_review.get("status", "")).strip().lower()
    status = "pass" if review_status == "pass" else "fail"

    payload = {
        "status": status,
        "mission_id": mission_id,
        "launch_mode": launch_mode,
        "variant": variant,
        "round_dir": str(round_dir),
        "fresh_report": fresh_report,
    }
    operator_dir = repo_root / "docs" / "specs" / mission_id / "operator"
    json_path = operator_dir / "mission_start_acceptance.json"
    md_path = operator_dir / "mission_start_acceptance.md"
    _write_json(json_path, payload)
    operator_dir.mkdir(parents=True, exist_ok=True)
    md_path.write_text(
        "\n".join(
            [
                "# Mission-Start Acceptance Smoke",
                "",
                f"- Status: `{status}`",
                f"- Mission: `{mission_id}`",
                f"- Launch mode: `{launch_mode}`",
                f"- Variant: `{variant}`",
                f"- Round dir: `{round_dir}`",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return {"json_path": str(json_path), "markdown_path": str(md_path)}
