from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from spec_orch.domain.models import AcceptanceInteractionStep


def test_parse_request_merges_input_and_environment_defaults(tmp_path: Path, monkeypatch) -> None:
    from spec_orch.services.visual.playwright_visual_eval import parse_request

    input_path = tmp_path / "input.json"
    input_path.write_text(
        json.dumps(
            {
                "mission_id": "mission-1",
                "round_id": 2,
                "round_dir": str(tmp_path / "round-02"),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SPEC_ORCH_VISUAL_EVAL_URL", "http://127.0.0.1:4173")
    monkeypatch.setenv("SPEC_ORCH_VISUAL_EVAL_PATHS", "/,/settings")
    monkeypatch.setenv("SPEC_ORCH_VISUAL_EVAL_WAIT_FOR", "[data-ready]")

    request = parse_request(input_path)

    assert request.mission_id == "mission-1"
    assert request.round_id == 2
    assert request.base_url == "http://127.0.0.1:4173"
    assert request.paths == ["/", "/settings"]
    assert request.wait_for_selector == "[data-ready]"
    assert request.round_dir == tmp_path / "round-02"


def test_build_visual_evaluation_result_tracks_console_and_page_errors(tmp_path: Path) -> None:
    from spec_orch.services.visual.playwright_visual_eval import (
        PageSnapshot,
        VisualEvalRequest,
        build_visual_evaluation_result,
    )

    request = VisualEvalRequest(
        mission_id="mission-2",
        round_id=4,
        round_dir=tmp_path / "round-04",
        base_url="http://127.0.0.1:4173",
        paths=["/", "/settings"],
    )
    result = build_visual_evaluation_result(
        request,
        [
            PageSnapshot(
                path="/",
                url="http://127.0.0.1:4173/",
                title="Home",
                screenshot_path=tmp_path / "round-04" / "visual" / "home.png",
                console_errors=[],
                page_errors=[],
            ),
            PageSnapshot(
                path="/settings",
                url="http://127.0.0.1:4173/settings",
                title="Settings",
                screenshot_path=tmp_path / "round-04" / "visual" / "settings.png",
                console_errors=["ReferenceError: boom"],
                page_errors=["Unhandled rejection"],
            ),
        ],
    )

    assert result.evaluator == "playwright_sample"
    assert "2 pages" in result.summary
    assert result.confidence == 0.4
    assert result.artifacts["/"].endswith("home.png")
    assert result.artifacts["/settings"].endswith("settings.png")
    assert any(finding["summary"].endswith("ReferenceError: boom") for finding in result.findings)
    assert any(finding["summary"].endswith("Unhandled rejection") for finding in result.findings)


def test_run_playwright_visual_evaluation_rejects_invalid_browser(tmp_path: Path) -> None:
    from spec_orch.services.visual.playwright_visual_eval import (
        VisualEvalRequest,
        run_playwright_visual_evaluation,
    )

    request = VisualEvalRequest(
        mission_id="mission-3",
        round_id=1,
        round_dir=tmp_path / "round-01",
        base_url="http://127.0.0.1:4173",
        paths=["/"],
        browser="safari",
    )

    with pytest.raises(ValueError, match="Invalid browser 'safari'"):
        run_playwright_visual_evaluation(request)


def test_run_playwright_visual_evaluation_continues_after_single_page_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from spec_orch.services.visual.playwright_visual_eval import (
        VisualEvalRequest,
        run_playwright_visual_evaluation,
    )

    class FakePage:
        def __init__(self) -> None:
            self._console_handler = None
            self._pageerror_handler = None
            self._url = ""

        def on(self, event: str, handler) -> None:
            if event == "console":
                self._console_handler = handler
            elif event == "pageerror":
                self._pageerror_handler = handler

        def goto(self, url: str, wait_until: str, timeout: int) -> None:
            self._url = url
            if url.endswith("/broken"):
                raise RuntimeError("navigation timeout")
            if self._console_handler is not None:
                self._console_handler(SimpleNamespace(type="error", text="boom"))

        def wait_for_selector(self, selector: str, timeout: int) -> None:
            return None

        def title(self) -> str:
            return "Page"

        def screenshot(self, path: str, full_page: bool) -> None:
            Path(path).write_text("png", encoding="utf-8")

        def close(self) -> None:
            return None

    class FakeBrowser:
        def __init__(self) -> None:
            self.calls = 0

        def new_page(self) -> FakePage:
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("tab creation failed")
            return FakePage()

        def close(self) -> None:
            return None

    class FakeLauncher:
        def launch(self, *, headless: bool) -> FakeBrowser:
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeLauncher()
        firefox = FakeLauncher()
        webkit = FakeLauncher()

    class FakeManager:
        def __enter__(self) -> FakePlaywright:
            return FakePlaywright()

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    monkeypatch.setitem(__import__("sys").modules, "playwright", SimpleNamespace())
    monkeypatch.setitem(
        __import__("sys").modules,
        "playwright.sync_api",
        SimpleNamespace(sync_playwright=lambda: FakeManager()),
    )

    request = VisualEvalRequest(
        mission_id="mission-4",
        round_id=1,
        round_dir=tmp_path / "round-01",
        base_url="http://127.0.0.1:4173",
        paths=["/", "/broken"],
        browser="chromium",
    )

    result = run_playwright_visual_evaluation(request)

    assert "2 pages" in result.summary
    assert "2 browser errors" in result.summary
    assert result.confidence == 0.4
    assert result.artifacts["/"].endswith("root.png")
    assert any("tab creation failed" in finding["summary"] for finding in result.findings)


def test_capture_page_snapshots_executes_interaction_plan(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from spec_orch.services.visual.playwright_visual_eval import (
        VisualEvalRequest,
        capture_page_snapshots,
    )

    class FakeLocator:
        def __init__(self, text: str, log: list[tuple[str, str]]) -> None:
            self.text = text
            self.log = log

        def click(self, timeout: int) -> None:
            self.log.append(("click", self.text))

        def fill(self, value: str, timeout: int) -> None:
            self.log.append(("fill", f"{self.text}={value}"))

        def wait_for(self, state: str, timeout: int) -> None:
            self.log.append(("wait_for", self.text))

    class FakePage:
        def __init__(self, log: list[tuple[str, str]]) -> None:
            self._console_handler = None
            self._pageerror_handler = None
            self.log = log

        def on(self, event: str, handler) -> None:
            if event == "console":
                self._console_handler = handler
            elif event == "pageerror":
                self._pageerror_handler = handler

        def goto(self, url: str, wait_until: str, timeout: int) -> None:
            self.log.append(("goto", url))

        def wait_for_selector(self, selector: str, timeout: int) -> None:
            self.log.append(("selector", selector))

        def get_by_text(self, text: str, exact: bool = True) -> FakeLocator:
            return FakeLocator(text, self.log)

        def locator(self, selector: str) -> FakeLocator:
            return FakeLocator(selector, self.log)

        def wait_for_load_state(self, state: str, timeout: int) -> None:
            self.log.append(("load_state", state))

        def title(self) -> str:
            return "Mission"

        def screenshot(self, path: str, full_page: bool) -> None:
            Path(path).write_text("png", encoding="utf-8")

        def close(self) -> None:
            return None

    class FakeBrowser:
        def __init__(self, log: list[tuple[str, str]]) -> None:
            self.log = log

        def new_page(self) -> FakePage:
            return FakePage(self.log)

        def close(self) -> None:
            return None

    class FakeLauncher:
        def __init__(self, log: list[tuple[str, str]]) -> None:
            self.log = log

        def launch(self, *, headless: bool) -> FakeBrowser:
            return FakeBrowser(self.log)

    class FakePlaywright:
        def __init__(self, log: list[tuple[str, str]]) -> None:
            self.chromium = FakeLauncher(log)
            self.firefox = FakeLauncher(log)
            self.webkit = FakeLauncher(log)

    class FakeManager:
        def __init__(self, log: list[tuple[str, str]]) -> None:
            self.log = log

        def __enter__(self) -> FakePlaywright:
            return FakePlaywright(self.log)

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    log: list[tuple[str, str]] = []
    monkeypatch.setitem(__import__("sys").modules, "playwright", SimpleNamespace())
    monkeypatch.setitem(
        __import__("sys").modules,
        "playwright.sync_api",
        SimpleNamespace(sync_playwright=lambda: FakeManager(log)),
    )

    request = VisualEvalRequest(
        mission_id="mission-5",
        round_id=1,
        round_dir=tmp_path / "round-01",
        base_url="http://127.0.0.1:4173",
        paths=["/?mission=mission-5&tab=overview"],
        interaction_plans={
            "/?mission=mission-5&tab=overview": [
                AcceptanceInteractionStep(
                    action="fill_selector",
                    target='[data-automation-target="launcher-field"][data-field-key="title"]',
                    value="Mission 5 Workflow Smoke",
                ),
                AcceptanceInteractionStep(
                    action="click_selector",
                    target='[data-automation-target="mission-card"][data-mission-id="mission-5"]',
                ),
                AcceptanceInteractionStep(action="click_text", target="Transcript"),
                AcceptanceInteractionStep(action="click_text", target="Overview"),
            ]
        },
        browser="chromium",
    )

    snapshots, failures = capture_page_snapshots(request)

    assert failures == []
    assert snapshots[0].interaction_log == [
        {
            "step_id": "step-01",
            "action": "fill_selector",
            "target": '[data-automation-target="launcher-field"][data-field-key="title"]',
            "description": "",
            "expected": 'fill_selector [data-automation-target="launcher-field"][data-field-key="title"]',
            "before_snapshot_ref": "step-01:before",
            "after_snapshot_ref": "step-01:after",
            "status": "passed",
            "marker": "STEP_PASS",
            "actual": "Step completed.",
        },
        {
            "step_id": "step-02",
            "action": "click_selector",
            "target": '[data-automation-target="mission-card"][data-mission-id="mission-5"]',
            "description": "",
            "expected": 'click_selector [data-automation-target="mission-card"][data-mission-id="mission-5"]',
            "before_snapshot_ref": "step-02:before",
            "after_snapshot_ref": "step-02:after",
            "status": "passed",
            "marker": "STEP_PASS",
            "actual": "Step completed.",
        },
        {
            "step_id": "step-03",
            "action": "click_text",
            "target": "Transcript",
            "description": "",
            "expected": "click_text Transcript",
            "before_snapshot_ref": "step-03:before",
            "after_snapshot_ref": "step-03:after",
            "status": "passed",
            "marker": "STEP_PASS",
            "actual": "Step completed.",
        },
        {
            "step_id": "step-04",
            "action": "click_text",
            "target": "Overview",
            "description": "",
            "expected": "click_text Overview",
            "before_snapshot_ref": "step-04:before",
            "after_snapshot_ref": "step-04:after",
            "status": "passed",
            "marker": "STEP_PASS",
            "actual": "Step completed.",
        },
    ]
    assert (
        "fill",
        '[data-automation-target="launcher-field"][data-field-key="title"]=Mission 5 Workflow Smoke',
    ) in log
    assert ("click", '[data-automation-target="mission-card"][data-mission-id="mission-5"]') in log
    assert ("click", "Transcript") in log
    assert ("click", "Overview") in log


def test_capture_page_snapshots_uses_step_specific_timeout(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from spec_orch.services.visual.playwright_visual_eval import (
        VisualEvalRequest,
        capture_page_snapshots,
    )

    class FakeLocator:
        def __init__(self, selector: str, log: list[tuple[str, str, int]]) -> None:
            self.selector = selector
            self.log = log

        def click(self, timeout: int) -> None:
            self.log.append(("click", self.selector, timeout))

        def fill(self, value: str, timeout: int) -> None:
            self.log.append(("fill", f"{self.selector}={value}", timeout))

    class FakePage:
        def __init__(self, log: list[tuple[str, str, int]]) -> None:
            self.log = log

        def on(self, event: str, handler) -> None:
            return None

        def goto(self, url: str, wait_until: str, timeout: int) -> None:
            self.log.append(("goto", url, timeout))

        def wait_for_selector(self, selector: str, timeout: int) -> None:
            self.log.append(("selector", selector, timeout))

        def locator(self, selector: str) -> FakeLocator:
            return FakeLocator(selector, self.log)

        def wait_for_load_state(self, state: str, timeout: int) -> None:
            self.log.append(("load_state", state, timeout))

        def title(self) -> str:
            return "Mission"

        def screenshot(self, path: str, full_page: bool) -> None:
            Path(path).write_text("png", encoding="utf-8")

        def close(self) -> None:
            return None

    class FakeBrowser:
        def __init__(self, log: list[tuple[str, str, int]]) -> None:
            self.log = log

        def new_page(self) -> FakePage:
            return FakePage(self.log)

        def close(self) -> None:
            return None

    class FakeLauncher:
        def __init__(self, log: list[tuple[str, str, int]]) -> None:
            self.log = log

        def launch(self, *, headless: bool) -> FakeBrowser:
            return FakeBrowser(self.log)

    class FakePlaywright:
        def __init__(self, log: list[tuple[str, str, int]]) -> None:
            self.chromium = FakeLauncher(log)
            self.firefox = FakeLauncher(log)
            self.webkit = FakeLauncher(log)

    class FakeManager:
        def __init__(self, log: list[tuple[str, str, int]]) -> None:
            self.log = log

        def __enter__(self) -> FakePlaywright:
            return FakePlaywright(self.log)

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    log: list[tuple[str, str, int]] = []
    monkeypatch.setitem(__import__("sys").modules, "playwright", SimpleNamespace())
    monkeypatch.setitem(
        __import__("sys").modules,
        "playwright.sync_api",
        SimpleNamespace(sync_playwright=lambda: FakeManager(log)),
    )

    request = VisualEvalRequest(
        mission_id="mission-6",
        round_id=1,
        round_dir=tmp_path / "round-01",
        base_url="http://127.0.0.1:4173",
        paths=["/"],
        interaction_plans={
            "/": [
                AcceptanceInteractionStep(
                    action="click_selector",
                    target='[data-automation-target="launcher-action"][data-launcher-action="approve-plan"]',
                    timeout_ms=90000,
                ),
                AcceptanceInteractionStep(
                    action="wait_for_selector",
                    target='[data-automation-target="launcher-status"][data-tone="success"]',
                    timeout_ms=90000,
                ),
            ]
        },
        timeout_ms=5000,
        browser="chromium",
    )

    snapshots, failures = capture_page_snapshots(request)

    assert failures == []
    assert snapshots[0].interaction_log[-1]["status"] == "passed"
    assert (
        "click",
        '[data-automation-target="launcher-action"][data-launcher-action="approve-plan"]',
        90000,
    ) in log
    assert (
        "selector",
        '[data-automation-target="launcher-status"][data-tone="success"]',
        90000,
    ) in log


def test_capture_page_snapshots_falls_back_to_request_timeout_when_step_timeout_is_zero(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from spec_orch.services.visual.playwright_visual_eval import (
        VisualEvalRequest,
        capture_page_snapshots,
    )

    class FakeLocator:
        def __init__(self, selector: str, log: list[tuple[str, str, int]]) -> None:
            self.selector = selector
            self.log = log

        def click(self, timeout: int) -> None:
            self.log.append(("click", self.selector, timeout))

    class FakePage:
        def __init__(self, log: list[tuple[str, str, int]]) -> None:
            self.log = log

        def on(self, event: str, handler) -> None:
            return None

        def goto(self, url: str, wait_until: str, timeout: int) -> None:
            self.log.append(("goto", url, timeout))

        def wait_for_selector(self, selector: str, timeout: int) -> None:
            self.log.append(("selector", selector, timeout))

        def locator(self, selector: str) -> FakeLocator:
            return FakeLocator(selector, self.log)

        def wait_for_load_state(self, state: str, timeout: int) -> None:
            self.log.append(("load_state", state, timeout))

        def title(self) -> str:
            return "Mission"

        def screenshot(self, path: str, full_page: bool) -> None:
            Path(path).write_text("png", encoding="utf-8")

        def close(self) -> None:
            return None

    class FakeBrowser:
        def __init__(self, log: list[tuple[str, str, int]]) -> None:
            self.log = log

        def new_page(self) -> FakePage:
            return FakePage(self.log)

        def close(self) -> None:
            return None

    class FakeLauncher:
        def __init__(self, log: list[tuple[str, str, int]]) -> None:
            self.log = log

        def launch(self, *, headless: bool) -> FakeBrowser:
            return FakeBrowser(self.log)

    class FakePlaywright:
        def __init__(self, log: list[tuple[str, str, int]]) -> None:
            self.chromium = FakeLauncher(log)
            self.firefox = FakeLauncher(log)
            self.webkit = FakeLauncher(log)

    class FakeManager:
        def __init__(self, log: list[tuple[str, str, int]]) -> None:
            self.log = log

        def __enter__(self) -> FakePlaywright:
            return FakePlaywright(self.log)

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    log: list[tuple[str, str, int]] = []
    monkeypatch.setitem(__import__("sys").modules, "playwright", SimpleNamespace())
    monkeypatch.setitem(
        __import__("sys").modules,
        "playwright.sync_api",
        SimpleNamespace(sync_playwright=lambda: FakeManager(log)),
    )

    request = VisualEvalRequest(
        mission_id="mission-6",
        round_id=1,
        round_dir=tmp_path / "round-01",
        base_url="http://127.0.0.1:4173",
        paths=["/"],
        interaction_plans={
            "/": [
                AcceptanceInteractionStep(
                    action="click_selector",
                    target='[data-automation-target="launcher-action"][data-launcher-action="approve-plan"]',
                    timeout_ms=0,
                ),
            ]
        },
        timeout_ms=5000,
        browser="chromium",
    )

    snapshots, failures = capture_page_snapshots(request)

    assert failures == []
    assert snapshots[0].interaction_log[-1]["status"] == "passed"
    assert (
        "click",
        '[data-automation-target="launcher-action"][data-launcher-action="approve-plan"]',
        5000,
    ) in log


def test_run_playwright_visual_evaluation_persists_proof_type_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from spec_orch.services.visual.playwright_visual_eval import (
        VisualEvalRequest,
        run_playwright_visual_evaluation,
    )

    class FakePage:
        def on(self, event: str, handler) -> None:
            return None

        def goto(self, url: str, wait_until: str, timeout: int) -> None:
            return None

        def title(self) -> str:
            return "Mission"

        def screenshot(self, path: str, full_page: bool) -> None:
            Path(path).write_text("png", encoding="utf-8")

        def close(self) -> None:
            return None

    class FakeBrowser:
        def new_page(self) -> FakePage:
            return FakePage()

        def close(self) -> None:
            return None

    class FakeLauncher:
        def launch(self, *, headless: bool) -> FakeBrowser:
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeLauncher()
        firefox = FakeLauncher()
        webkit = FakeLauncher()

    class FakeManager:
        def __enter__(self) -> FakePlaywright:
            return FakePlaywright()

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    monkeypatch.setitem(__import__("sys").modules, "playwright", SimpleNamespace())
    monkeypatch.setitem(
        __import__("sys").modules,
        "playwright.sync_api",
        SimpleNamespace(sync_playwright=lambda: FakeManager()),
    )

    request = VisualEvalRequest(
        mission_id="fresh-mission",
        round_id=2,
        round_dir=tmp_path / "round-02",
        base_url="http://127.0.0.1:4173",
        paths=["/"],
        proof_type="fresh_post_run_replay",
    )

    run_playwright_visual_evaluation(request)

    persisted = json.loads(
        (tmp_path / "round-02" / "visual" / "playwright_result.json").read_text(encoding="utf-8")
    )

    assert persisted["proof_type"] == "fresh_post_run_replay"
    assert persisted["result"]["summary"].startswith("Checked 1 pages")
