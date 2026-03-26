from __future__ import annotations

import json
from pathlib import Path


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
    assert result.findings[0]["severity"] == "error"
    assert "ReferenceError: boom" in result.findings[0]["summary"]
