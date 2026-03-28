from __future__ import annotations

from pathlib import Path
from typing import Any

from spec_orch.services.visual.playwright_visual_eval import PageSnapshot, VisualEvalRequest


def build_acceptance_browser_request(
    *,
    mission_id: str,
    round_id: int,
    round_dir: Path,
    base_url: str,
    paths: list[str],
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
        "tested_routes": [snapshot.path for snapshot in snapshots],
        "screenshots": screenshots,
        "console_errors": console_errors,
        "page_errors": page_errors,
        "artifact_paths": {
            "round_dir": str(round_dir),
            "visual_dir": str(round_dir / "visual"),
        },
    }
