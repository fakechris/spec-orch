from __future__ import annotations

import inspect
import json
import os
import time
import tomllib
from dataclasses import replace
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError
from urllib.request import urlopen

from spec_orch.domain.models import AcceptanceFinding, AcceptanceReviewResult
from spec_orch.services.acceptance.browser_evidence import collect_playwright_browser_evidence
from spec_orch.services.litellm_profile import resolve_role_litellm_settings


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _load_raw_config(repo_root: Path) -> dict[str, Any]:
    config_path = Path(repo_root) / "spec-orch.toml"
    if not config_path.exists():
        return {}
    try:
        with config_path.open("rb") as handle:
            raw = tomllib.load(handle)
    except (FileNotFoundError, tomllib.TOMLDecodeError, OSError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _resolve_exploratory_acceptance_settings(repo_root: Path) -> dict[str, Any]:
    raw = _load_raw_config(repo_root)
    cfg = raw.get("acceptance_evaluator", {})
    if not isinstance(cfg, dict):
        cfg = {}
    settings = resolve_role_litellm_settings(
        raw,
        section_name="acceptance_evaluator",
        default_model=str(cfg.get("model", "MiniMax-M2.7-highspeed")).strip()
        or "MiniMax-M2.7-highspeed",
        default_api_type=str(cfg.get("api_type", "anthropic")).strip().lower() or "anthropic",
    )
    return {
        "adapter": str(cfg.get("adapter", "litellm")).strip() or "litellm",
        "model": settings["model"],
        "api_type": settings["api_type"],
        "api_key_env": settings["api_key_env"],
        "api_base_env": settings["api_base_env"],
        "api_key": settings["api_key"],
        "api_base": settings["api_base"],
        "model_chain": settings["model_chain"],
    }


def _exploratory_acceptance_config_error(settings: dict[str, Any]) -> AcceptanceReviewResult | None:
    api_type = str(settings.get("api_type", "")).strip().lower()
    model = str(settings.get("model", "")).strip()
    api_key = str(settings.get("api_key", "")).strip()
    api_base = str(settings.get("api_base", "")).strip()
    api_base_env = str(settings.get("api_base_env", "")).strip() or "SPEC_ORCH_LLM_API_BASE"
    model_name = model.split("/", 1)[1] if "/" in model else model
    needs_minimax_base = api_type == "anthropic" and model_name.lower().startswith("minimax-")
    if not (needs_minimax_base and api_key and not api_base):
        return None
    detail = (
        "Resolved acceptance evaluator settings require an anthropic-compatible API base, "
        f"but none was found. model={model!r}, api_type={api_type!r}, "
        f"api_key_present={bool(api_key)}, api_base_env={api_base_env!r}. "
        "Set MINIMAX_ANTHROPIC_BASE_URL or SPEC_ORCH_LLM_API_BASE before rerunning "
        "exploratory critique."
    )
    return AcceptanceReviewResult(
        status="warn",
        summary="Exploratory acceptance configuration is incomplete.",
        confidence=0.98,
        evaluator="exploratory_acceptance_config_guard",
        findings=[
            AcceptanceFinding(
                severity="high",
                summary="Acceptance evaluator configuration is incomplete.",
                details=detail,
                why_it_matters=(
                    "The second-stage exploratory critique cannot produce product findings "
                    "until its provider configuration is valid."
                ),
            )
        ],
        artifacts={
            "acceptance_evaluator_config": {
                "model": model,
                "api_type": api_type,
                "api_key_present": bool(api_key),
                "api_base_present": bool(api_base),
                "api_base_env": api_base_env,
                "config_error": "missing_api_base",
            }
        },
        acceptance_mode="exploratory",
        coverage_status="partial",
        recommended_next_step=(
            "Set the acceptance evaluator API base and rerun exploratory critique."
        ),
    )


def _finalize_exploratory_campaign(campaign: Any) -> Any:
    critique_focus = list(getattr(campaign, "critique_focus", []) or [])
    if not critique_focus:
        critique_focus = [
            "evidence_discoverability",
            "task_continuity",
            "operator_confidence",
            "information_hierarchy",
        ]
    filing_policy = getattr(campaign, "filing_policy", "") or ""
    if filing_policy == "auto_file_broken_flows_only":
        filing_policy = "hold_ux_concerns_for_operator_review"
    exploration_budget = getattr(campaign, "exploration_budget", "") or ""
    if exploration_budget == "bounded":
        exploration_budget = "wide"
    return replace(
        campaign,
        critique_focus=critique_focus,
        filing_policy=filing_policy,
        exploration_budget=exploration_budget,
    )


def _collect_exploratory_browser_evidence(
    *,
    mission_id: str,
    round_id: int,
    round_dir: Path,
    campaign: Any,
) -> dict[str, Any] | None:
    if not os.environ.get("SPEC_ORCH_VISUAL_EVAL_URL", "").strip():
        return None
    routes = list(getattr(campaign, "primary_routes", []) or [])
    related_routes = list(getattr(campaign, "related_routes", []) or [])
    related_route_budget = int(getattr(campaign, "related_route_budget", 0) or 0)
    if related_route_budget > 0:
        routes.extend(related_routes[:related_route_budget])
    else:
        routes.extend(related_routes)
    if not routes:
        return None
    return collect_playwright_browser_evidence(
        mission_id=mission_id,
        round_id=round_id,
        round_dir=round_dir,
        paths=routes,
        interaction_plans=dict(getattr(campaign, "interaction_plans", {}) or {}),
        output_name="exploratory_browser_evidence.json",
    )


def _existing_browser_evidence_covers_campaign(
    browser_evidence: dict[str, Any],
    campaign: Any,
) -> bool:
    tested_routes = browser_evidence.get("tested_routes")
    if not isinstance(tested_routes, list) or not tested_routes:
        return False
    covered_routes = {str(route).strip() for route in tested_routes if str(route).strip()}
    if not covered_routes:
        return False
    required_routes = set(getattr(campaign, "primary_routes", []) or [])
    related_routes = list(getattr(campaign, "related_routes", []) or [])
    related_route_budget = int(getattr(campaign, "related_route_budget", 0) or 0)
    if related_route_budget > 0:
        required_routes.update(related_routes[:related_route_budget])
    else:
        required_routes.update(related_routes)
    return required_routes.issubset(covered_routes)


def _build_execution_lifecycle_manager(repo_root: Path) -> Any:
    from spec_orch.dashboard.launcher import _build_execution_lifecycle_manager as _build_manager

    return _build_manager(repo_root)


def _invoke_supported_kwargs(func: Any, **kwargs: Any) -> Any:
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return func(**kwargs)
    supported_kwargs = {
        name: value for name, value in kwargs.items() if name in signature.parameters
    }
    return func(**supported_kwargs)


def _probe_dashboard(url: str, timeout_seconds: float) -> dict[str, Any]:
    try:
        with urlopen(url, timeout=timeout_seconds) as response:
            return {
                "url": url,
                "status": getattr(response, "status", None),
            }
    except HTTPError as exc:
        return {
            "url": url,
            "status": exc.code,
        }


def wait_for_dashboard_ready(
    base_url: str,
    *,
    timeout_seconds: float = 20.0,
    poll_interval_seconds: float = 0.5,
    probe_timeout_seconds: float = 2.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    attempts = 0
    last_error = ""
    while True:
        attempts += 1
        try:
            payload = _probe_dashboard(base_url, probe_timeout_seconds)
            status = int(payload.get("status") or 0)
            if 200 <= status < 500:
                return {
                    "ready": True,
                    "attempts": attempts,
                    "status": status,
                    "url": base_url,
                }
            last_error = f"unexpected status={status}"
        except HTTPError as exc:
            status = int(exc.code)
            if 200 <= status < 500:
                return {
                    "ready": True,
                    "attempts": attempts,
                    "status": status,
                    "url": base_url,
                }
            last_error = f"unexpected status={status}"
        except Exception as exc:
            last_error = str(exc)
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Dashboard never became ready at {base_url}: {last_error}")
        time.sleep(poll_interval_seconds)


def run_fresh_launch_and_pickup(*, repo_root: Path, mission_id: str) -> dict[str, Any]:
    from spec_orch.dashboard.launcher import _launch_mission

    operator_dir = repo_root / "docs" / "specs" / mission_id / "operator"
    operator_dir.mkdir(parents=True, exist_ok=True)
    launch_result = _launch_mission(repo_root, mission_id, allow_background_runner=False)
    runner_status = str(launch_result.get("launch", {}).get("runner", {}).get("status", "")).strip()
    daemon_run = None
    if runner_status == "foreground_required":
        daemon_run = run_fresh_execution_once(repo_root=repo_root, mission_id=mission_id)
    payload = {
        "mission_id": mission_id,
        "proof_type": "fresh_launch_pickup",
        "launch_result": launch_result,
        "daemon_run": daemon_run,
    }
    _write_json(operator_dir / "launch_pickup.json", payload)
    return payload


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
        len(wave.get("work_packets", [])) for wave in waves if isinstance(wave, dict)
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
        "launch_phase": str(launch.get("last_launch", {}).get("state", {}).get("phase", "")).strip()
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


def build_fresh_exploratory_artifacts(
    *,
    repo_root: Path,
    mission_id: str,
    round_dir: Path,
    mission_payload: dict[str, Any],
    browser_evidence: dict[str, Any],
) -> dict[str, Any]:
    artifacts: dict[str, Any] = {
        "mission": dict(mission_payload),
        "browser_evidence": dict(browser_evidence),
    }
    report_payload = _read_json(round_dir / "fresh_acpx_mission_e2e_report.json")
    if report_payload:
        artifacts["fresh_acpx_mission_e2e_report"] = report_payload
        fresh_execution = report_payload.get("fresh_execution")
        workflow_replay = report_payload.get("workflow_replay")
        if isinstance(fresh_execution, dict) and fresh_execution:
            artifacts["fresh_execution"] = fresh_execution
        if isinstance(workflow_replay, dict) and workflow_replay:
            artifacts["workflow_replay"] = workflow_replay
            review_routes = workflow_replay.get("review_routes")
            if isinstance(review_routes, dict) and review_routes:
                artifacts["review_routes"] = review_routes
            workflow_assertions = workflow_replay.get("workflow_assertions")
            if isinstance(workflow_assertions, list) and workflow_assertions:
                artifacts["workflow_assertions"] = workflow_assertions
        if "fresh_execution" in artifacts and "workflow_replay" in artifacts:
            artifacts["proof_split"] = {
                "fresh_execution": artifacts["fresh_execution"],
                "workflow_replay": artifacts["workflow_replay"],
            }

    prior_acceptance = _read_json(round_dir / "acceptance_review.json")
    if prior_acceptance:
        artifacts["workflow_acceptance_review"] = prior_acceptance
    round_summary = _read_json(round_dir / "round_summary.json")
    if round_summary:
        artifacts["round_summary"] = round_summary

    return artifacts


def run_fresh_exploratory_acceptance_review(
    *,
    repo_root: Path,
    mission_id: str,
    round_dir: Path,
    mission_payload: dict[str, Any],
    browser_evidence: dict[str, Any],
) -> dict[str, Any]:
    from spec_orch.domain.models import AcceptanceMode
    from spec_orch.services.acceptance.litellm_acceptance_evaluator import (
        LiteLLMAcceptanceEvaluator,
    )
    from spec_orch.services.round_orchestrator import RoundOrchestrator

    repo_root = Path(repo_root).resolve()
    round_dir = Path(round_dir).resolve()
    artifacts = build_fresh_exploratory_artifacts(
        repo_root=repo_root,
        mission_id=mission_id,
        round_dir=round_dir,
        mission_payload=mission_payload,
        browser_evidence=browser_evidence,
    )
    orchestrator = RoundOrchestrator(
        repo_root=repo_root,
        supervisor=cast(Any, object()),
        worker_factory=cast(Any, object()),
        context_assembler=cast(Any, object()),
    )
    campaign = orchestrator._build_acceptance_campaign(
        mission_id=mission_id,
        artifacts=artifacts,
        mode_override=AcceptanceMode.EXPLORATORY,
    )
    campaign = _finalize_exploratory_campaign(campaign)

    round_summary = _read_json(round_dir / "round_summary.json")
    raw_round_id = round_summary.get("round_id")
    try:
        round_id = int(str(raw_round_id))
    except (TypeError, ValueError):
        try:
            round_id = int(str(round_dir.name).split("-")[-1])
        except (TypeError, ValueError):
            round_id = 0

    settings = _resolve_exploratory_acceptance_settings(repo_root)
    config_error = _exploratory_acceptance_config_error(settings)
    if config_error is not None:
        payload = config_error.to_dict()
        _write_json(round_dir / "exploratory_acceptance_review.json", payload)
        return payload

    prior_browser_evidence = artifacts.get("browser_evidence")
    should_recollect_browser_evidence = not (
        isinstance(prior_browser_evidence, dict)
        and prior_browser_evidence
        and _existing_browser_evidence_covers_campaign(prior_browser_evidence, campaign)
    )
    if should_recollect_browser_evidence:
        refreshed_browser_evidence = _collect_exploratory_browser_evidence(
            mission_id=mission_id,
            round_id=round_id,
            round_dir=round_dir,
            campaign=campaign,
        )
        if refreshed_browser_evidence is not None:
            if isinstance(prior_browser_evidence, dict) and prior_browser_evidence:
                artifacts["workflow_browser_evidence"] = dict(prior_browser_evidence)
            artifacts["browser_evidence"] = refreshed_browser_evidence

    evaluator = _invoke_supported_kwargs(
        LiteLLMAcceptanceEvaluator,
        repo_root=repo_root,
        model=str(settings["model"]),
        api_type=str(settings["api_type"]),
        api_key=str(settings["api_key"]) or None,
        api_base=str(settings["api_base"]) or None,
        model_chain=settings.get("model_chain"),
    )
    result = evaluator.evaluate_acceptance(
        mission_id=mission_id,
        round_id=round_id,
        round_dir=round_dir,
        worker_results=[],
        artifacts=artifacts,
        repo_root=repo_root,
        campaign=campaign,
    )
    payload = result.to_dict()
    if not isinstance(payload, dict):
        payload = {}
    acceptance_config = payload.setdefault("artifacts", {}).setdefault(
        "acceptance_evaluator_config",
        {},
    )
    if isinstance(acceptance_config, dict):
        acceptance_config.setdefault("model", str(settings["model"]))
        acceptance_config.setdefault("api_type", str(settings["api_type"]))
        acceptance_config.setdefault("api_key_present", bool(str(settings["api_key"]).strip()))
        acceptance_config.setdefault("api_base_present", bool(str(settings["api_base"]).strip()))
        acceptance_config.setdefault("api_base_env", str(settings["api_base_env"]))
    _write_json(round_dir / "exploratory_acceptance_review.json", payload)
    return payload


def write_fresh_acpx_mission_report(
    *,
    round_dir: Path,
    mission_id: str,
    dashboard_url: str,
    fresh_execution: dict[str, Any],
    workflow_replay: dict[str, Any],
    acceptance_review: AcceptanceReviewResult,
) -> dict[str, Any]:
    bootstrap = fresh_execution.get("mission_bootstrap", {})
    metadata = bootstrap.get("metadata", {}) if isinstance(bootstrap, dict) else {}
    variant = str(metadata.get("fresh_variant", "default")).strip() or "default"
    report_payload = {
        "mission_id": mission_id,
        "variant": variant,
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
            f"- Variant: `{variant}`",
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
