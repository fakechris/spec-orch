from __future__ import annotations

import json
from pathlib import Path

import pytest

from spec_orch.domain.models import AcceptanceInteractionStep
from spec_orch.services.acceptance.browser_evidence import (
    build_acceptance_browser_request,
    collect_browser_evidence,
)
from spec_orch.services.visual.playwright_visual_eval import PageSnapshot


def test_build_acceptance_browser_request_uses_round_context(tmp_path: Path) -> None:
    round_dir = tmp_path / "docs" / "specs" / "demo" / "rounds" / "round-01"
    round_dir.mkdir(parents=True)

    request = build_acceptance_browser_request(
        mission_id="demo-mission",
        round_id=1,
        round_dir=round_dir,
        base_url="http://127.0.0.1:3000",
        paths=["/", "/settings"],
        interaction_plans={
            "/settings": [AcceptanceInteractionStep(action="click_text", target="Transcript")]
        },
        wait_for_selector="#app",
        timeout_ms=9000,
        headless=False,
        browser="firefox",
    )

    assert request.mission_id == "demo-mission"
    assert request.round_id == 1
    assert request.round_dir == round_dir
    assert request.base_url == "http://127.0.0.1:3000"
    assert request.paths == ["/", "/settings"]
    assert request.interaction_plans["/settings"][0].target == "Transcript"
    assert request.wait_for_selector == "#app"
    assert request.timeout_ms == 9000
    assert request.headless is False
    assert request.browser == "firefox"


def test_collect_browser_evidence_returns_operator_friendly_payload(tmp_path: Path) -> None:
    round_dir = tmp_path / "round-01"
    round_dir.mkdir(parents=True)
    visual_dir = round_dir / "visual"
    visual_dir.mkdir()
    home_png = visual_dir / "home.png"
    settings_png = visual_dir / "settings.png"
    home_png.write_text("png", encoding="utf-8")
    settings_png.write_text("png", encoding="utf-8")

    evidence = collect_browser_evidence(
        mission_id="demo-mission",
        round_id=1,
        round_dir=round_dir,
        snapshots=[
            PageSnapshot(
                path="/",
                url="http://127.0.0.1:3000/",
                title="Home",
                screenshot_path=home_png,
                console_errors=["ReferenceError: boom"],
                page_errors=[],
                interaction_log=[
                    {
                        "action": "click_text",
                        "target": "Transcript",
                        "description": "Open transcript timeline.",
                        "status": "passed",
                    }
                ],
            ),
            PageSnapshot(
                path="/settings",
                url="http://127.0.0.1:3000/settings",
                title="Settings",
                screenshot_path=settings_png,
                console_errors=[],
                page_errors=["Unhandled exception"],
                interaction_log=[
                    {
                        "action": "click_text",
                        "target": "Acceptance",
                        "description": "Open acceptance evidence.",
                        "status": "failed",
                        "message": "selector missing",
                    },
                    {
                        "action": "wait_for_selector",
                        "target": "[data-role='acceptance-panel']",
                        "description": "Wait for acceptance panel.",
                        "status": "skipped",
                    },
                ],
            ),
        ],
    )

    assert evidence["mission_id"] == "demo-mission"
    assert evidence["round_id"] == 1
    assert evidence["tested_routes"] == ["/", "/settings"]
    assert evidence["screenshots"] == {
        "/": str(home_png),
        "/settings": str(settings_png),
    }
    assert evidence["interactions"]["/"][0]["marker"] == "STEP_PASS"
    assert evidence["interactions"]["/"][0]["step_id"] == "step-01"
    assert evidence["interactions"]["/"][0]["expected"] == "Open transcript timeline."
    assert evidence["interactions"]["/"][0]["actual"] == "Step completed."
    assert evidence["interactions"]["/"][0]["screenshot_path"] == str(home_png)
    assert evidence["interactions"]["/settings"][0]["marker"] == "STEP_FAIL"
    assert evidence["interactions"]["/settings"][0]["step_id"] == "step-01"
    assert evidence["interactions"]["/settings"][0]["expected"] == "Open acceptance evidence."
    assert evidence["interactions"]["/settings"][0]["actual"] == "selector missing"
    assert evidence["interactions"]["/settings"][0]["screenshot_path"] == str(settings_png)
    assert evidence["interactions"]["/settings"][0]["before_snapshot_ref"]
    assert evidence["interactions"]["/settings"][0]["after_snapshot_ref"]
    assert evidence["interactions"]["/settings"][1]["marker"] == "STEP_SKIP"
    assert evidence["interactions"]["/settings"][1]["actual"] == "Skipped."
    assert evidence["artifact_paths"]["round_dir"] == str(round_dir)
    assert evidence["artifact_paths"]["visual_dir"] == str(visual_dir)
    assert evidence["console_errors"] == [{"path": "/", "message": "ReferenceError: boom"}]
    assert evidence["page_errors"] == [{"path": "/settings", "message": "Unhandled exception"}]


def test_collect_browser_evidence_rejects_duplicate_snapshot_paths(tmp_path: Path) -> None:
    round_dir = tmp_path / "round-01"
    round_dir.mkdir(parents=True)
    visual_dir = round_dir / "visual"
    visual_dir.mkdir()
    first_png = visual_dir / "home-a.png"
    second_png = visual_dir / "home-b.png"
    first_png.write_text("png", encoding="utf-8")
    second_png.write_text("png", encoding="utf-8")

    try:
        collect_browser_evidence(
            mission_id="demo-mission",
            round_id=1,
            round_dir=round_dir,
            snapshots=[
                PageSnapshot(
                    path="/",
                    url="http://127.0.0.1:3000/",
                    title="Home",
                    screenshot_path=first_png,
                    console_errors=[],
                    page_errors=[],
                ),
                PageSnapshot(
                    path="/",
                    url="http://127.0.0.1:3000/",
                    title="Home duplicate",
                    screenshot_path=second_png,
                    console_errors=[],
                    page_errors=[],
                ),
            ],
        )
    except ValueError as exc:
        assert "Duplicate snapshot path" in str(exc)
    else:
        raise AssertionError("expected duplicate snapshot paths to fail fast")


def test_collect_playwright_browser_evidence_reuses_snapshot_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import spec_orch.services.acceptance.browser_evidence as browser_evidence

    round_dir = tmp_path / "docs" / "specs" / "demo" / "rounds" / "round-01"
    visual_dir = round_dir / "visual"
    visual_dir.mkdir(parents=True)
    home_png = visual_dir / "home.png"
    home_png.write_text("png", encoding="utf-8")

    monkeypatch.setenv("SPEC_ORCH_VISUAL_EVAL_URL", "http://127.0.0.1:4173")
    monkeypatch.setenv("SPEC_ORCH_VISUAL_EVAL_PATHS", "/,/settings")

    def fake_capture(request):
        assert request.mission_id == "demo-mission"
        assert request.round_id == 1
        assert request.interaction_plans["/settings"][0].target == "Transcript"
        return (
            [
                PageSnapshot(
                    path="/",
                    url="http://127.0.0.1:4173/",
                    title="Home",
                    screenshot_path=home_png,
                    console_errors=["ReferenceError: boom"],
                    page_errors=[],
                    interaction_log=[],
                )
            ],
            [{"path": "/settings", "message": "navigation timeout"}],
        )

    monkeypatch.setattr(browser_evidence, "capture_page_snapshots", fake_capture)

    evidence = browser_evidence.collect_playwright_browser_evidence(
        mission_id="demo-mission",
        round_id=1,
        round_dir=round_dir,
        interaction_plans={
            "/settings": [AcceptanceInteractionStep(action="click_text", target="Transcript")]
        },
    )

    assert evidence["tested_routes"] == ["/"]
    assert evidence["interactions"] == {"/": []}
    assert evidence["screenshots"]["/"] == str(home_png)
    assert evidence["console_errors"] == [{"path": "/", "message": "ReferenceError: boom"}]
    assert evidence["page_errors"] == [{"path": "/settings", "message": "navigation timeout"}]
    persisted = json.loads((round_dir / "browser_evidence.json").read_text(encoding="utf-8"))
    assert persisted["artifact_paths"]["visual_dir"] == str(visual_dir)


def test_build_acceptance_browser_request_from_env_falls_back_on_bad_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from spec_orch.services.acceptance.browser_evidence import (
        build_acceptance_browser_request_from_env,
    )

    round_dir = tmp_path / "docs" / "specs" / "demo" / "rounds" / "round-01"
    monkeypatch.setenv("SPEC_ORCH_VISUAL_EVAL_URL", "http://127.0.0.1:4173")
    monkeypatch.setenv("SPEC_ORCH_VISUAL_EVAL_TIMEOUT_MS", "not-a-number")

    request = build_acceptance_browser_request_from_env(
        mission_id="demo-mission",
        round_id=1,
        round_dir=round_dir,
    )

    assert request is not None
    assert request.timeout_ms == 5000
    assert "SPEC_ORCH_VISUAL_EVAL_TIMEOUT_MS" in caplog.text
