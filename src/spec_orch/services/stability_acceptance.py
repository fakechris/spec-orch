from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from spec_orch.runtime_chain.store import read_chain_status
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


def _write_markdown(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _dataclass_payload(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    return value


def _latest_report(paths: list[Path]) -> dict[str, Any]:
    existing = [path for path in paths if path.exists()]
    if not existing:
        return {}
    latest = max(existing, key=lambda path: path.stat().st_mtime)
    payload = _read_json_object(latest)
    payload["_path"] = str(latest)
    return payload


def _runtime_chain_summary(chain_root: Path) -> dict[str, Any]:
    status = read_chain_status(chain_root)
    if status is None:
        return {}
    payload = status.to_dict()
    payload["chain_root"] = str(chain_root)
    return payload


def _augment_report_with_runtime_chain(
    report: dict[str, Any], *, check_name: str
) -> dict[str, Any]:
    if not report or report.get("runtime_chain"):
        return report
    path = str(report.get("_path", "")).strip()
    if check_name == "issue_start":
        workspace = str(report.get("workspace", "")).strip()
        if workspace:
            report["runtime_chain"] = _runtime_chain_summary(
                Path(workspace).resolve() / "telemetry" / "runtime_chain"
            )
        return report
    if path:
        operator_dir = Path(path).resolve().parent
        report["runtime_chain"] = _runtime_chain_summary(operator_dir / "runtime_chain")
    return report


def write_issue_start_acceptance_report(
    *,
    repo_root: Path,
    issue_id: str,
    fixture_issue_id: str,
    preflight_report: dict[str, Any],
    run_exit_code: int,
) -> dict[str, str]:
    repo_root = Path(repo_root).resolve()
    workspace = WorkspaceService(repo_root=repo_root).issue_workspace_path(issue_id)
    attempt = read_issue_execution_attempt(workspace)
    attempt_payload = _dataclass_payload(attempt) if attempt is not None else None
    attempt_status = ""
    if isinstance(attempt_payload, dict):
        outcome = attempt_payload.get("outcome", {})
        if isinstance(outcome, dict):
            attempt_status = str(outcome.get("status", "")).strip().lower()

    status = "fail"
    if (
        isinstance(preflight_report.get("summary"), dict)
        and int(preflight_report["summary"].get("fail", 0)) == 0
        and run_exit_code == 0
        and attempt_status == "succeeded"
    ):
        status = "pass"

    payload = {
        "status": status,
        "issue_id": issue_id,
        "fixture_issue_id": fixture_issue_id,
        "workspace": str(workspace),
        "preflight": preflight_report,
        "run_exit_code": run_exit_code,
        "attempt": attempt_payload,
        "runtime_chain": _runtime_chain_summary(workspace / "telemetry" / "runtime_chain"),
    }
    report_dir = repo_root / ".spec_orch" / "acceptance"
    json_path = report_dir / "issue_start_smoke.json"
    md_path = report_dir / "issue_start_smoke.md"
    _write_json(json_path, payload)
    _write_markdown(
        md_path,
        [
            "# Issue-Start Acceptance Smoke",
            "",
            f"- Status: `{status}`",
            f"- Issue: `{issue_id}`",
            f"- Fixture issue: `{fixture_issue_id}`",
            f"- Workspace: `{workspace}`",
            "",
        ],
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
        "runtime_chain": _runtime_chain_summary(
            repo_root / "docs" / "specs" / mission_id / "operator" / "runtime_chain"
        ),
    }
    operator_dir = repo_root / "docs" / "specs" / mission_id / "operator"
    json_path = operator_dir / "mission_start_acceptance.json"
    md_path = operator_dir / "mission_start_acceptance.md"
    _write_json(json_path, payload)
    _write_markdown(
        md_path,
        [
            "# Mission-Start Acceptance Smoke",
            "",
            f"- Status: `{status}`",
            f"- Mission: `{mission_id}`",
            f"- Launch mode: `{launch_mode}`",
            f"- Variant: `{variant}`",
            f"- Round dir: `{round_dir}`",
            "",
        ],
    )
    return {"json_path": str(json_path), "markdown_path": str(md_path)}


def write_dashboard_ui_acceptance_report(
    *,
    repo_root: Path,
    command: str,
    suite_summary: dict[str, Any],
) -> dict[str, str]:
    repo_root = Path(repo_root).resolve()
    status = str(suite_summary.get("status", "")).strip().lower() or "fail"
    payload = {
        "status": status,
        "command": command,
        "suite_summary": suite_summary,
    }
    report_dir = repo_root / ".spec_orch" / "acceptance"
    json_path = report_dir / "dashboard_ui_acceptance.json"
    md_path = report_dir / "dashboard_ui_acceptance.md"
    _write_json(json_path, payload)
    _write_markdown(
        md_path,
        [
            "# Dashboard UI Acceptance",
            "",
            f"- Status: `{status}`",
            f"- Command: `{command}`",
            "",
        ],
    )
    return {"json_path": str(json_path), "markdown_path": str(md_path)}


def write_exploratory_acceptance_report(
    *,
    repo_root: Path,
    mission_id: str,
    variant: str,
    round_dir: Path,
    source: str,
) -> dict[str, str]:
    repo_root = Path(repo_root).resolve()
    round_dir = Path(round_dir).resolve()
    acceptance_review = _read_json_object(round_dir / "acceptance_review.json")
    browser_evidence = _read_json_object(round_dir / "browser_evidence.json")
    fresh_report = _read_json_object(round_dir / "fresh_acpx_mission_e2e_report.json")
    review_status = str(acceptance_review.get("status", "")).strip().lower()
    status = "pass" if review_status == "pass" else "fail"
    payload = {
        "status": status,
        "mission_id": mission_id,
        "variant": variant,
        "source": source,
        "round_dir": str(round_dir),
        "acceptance_review": acceptance_review,
        "browser_evidence": browser_evidence,
        "fresh_report": fresh_report,
        "runtime_chain": _runtime_chain_summary(
            repo_root / "docs" / "specs" / mission_id / "operator" / "runtime_chain"
        ),
    }
    operator_dir = repo_root / "docs" / "specs" / mission_id / "operator"
    json_path = operator_dir / "exploratory_acceptance_smoke.json"
    md_path = operator_dir / "exploratory_acceptance_smoke.md"
    _write_json(json_path, payload)
    _write_markdown(
        md_path,
        [
            "# Exploratory Acceptance Smoke",
            "",
            f"- Status: `{status}`",
            f"- Mission: `{mission_id}`",
            f"- Variant: `{variant}`",
            f"- Source: `{source}`",
            f"- Round dir: `{round_dir}`",
            "",
        ],
    )
    return {"json_path": str(json_path), "markdown_path": str(md_path)}


def write_stability_acceptance_status(*, repo_root: Path) -> dict[str, str]:
    repo_root = Path(repo_root).resolve()
    acceptance_dir = repo_root / ".spec_orch" / "acceptance"
    specs_dir = repo_root / "docs" / "specs"

    mission_reports = list(specs_dir.glob("*/operator/mission_start_acceptance.json"))
    exploratory_reports = list(specs_dir.glob("*/operator/exploratory_acceptance_smoke.json"))

    checks = {
        "issue_start": _read_json_object(acceptance_dir / "issue_start_smoke.json"),
        "dashboard_ui": _read_json_object(acceptance_dir / "dashboard_ui_acceptance.json"),
        "mission_start": _latest_report(mission_reports),
        "exploratory": _latest_report(exploratory_reports),
    }
    checks = {
        name: _augment_report_with_runtime_chain(report, check_name=name)
        for name, report in checks.items()
    }

    statuses = [str(item.get("status", "")).strip().lower() for item in checks.values() if item]
    if not statuses:
        overall_status = "missing"
    elif any(status == "fail" for status in statuses):
        overall_status = "fail"
    elif all(status == "pass" for status in statuses):
        overall_status = "pass"
    else:
        overall_status = "partial"

    reported_checks = len([item for item in checks.values() if item])
    total_checks = len(checks)
    payload = {
        "summary": {
            "overall_status": overall_status,
            "reported_checks": reported_checks,
            "total_checks": total_checks,
        },
        "checks": checks,
    }

    issue_runtime_chain = checks["issue_start"].get("runtime_chain", {})
    mission_runtime_chain = checks["mission_start"].get("runtime_chain", {})
    exploratory_runtime_chain = checks["exploratory"].get("runtime_chain", {})

    json_path = acceptance_dir / "stability_acceptance_status.json"
    md_path = repo_root / "docs" / "plans" / "2026-03-30-stability-acceptance-status.md"
    _write_json(json_path, payload)
    _write_markdown(
        md_path,
        [
            "# Stability Acceptance Status",
            "",
            f"- Overall status: `{overall_status}`",
            f"- Reported checks: `{reported_checks}/{total_checks}`",
            "",
            "## Checks",
            "",
            f"- Issue Start: `{checks['issue_start'].get('status', 'missing')}`",
            f"  - Chain: `{issue_runtime_chain.get('phase', 'missing')}`"
            f" / `{issue_runtime_chain.get('status_reason', 'none')}`",
            f"- Mission Start: `{checks['mission_start'].get('status', 'missing')}`",
            f"  - Chain: `{mission_runtime_chain.get('phase', 'missing')}`"
            f" / `{mission_runtime_chain.get('status_reason', 'none')}`",
            f"- Dashboard UI: `{checks['dashboard_ui'].get('status', 'missing')}`",
            f"- Exploratory: `{checks['exploratory'].get('status', 'missing')}`",
            f"  - Chain: `{exploratory_runtime_chain.get('phase', 'missing')}`"
            f" / `{exploratory_runtime_chain.get('status_reason', 'none')}`",
            "",
        ],
    )
    return {"json_path": str(json_path), "markdown_path": str(md_path)}
