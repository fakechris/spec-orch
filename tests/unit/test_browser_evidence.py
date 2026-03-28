from __future__ import annotations

from pathlib import Path

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
            ),
            PageSnapshot(
                path="/settings",
                url="http://127.0.0.1:3000/settings",
                title="Settings",
                screenshot_path=settings_png,
                console_errors=[],
                page_errors=["Unhandled exception"],
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
