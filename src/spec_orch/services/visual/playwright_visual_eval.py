from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from spec_orch.domain.models import AcceptanceInteractionStep, VisualEvaluationResult
from spec_orch.services.io import atomic_write_json


@dataclass
class VisualEvalRequest:
    mission_id: str
    round_id: int
    round_dir: Path
    base_url: str
    paths: list[str]
    interaction_plans: dict[str, list[AcceptanceInteractionStep]] = field(default_factory=dict)
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
    interaction_log: list[dict[str, Any]] = field(default_factory=list)


def capture_page_snapshots(
    request: VisualEvalRequest,
) -> tuple[list[PageSnapshot], list[dict[str, str]]]:
    valid_browsers = ("chromium", "firefox", "webkit")
    if request.browser not in valid_browsers:
        raise ValueError(
            f"Invalid browser '{request.browser}'. Must be one of: {', '.join(valid_browsers)}"
        )
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
    failures: list[dict[str, str]] = []
    with sync_playwright() as playwright:
        browser_launcher = getattr(playwright, request.browser)
        browser = browser_launcher.launch(headless=request.headless)
        try:
            for path in request.paths:
                console_errors: list[str] = []
                page_errors: list[str] = []
                page = None
                try:
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
                        page.wait_for_selector(
                            request.wait_for_selector, timeout=request.timeout_ms
                        )
                    interaction_log = _execute_interaction_plan(
                        page,
                        request.interaction_plans.get(path, []),
                        timeout_ms=request.timeout_ms,
                    )
                    page_errors.extend(
                        entry["message"]
                        for entry in interaction_log
                        if entry.get("status") == "failed" and isinstance(entry.get("message"), str)
                    )
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
                            interaction_log=interaction_log,
                        )
                    )
                except Exception as exc:
                    failures.append(
                        {
                            "path": path,
                            "message": f"visual evaluation failed on {path}: {exc}",
                        }
                    )
                finally:
                    if page is not None:
                        page.close()
        finally:
            browser.close()

    return snapshots, failures


def parse_request(input_path: Path) -> VisualEvalRequest:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
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
        interaction_plans={},
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
    snapshots, failures = capture_page_snapshots(request)
    visual_dir = request.round_dir / "visual"
    result = build_visual_evaluation_result(request, snapshots)
    result.findings.extend(
        {
            "severity": "error",
            "path": failure["path"],
            "summary": failure["message"],
        }
        for failure in failures
    )
    total_errors = len(result.findings)
    attempted_pages = len(request.paths)
    result.summary = (
        f"Checked {attempted_pages} pages with no browser errors."
        if total_errors == 0
        else f"Checked {attempted_pages} pages and found {total_errors} browser errors."
    )
    result.confidence = 0.9 if total_errors == 0 else 0.4
    atomic_write_json(visual_dir / "playwright_result.json", result.to_dict())
    return result


def _slugify_path(path: str) -> str:
    if path in ("", "/"):
        return "root.png"
    cleaned = path.strip("/").replace("/", "__").replace("?", "_").replace("&", "_")
    return f"{cleaned or 'page'}.png"


def _execute_interaction_plan(
    page: Any,
    steps: list[AcceptanceInteractionStep],
    *,
    timeout_ms: int,
) -> list[dict[str, Any]]:
    log: list[dict[str, Any]] = []
    for step in steps:
        entry: dict[str, Any] = {
            "action": step.action,
            "target": step.target,
            "description": step.description,
        }
        try:
            if step.action == "click_text":
                page.get_by_text(step.target, exact=True).click(timeout=timeout_ms)
                _wait_for_network_idle(page, timeout_ms=timeout_ms)
            elif step.action == "wait_for_text":
                page.get_by_text(step.target, exact=True).wait_for(
                    state="visible",
                    timeout=timeout_ms,
                )
            elif step.action == "wait_for_selector":
                page.wait_for_selector(step.target, timeout=timeout_ms)
            else:
                raise ValueError(f"Unsupported interaction action: {step.action}")
        except Exception as exc:
            entry["status"] = "failed"
            entry["message"] = f"{step.action} {step.target!r} failed: {exc}"
            log.append(entry)
            break
        entry["status"] = "passed"
        log.append(entry)
    return log


def _wait_for_network_idle(page: Any, *, timeout_ms: int) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=timeout_ms)
    except Exception:
        return None
