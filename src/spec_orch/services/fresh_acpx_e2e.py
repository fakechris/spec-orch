from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from spec_orch.domain.models import AcceptanceReviewResult


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _build_execution_lifecycle_manager(repo_root: Path) -> Any:
    from spec_orch.dashboard.launcher import _build_execution_lifecycle_manager as _build_manager

    return _build_manager(repo_root)


def run_fresh_execution_once(*, repo_root: Path, mission_id: str) -> dict[str, Any]:
    operator_dir = repo_root / "docs" / "specs" / mission_id / "operator"
    operator_dir.mkdir(parents=True, exist_ok=True)
    manager = _build_execution_lifecycle_manager(repo_root)
    state = manager.auto_advance(mission_id)
    payload = {
        "mission_id": mission_id,
        "proof_type": "fresh_execution",
        "runner_status": "finished" if state is not None else "no_state",
        "state": state.to_dict() if state is not None else {},
    }
    _write_json(operator_dir / "daemon_run.json", payload)
    return payload


def assert_fresh_plan_budget(
    plan_payload: dict[str, Any],
    *,
    max_waves: int,
    max_packets: int,
) -> dict[str, int]:
    waves = list(plan_payload.get("waves", []))
    packet_count = sum(
        len(wave.get("work_packets", []))
        for wave in waves
        if isinstance(wave, dict)
    )
    summary = {
        "wave_count": len(waves),
        "packet_count": packet_count,
    }
    if summary["wave_count"] > max_waves or summary["packet_count"] > max_packets:
        raise ValueError(
            "Fresh plan exceeded budget: "
            f"wave_count={summary['wave_count']} max_waves={max_waves}, "
            f"packet_count={summary['packet_count']} max_packets={max_packets}"
        )
    return summary


def materialize_fresh_execution_artifacts(
    *,
    repo_root: Path,
    mission_id: str,
    round_dir: Path,
    launch_result: dict[str, Any],
) -> dict[str, Any]:
    operator_dir = repo_root / "docs" / "specs" / mission_id / "operator"
    operator_dir.mkdir(parents=True, exist_ok=True)

    mission_bootstrap = _read_json(operator_dir / "mission_bootstrap.json")
    launch = _read_json(operator_dir / "launch.json")
    round_summary = _read_json(round_dir / "round_summary.json")
    builder_execution_summary = {
        "round_id": round_summary.get("round_id"),
        "status": round_summary.get("status"),
        "worker_results": list(round_summary.get("worker_results", [])),
    }
    daemon_run = {
        "mission_id": mission_id,
        "proof_type": "fresh_execution",
        "fresh_round_path": str(round_dir),
        "runner_status": (
            str(launch.get("runner", {}).get("status", "")).strip()
            or ("started" if launch_result.get("background_runner_started") else "unknown")
        ),
        "launch_phase": str(
            launch.get("last_launch", {}).get("state", {}).get("phase", "")
        ).strip()
        or str(launch_result.get("state", {}).get("phase", "")).strip(),
    }

    _write_json(operator_dir / "daemon_run.json", daemon_run)
    _write_json(round_dir / "fresh_round_summary.json", round_summary)
    _write_json(round_dir / "builder_execution_summary.json", builder_execution_summary)

    return {
        "proof_type": "fresh_execution",
        "mission_bootstrap": mission_bootstrap,
        "launch": launch,
        "daemon_run": daemon_run,
        "fresh_round_path": str(round_dir),
        "builder_execution_summary": builder_execution_summary,
    }


def write_fresh_acpx_mission_report(
    *,
    round_dir: Path,
    mission_id: str,
    dashboard_url: str,
    fresh_execution: dict[str, Any],
    workflow_replay: dict[str, Any],
    acceptance_review: AcceptanceReviewResult,
) -> dict[str, Any]:
    report_payload = {
        "mission_id": mission_id,
        "dashboard_url": dashboard_url,
        "fresh_execution": fresh_execution,
        "workflow_replay": workflow_replay,
        "acceptance_review": acceptance_review.to_dict(),
        "remaining_gaps": [
            "Fresh proof still does not establish provider-agnostic portability.",
            "Fresh proof covers one narrow path until more fresh mission scenarios are added.",
        ],
    }

    daemon_round_path = fresh_execution.get("daemon_run", {}).get("fresh_round_path", "")
    builder_packets = len(
        fresh_execution.get("builder_execution_summary", {}).get("worker_results", [])
    )
    markdown = "\n".join(
        [
            f"# Fresh Acpx Mission E2E Report: {mission_id}",
            "",
            "## Fresh Execution Proof",
            "",
            f"- Fresh round path: `{fresh_execution.get('fresh_round_path', '')}`",
            f"- Daemon pickup evidence: `{daemon_round_path}`",
            f"- Builder packets observed: `{builder_packets}`",
            "",
            "## Workflow Replay Proof",
            "",
            f"- Dashboard URL: `{dashboard_url}`",
            f"- Acceptance status: `{acceptance_review.status}`",
            f"- Coverage status: `{acceptance_review.coverage_status}`",
            f"- Tested routes: `{len(acceptance_review.tested_routes)}`",
            "",
            "## Remaining Gaps",
            "",
            "- Provider portability remains unproven by this single fresh path.",
            "- Additional fresh mission variants are still needed before broader claims.",
            "",
        ]
    )

    markdown_path = round_dir / "fresh_acpx_mission_e2e_report.md"
    markdown_path.write_text(markdown + "\n", encoding="utf-8")
    json_path = round_dir / "fresh_acpx_mission_e2e_report.json"
    _write_json(json_path, report_payload)

    return {
        "mission_id": mission_id,
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
    }
