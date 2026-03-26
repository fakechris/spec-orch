from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from spec_orch.domain.models import VisualEvaluationResult
from spec_orch.services.io import atomic_write_json


@dataclass
class VisualEvalRequest:
    mission_id: str
    round_id: int
    round_dir: Path
    base_url: str
    paths: list[str]
    wait_for_selector: str | None = None
    timeout_ms: int = 5000
    headless: bool = True
    browser: str = "chromium"


@dataclass
class PageSnapshot:
    path: str
    url: str
    title: str
    screenshot_path: Path
    console_errors: list[str]
    page_errors: list[str]


def parse_request(input_path: Path) -> VisualEvalRequest:
    payload = json.loads(Path(input_path).read_text(encoding="utf-8"))
    base_url = os.environ.get("SPEC_ORCH_VISUAL_EVAL_URL", "").strip()
    if not base_url:
        raise ValueError("SPEC_ORCH_VISUAL_EVAL_URL is required")

    paths_env = os.environ.get("SPEC_ORCH_VISUAL_EVAL_PATHS", "/")
    paths = [part.strip() for part in paths_env.split(",") if part.strip()]
    if not paths:
        paths = ["/"]

    wait_for_selector = os.environ.get("SPEC_ORCH_VISUAL_EVAL_WAIT_FOR") or None
    timeout_ms = int(os.environ.get("SPEC_ORCH_VISUAL_EVAL_TIMEOUT_MS", "5000"))
    headless = os.environ.get("SPEC_ORCH_VISUAL_EVAL_HEADLESS", "1") != "0"
    browser = os.environ.get("SPEC_ORCH_VISUAL_EVAL_BROWSER", "chromium")
    round_dir = Path(payload["round_dir"])
    return VisualEvalRequest(
        mission_id=str(payload["mission_id"]),
        round_id=int(payload["round_id"]),
        round_dir=round_dir,
        base_url=base_url.rstrip("/"),
        paths=paths,
        wait_for_selector=wait_for_selector,
        timeout_ms=timeout_ms,
        headless=headless,
        browser=browser,
    )


def build_visual_evaluation_result(
    request: VisualEvalRequest,
    snapshots: list[PageSnapshot],
) -> VisualEvaluationResult:
    findings: list[dict[str, str]] = []
    artifacts = {snapshot.path: str(snapshot.screenshot_path) for snapshot in snapshots}
    error_count = 0
    for snapshot in snapshots:
        for message in snapshot.console_errors:
            findings.append(
                {
                    "severity": "error",
                    "path": snapshot.path,
                    "summary": f"console error on {snapshot.path}: {message}",
                }
            )
            error_count += 1
        for message in snapshot.page_errors:
            findings.append(
                {
                    "severity": "error",
                    "path": snapshot.path,
                    "summary": f"page error on {snapshot.path}: {message}",
                }
            )
            error_count += 1

    confidence = 0.9 if error_count == 0 else 0.4
    summary = (
        f"Checked {len(snapshots)} pages with no browser errors."
        if error_count == 0
        else f"Checked {len(snapshots)} pages and found {error_count} browser errors."
    )
    return VisualEvaluationResult(
        evaluator="playwright_sample",
        summary=summary,
        confidence=confidence,
        findings=findings,
        artifacts=artifacts,
    )


def run_playwright_visual_evaluation(request: VisualEvalRequest) -> VisualEvaluationResult:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "playwright is required for tools/visual_eval.py. "
            'Install with: pip install "spec-orch[visual]" && python -m playwright install chromium'
        ) from exc

    visual_dir = request.round_dir / "visual"
    visual_dir.mkdir(parents=True, exist_ok=True)

    snapshots: list[PageSnapshot] = []
    with sync_playwright() as playwright:
        browser_launcher = getattr(playwright, request.browser)
        browser = browser_launcher.launch(headless=request.headless)
        try:
            for path in request.paths:
                console_errors: list[str] = []
                page_errors: list[str] = []
                page = browser.new_page()
                page.on(
                    "console",
                    lambda msg, errors=console_errors: (
                        errors.append(msg.text) if msg.type == "error" else None
                    ),
                )
                page.on("pageerror", lambda exc, errors=page_errors: errors.append(str(exc)))
                url = f"{request.base_url}{path}" if path != "/" else f"{request.base_url}/"
                page.goto(url, wait_until="networkidle", timeout=request.timeout_ms)
                if request.wait_for_selector:
                    page.wait_for_selector(request.wait_for_selector, timeout=request.timeout_ms)
                title = page.title()
                screenshot_path = visual_dir / _slugify_path(path)
                page.screenshot(path=str(screenshot_path), full_page=True)
                snapshots.append(
                    PageSnapshot(
                        path=path,
                        url=url,
                        title=title,
                        screenshot_path=screenshot_path,
                        console_errors=console_errors,
                        page_errors=page_errors,
                    )
                )
                page.close()
        finally:
            browser.close()

    result = build_visual_evaluation_result(request, snapshots)
    atomic_write_json(visual_dir / "playwright_result.json", result.to_dict())
    return result


def _slugify_path(path: str) -> str:
    if path in ("", "/"):
        return "root.png"
    cleaned = path.strip("/").replace("/", "__").replace("?", "_").replace("&", "_")
    return f"{cleaned or 'page'}.png"
