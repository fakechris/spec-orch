from __future__ import annotations

from spec_orch.services.project_detector import (
    ProjectProfile,
    detect_project,
    generate_toml_config,
)
from spec_orch.services.smart_project_analyzer import _parse_llm_result


def test_detect_project_sets_rules_detection_method(tmp_path, monkeypatch) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n")
    monkeypatch.setattr("spec_orch.services.project_detector._detect_base_branch", lambda _r: "main")

    profile = detect_project(tmp_path)

    assert profile.language == "python"
    assert profile.detection_method == "rules"


def test_generate_toml_includes_detection_method_comment() -> None:
    profile = ProjectProfile(
        language="python",
        framework="fastapi",
        verification={},
        base_branch="main",
        detection_method="llm",
    )

    toml_text = generate_toml_config(profile)

    assert "# Detection method: llm" in toml_text


def test_parse_llm_result_sets_llm_detection_method(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "spec_orch.services.smart_project_analyzer._detect_base_branch",
        lambda _r: "main",
    )
    data = {
        "languages": ["python"],
        "framework": "fastapi",
        "verification": {"test": ["pytest", "-q"]},
        "notes": "inferred from pyproject",
    }

    profile = _parse_llm_result(data, tmp_path)

    assert profile.detection_method == "llm"
    assert profile.verification["test"] == ["pytest", "-q"]
