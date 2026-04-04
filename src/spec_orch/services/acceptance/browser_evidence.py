from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from spec_orch.domain.models import AcceptanceInteractionStep
from spec_orch.services.io import atomic_write_json
from spec_orch.services.visual.playwright_visual_eval import (
    PageSnapshot,
    VisualEvalRequest,
    capture_page_snapshots,
)

logger = logging.getLogger(__name__)


def _step_marker_for_status(status: str) -> str:
    normalized = status.strip().lower()
    if normalized == "failed":
        return "STEP_FAIL"
    if normalized == "skipped":
        return "STEP_SKIP"
    return "STEP_PASS"


def _expected_for_interaction(entry: dict[str, Any]) -> str:
    description = str(entry.get("description", "") or "").strip()
    if description:
        return description
    action = str(entry.get("action", "") or "").strip()
    target = str(entry.get("target", "") or "").strip()
    if action and target:
        return f"{action} {target}"
    if target:
        return target
    return "Interaction completes successfully."


def _actual_for_interaction(entry: dict[str, Any], *, status: str) -> str:
    message = str(entry.get("message", "") or "").strip()
    if message:
        return message
    normalized = status.strip().lower()
    if normalized == "failed":
        return "Step failed."
    if normalized == "skipped":
        return "Skipped."
    return "Step completed."


def _normalize_interaction_log(
    steps: list[dict[str, Any]],
    *,
    screenshot_path: Path,
) -> list[dict[str, Any]]:
    normalized_steps: list[dict[str, Any]] = []
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            continue
        status = str(step.get("status", "passed") or "passed").strip().lower() or "passed"
        step_id = str(step.get("step_id", "") or f"step-{index:02d}").strip() or f"step-{index:02d}"
        marker = str(step.get("marker", "") or _step_marker_for_status(status)).strip()
        normalized_step = dict(step)
        normalized_step["status"] = status
        normalized_step["step_id"] = step_id
        normalized_step["marker"] = marker
        normalized_step["expected"] = str(
            step.get("expected", "") or _expected_for_interaction(step)
        ).strip()
        normalized_step["actual"] = str(
            step.get("actual", "") or _actual_for_interaction(step, status=status)
        ).strip()
        normalized_step["screenshot_path"] = str(
            step.get("screenshot_path", "") or str(screenshot_path)
        ).strip()
        normalized_step["before_snapshot_ref"] = str(
            step.get("before_snapshot_ref", "") or f"{step_id}:before"
        ).strip()
        normalized_step["after_snapshot_ref"] = str(
            step.get("after_snapshot_ref", "") or f"{step_id}:after"
        ).strip()
        normalized_steps.append(normalized_step)
    return normalized_steps


def build_acceptance_browser_request(
    *,
    mission_id: str,
    round_id: int,
    round_dir: Path,
    base_url: str,
    paths: list[str],
    interaction_plans: dict[str, list[AcceptanceInteractionStep]] | None = None,
    wait_for_selector: str | None = None,
    timeout_ms: int = 5000,
    headless: bool = True,
    browser: str = "chromium",
) -> VisualEvalRequest:
    return VisualEvalRequest(
        mission_id=mission_id,
        round_id=round_id,
        round_dir=round_dir,
        base_url=base_url.rstrip("/"),
        paths=list(paths),
        interaction_plans=dict(interaction_plans or {}),
        wait_for_selector=wait_for_selector,
        timeout_ms=timeout_ms,
        headless=headless,
        browser=browser,
    )


def build_acceptance_browser_request_from_env(
    *,
    mission_id: str,
    round_id: int,
    round_dir: Path,
    paths: list[str] | None = None,
    interaction_plans: dict[str, list[AcceptanceInteractionStep]] | None = None,
) -> VisualEvalRequest | None:
    base_url = os.environ.get("SPEC_ORCH_VISUAL_EVAL_URL", "").strip()
    if not base_url:
        return None
    resolved_paths = list(paths or [])
    if not resolved_paths:
        paths_env = os.environ.get("SPEC_ORCH_VISUAL_EVAL_PATHS", "/")
        resolved_paths = [part.strip() for part in paths_env.split(",") if part.strip()]
    if not resolved_paths:
        resolved_paths = ["/"]
    wait_for_selector = os.environ.get("SPEC_ORCH_VISUAL_EVAL_WAIT_FOR") or None
    raw_timeout = os.environ.get("SPEC_ORCH_VISUAL_EVAL_TIMEOUT_MS", "5000")
    try:
        timeout_ms = int(raw_timeout)
    except ValueError:
        logger.warning(
            "Invalid SPEC_ORCH_VISUAL_EVAL_TIMEOUT_MS=%r; falling back to 5000",
            raw_timeout,
        )
        timeout_ms = 5000
    headless = os.environ.get("SPEC_ORCH_VISUAL_EVAL_HEADLESS", "1") != "0"
    browser = os.environ.get("SPEC_ORCH_VISUAL_EVAL_BROWSER", "chromium")
    return build_acceptance_browser_request(
        mission_id=mission_id,
        round_id=round_id,
        round_dir=round_dir,
        base_url=base_url,
        paths=resolved_paths,
        interaction_plans=interaction_plans,
        wait_for_selector=wait_for_selector,
        timeout_ms=timeout_ms,
        headless=headless,
        browser=browser,
    )


def collect_browser_evidence(
    *,
    mission_id: str,
    round_id: int,
    round_dir: Path,
    snapshots: list[PageSnapshot],
) -> dict[str, Any]:
    console_errors: list[dict[str, str]] = []
    page_errors: list[dict[str, str]] = []
    screenshots: dict[str, str] = {}

    for snapshot in snapshots:
        if snapshot.path in screenshots:
            raise ValueError(f"Duplicate snapshot path in acceptance evidence: {snapshot.path}")
        screenshots[snapshot.path] = str(snapshot.screenshot_path)
        console_errors.extend(
            {"path": snapshot.path, "message": message} for message in snapshot.console_errors
        )
        page_errors.extend(
            {"path": snapshot.path, "message": message} for message in snapshot.page_errors
        )

    return {
        "mission_id": mission_id,
        "round_id": round_id,
        "producer_role": "verifier",
        "verification_origin": "browser_verifier",
        "tested_routes": [snapshot.path for snapshot in snapshots],
        "interactions": {
            snapshot.path: _normalize_interaction_log(
                snapshot.interaction_log,
                screenshot_path=snapshot.screenshot_path,
            )
            for snapshot in snapshots
        },
        "screenshots": screenshots,
        "console_errors": console_errors,
        "page_errors": page_errors,
        "artifact_paths": {
            "round_dir": str(round_dir),
            "visual_dir": str(round_dir / "visual"),
        },
    }


def collect_playwright_browser_evidence(
    *,
    mission_id: str,
    round_id: int,
    round_dir: Path,
    paths: list[str] | None = None,
    interaction_plans: dict[str, list[AcceptanceInteractionStep]] | None = None,
    output_name: str = "browser_evidence.json",
) -> dict[str, Any] | None:
    request = build_acceptance_browser_request_from_env(
        mission_id=mission_id,
        round_id=round_id,
        round_dir=round_dir,
        paths=paths,
        interaction_plans=interaction_plans,
    )
    if request is None:
        return None
    snapshots, failures = capture_page_snapshots(request)
    evidence = collect_browser_evidence(
        mission_id=mission_id,
        round_id=round_id,
        round_dir=round_dir,
        snapshots=snapshots,
    )
    evidence["page_errors"].extend(
        {"path": failure["path"], "message": failure["message"]} for failure in failures
    )
    atomic_write_json(round_dir / output_name, evidence)
    return evidence
