from __future__ import annotations

import json
import re
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from spec_orch.runtime_chain.store import read_chain_status
from spec_orch.runtime_core.readers import read_issue_execution_attempt
from spec_orch.services.env_files import resolve_shared_repo_root
from spec_orch.services.workspace_service import WorkspaceService

_ABSOLUTE_PATH_FRAGMENT_RE = re.compile(r"/[^\s`]+")


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


def _collapse_external_path(path: Path) -> str:
    parts = [part for part in path.parts if part and part != path.anchor]
    if not parts:
        return "<external-path>"
    tail = "/".join(parts[-3:])
    return f"<external-path>/{tail}"


def _looks_like_filesystem_path(path: Path) -> bool:
    parts = [part for part in path.parts if part and part != path.anchor]
    if not parts:
        return False
    return parts[0] in {
        "Users",
        "home",
        "private",
        "tmp",
        "var",
        "opt",
        "etc",
    }


def _sanitize_path_like_string(
    value: str,
    *,
    repo_root: Path,
    shared_root: Path | None,
) -> str:
    repo_root_str = repo_root.as_posix()
    if value == repo_root_str:
        return "."

    sanitized = value.replace(f"{repo_root_str}/", "")
    if shared_root is not None:
        shared_root_str = shared_root.resolve().as_posix()
        if sanitized == shared_root_str:
            sanitized = "<shared-repo>"
        sanitized = sanitized.replace(f"{shared_root_str}/", "<shared-repo>/")

    def _replace_external_fragment(match: re.Match[str]) -> str:
        fragment = match.group(0)
        candidate = Path(fragment)
        if not (candidate.is_absolute() and _looks_like_filesystem_path(candidate)):
            return fragment
        return _collapse_external_path(candidate)

    sanitized = _ABSOLUTE_PATH_FRAGMENT_RE.sub(_replace_external_fragment, sanitized)

    stripped = sanitized.strip()
    if stripped and stripped == sanitized:
        candidate = Path(stripped)
        if candidate.is_absolute() and _looks_like_filesystem_path(candidate):
            return _collapse_external_path(candidate)
    return sanitized


def _sanitize_acceptance_value(
    value: Any,
    *,
    repo_root: Path,
    shared_root: Path | None,
) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _sanitize_acceptance_value(
                item,
                repo_root=repo_root,
                shared_root=shared_root,
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _sanitize_acceptance_value(item, repo_root=repo_root, shared_root=shared_root)
            for item in value
        ]
    if isinstance(value, str):
        return _sanitize_path_like_string(
            value,
            repo_root=repo_root,
            shared_root=shared_root,
        )
    return value


def _sanitized_payload(value: Any, *, repo_root: Path) -> Any:
    shared_root = resolve_shared_repo_root(repo_root)
    return _sanitize_acceptance_value(
        value,
        repo_root=repo_root.resolve(),
        shared_root=shared_root.resolve() if shared_root is not None else None,
    )


def _sanitized_lines(lines: list[str], *, repo_root: Path) -> list[str]:
    shared_root = resolve_shared_repo_root(repo_root)
    return [
        _sanitize_path_like_string(
            line,
            repo_root=repo_root.resolve(),
            shared_root=shared_root.resolve() if shared_root is not None else None,
        )
        for line in lines
    ]


def _latest_report(paths: list[Path]) -> dict[str, Any]:
    existing = [path for path in paths if path.exists()]
    if not existing:
        return {}
    latest = max(existing, key=lambda path: path.stat().st_mtime)
    payload = _read_json_object(latest)
    payload["_path"] = str(latest)
    return payload


def _direct_report(path: Path) -> dict[str, Any]:
    payload = _read_json_object(path)
    if payload:
        payload["_path"] = str(path)
    return payload


def _latest_available_report(*paths: Path) -> dict[str, Any]:
    return _latest_report(list(paths))


def _runtime_chain_summary(chain_root: Path) -> dict[str, Any]:
    status = read_chain_status(chain_root)
    if status is None:
        return {}
    payload = status.to_dict()
    payload["chain_root"] = str(chain_root)
    return payload


def _normalize_acceptance_status(value: Any) -> str:
    normalized = str(value).strip().lower()
    if normalized in {"pass", "warn", "fail", "partial"}:
        return normalized
    return "missing" if not normalized else "fail"


def _combined_text_fields(item: dict[str, Any], *, include_title: bool = False) -> str:
    text_parts = [
        str(item.get("summary", "")),
        str(item.get("details", "")),
        str(item.get("actual", "")),
        str(item.get("expected", "")),
        str(item.get("why_it_matters", "")),
        str(item.get("hold_reason", "")),
    ]
    if include_title:
        text_parts.append(str(item.get("title", "")))
    return " ".join(part.strip().lower() for part in text_parts if part).strip()


def _classify_acceptance_bug_type(item: dict[str, Any], *, include_title: bool = False) -> str:
    critique_axis = str(item.get("critique_axis", "")).strip().lower()
    route = str(item.get("route", "")).strip()
    text = _combined_text_fields(item, include_title=include_title)
    if critique_axis in {"broken_flow", "workflow_break", "page_error", "regression"} or any(
        marker in text
        for marker in (
            "page error",
            "blocked",
            "broken",
            "cannot ",
            "can't ",
            "unable to",
            "fails to",
            "crash",
            "exception",
            "regression",
        )
    ):
        return "n2n_bug" if route else "harness_bug"
    harness_axes = {
        "acceptance_harness",
        "evaluation_config",
        "model_config",
        "runtime_chain",
        "report_normalization",
    }
    if critique_axis in harness_axes or any(
        marker in text
        for marker in (
            "acceptance evaluator",
            "exploratory critique",
            "provider configuration",
            "api base",
            "api key",
            "runtime chain",
            "harness configuration",
        )
    ):
        return "harness_bug"
    if route:
        return "ux_gap"
    return "ux_gap"


def _finding_taxonomy(
    findings: Any,
    issue_proposals: Any,
) -> dict[str, Any]:
    classified_findings: list[dict[str, Any]] = []
    classified_issue_proposals: list[dict[str, Any]] = []
    counts = {"harness_bug": 0, "n2n_bug": 0, "ux_gap": 0}

    if isinstance(findings, list):
        for item in findings:
            if not isinstance(item, dict):
                continue
            bug_type = _classify_acceptance_bug_type(item)
            counts[bug_type] += 1
            classified_findings.append({**item, "bug_type": bug_type})

    if isinstance(issue_proposals, list):
        for item in issue_proposals:
            if not isinstance(item, dict):
                continue
            bug_type = _classify_acceptance_bug_type(item, include_title=True)
            counts[bug_type] += 1
            classified_issue_proposals.append({**item, "bug_type": bug_type})

    return {
        "counts": counts,
        "findings": classified_findings,
        "issue_proposals": classified_issue_proposals,
    }


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
    builder_succeeded = False
    verification_succeeded = False
    if isinstance(attempt_payload, dict):
        outcome = attempt_payload.get("outcome", {})
        if isinstance(outcome, dict):
            attempt_status = str(outcome.get("status", "")).strip().lower()
            build = outcome.get("build", {})
            if isinstance(build, dict):
                builder_succeeded = build.get("succeeded") is True
            verification = outcome.get("verification", {})
            if isinstance(verification, dict):
                verification_succeeded = all(
                    isinstance(step_cfg, dict) and int(step_cfg.get("exit_code", 1)) == 0
                    for step_cfg in verification.values()
                )

    status = "fail"
    if (
        isinstance(preflight_report.get("summary"), dict)
        and int(preflight_report["summary"].get("fail", 0)) == 0
        and run_exit_code == 0
        and (attempt_status == "succeeded" or (builder_succeeded and verification_succeeded))
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
    _write_json(json_path, _sanitized_payload(payload, repo_root=repo_root))
    _write_markdown(
        md_path,
        _sanitized_lines(
            [
                "# Issue-Start Acceptance Smoke",
                "",
                f"- Status: `{status}`",
                f"- Issue: `{issue_id}`",
                f"- Fixture issue: `{fixture_issue_id}`",
                f"- Workspace: `{workspace}`",
                "",
            ],
            repo_root=repo_root,
        ),
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
    _write_json(json_path, _sanitized_payload(payload, repo_root=repo_root))
    _write_markdown(
        md_path,
        _sanitized_lines(
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
            repo_root=repo_root,
        ),
    )
    return {"json_path": str(json_path), "markdown_path": str(md_path)}


def write_mission_start_acceptance_failure_report(
    *,
    repo_root: Path,
    launch_mode: str,
    variant: str,
    failure_reason: str,
    mission_id: str = "",
) -> dict[str, str]:
    repo_root = Path(repo_root).resolve()
    acceptance_dir = repo_root / ".spec_orch" / "acceptance"
    payload = {
        "status": "fail",
        "mission_id": mission_id,
        "launch_mode": launch_mode,
        "variant": variant,
        "failure_reason": failure_reason,
        "runtime_chain": {},
    }
    json_path = acceptance_dir / "mission_start_acceptance.json"
    md_path = acceptance_dir / "mission_start_acceptance.md"
    _write_json(json_path, _sanitized_payload(payload, repo_root=repo_root))
    _write_markdown(
        md_path,
        _sanitized_lines(
            [
                "# Mission-Start Acceptance Smoke",
                "",
                "- Status: `fail`",
                f"- Launch mode: `{launch_mode}`",
                f"- Variant: `{variant}`",
                f"- Failure reason: `{failure_reason}`",
                "",
            ],
            repo_root=repo_root,
        ),
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
    _write_json(json_path, _sanitized_payload(payload, repo_root=repo_root))
    _write_markdown(
        md_path,
        _sanitized_lines(
            [
                "# Dashboard UI Acceptance",
                "",
                f"- Status: `{status}`",
                f"- Command: `{command}`",
                "",
            ],
            repo_root=repo_root,
        ),
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
    exploratory_review = _read_json_object(round_dir / "exploratory_acceptance_review.json")
    acceptance_review = exploratory_review or _read_json_object(
        round_dir / "acceptance_review.json"
    )
    review_path = (
        round_dir / "exploratory_acceptance_review.json"
        if exploratory_review
        else round_dir / "acceptance_review.json"
    )
    browser_evidence = _read_json_object(round_dir / "exploratory_browser_evidence.json")
    if not browser_evidence:
        browser_evidence = _read_json_object(round_dir / "browser_evidence.json")
    fresh_report = _read_json_object(round_dir / "fresh_acpx_mission_e2e_report.json")
    review_status = _normalize_acceptance_status(acceptance_review.get("status", ""))
    status = review_status
    summary = str(acceptance_review.get("summary", "")).strip()
    findings = acceptance_review.get("findings", [])
    issue_proposals = acceptance_review.get("issue_proposals", [])
    findings_count = len(findings) if isinstance(findings, list) else 0
    issue_proposal_count = len(issue_proposals) if isinstance(issue_proposals, list) else 0
    recommended_next_step = str(acceptance_review.get("recommended_next_step", "")).strip()
    acceptance_mode = str(acceptance_review.get("acceptance_mode", "")).strip()
    review_coverage = str(acceptance_review.get("coverage_status", "")).strip()
    fresh_review = fresh_report.get("acceptance_review", {})
    fresh_coverage = ""
    if isinstance(fresh_review, dict):
        fresh_coverage = str(fresh_review.get("coverage_status", "")).strip()
    coverage_status = review_coverage or fresh_coverage
    finding_taxonomy = _finding_taxonomy(findings, issue_proposals)
    payload = {
        "status": status,
        "summary": summary,
        "mission_id": mission_id,
        "variant": variant,
        "source": source,
        "source_run": {
            "mission_id": mission_id,
            "round_id": round_dir.name,
            "round_dir": str(round_dir),
            "review_path": str(review_path),
            "source": source,
        },
        "round_dir": str(round_dir),
        "findings_count": findings_count,
        "issue_proposal_count": issue_proposal_count,
        "recommended_next_step": recommended_next_step,
        "acceptance_mode": acceptance_mode,
        "coverage_status": coverage_status,
        "finding_taxonomy": finding_taxonomy,
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
    _write_json(json_path, _sanitized_payload(payload, repo_root=repo_root))
    _write_markdown(
        md_path,
        _sanitized_lines(
            [
                "# Exploratory Acceptance Smoke",
                "",
                f"- Status: `{status}`",
                (f"- Summary: {summary}" if summary else "- Summary: `none`"),
                f"- Mission: `{mission_id}`",
                f"- Variant: `{variant}`",
                f"- Source: `{source}`",
                f"- Round dir: `{round_dir}`",
                f"- Findings: `{findings_count}`",
                f"- Issue proposals: `{issue_proposal_count}`",
                (
                    f"- Bug taxonomy: `harness_bug={finding_taxonomy['counts']['harness_bug']}`, "
                    f"`n2n_bug={finding_taxonomy['counts']['n2n_bug']}`, "
                    f"`ux_gap={finding_taxonomy['counts']['ux_gap']}`"
                ),
                (
                    f"- Recommended next step: `{recommended_next_step}`"
                    if recommended_next_step
                    else "- Recommended next step: `none`"
                ),
                "",
            ],
            repo_root=repo_root,
        ),
    )
    return {"json_path": str(json_path), "markdown_path": str(md_path)}


def write_exploratory_acceptance_failure_report(
    *,
    repo_root: Path,
    mission_id: str,
    variant: str,
    source: str,
    failure_reason: str,
) -> dict[str, str]:
    repo_root = Path(repo_root).resolve()
    acceptance_dir = repo_root / ".spec_orch" / "acceptance"
    payload = {
        "status": "fail",
        "summary": failure_reason,
        "mission_id": mission_id,
        "variant": variant,
        "source": source,
        "runtime_chain": {},
    }
    json_path = acceptance_dir / "exploratory_acceptance_smoke.json"
    md_path = acceptance_dir / "exploratory_acceptance_smoke.md"
    _write_json(json_path, _sanitized_payload(payload, repo_root=repo_root))
    _write_markdown(
        md_path,
        _sanitized_lines(
            [
                "# Exploratory Acceptance Smoke",
                "",
                "- Status: `fail`",
                f"- Summary: `{failure_reason}`",
                f"- Variant: `{variant}`",
                f"- Source: `{source}`",
                "",
            ],
            repo_root=repo_root,
        ),
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
        "mission_start": _latest_available_report(
            acceptance_dir / "mission_start_acceptance.json",
            *mission_reports,
        ),
        "exploratory": _latest_available_report(
            acceptance_dir / "exploratory_acceptance_smoke.json",
            *exploratory_reports,
        ),
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
    _write_json(json_path, _sanitized_payload(payload, repo_root=repo_root))
    _write_markdown(
        md_path,
        _sanitized_lines(
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
            repo_root=repo_root,
        ),
    )
    return {"json_path": str(json_path), "markdown_path": str(md_path)}
