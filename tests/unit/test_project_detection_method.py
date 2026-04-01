from __future__ import annotations

from spec_orch.services.project_detector import (
    ProjectProfile,
    detect_project,
    generate_toml_config,
)
from spec_orch.services.smart_project_analyzer import _parse_llm_result


def test_detect_project_sets_rules_detection_method(tmp_path, monkeypatch) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n")
    monkeypatch.setattr(
        "spec_orch.services.project_detector._detect_base_branch", lambda _r: "main"
    )

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

    assert profile is not None
    assert profile.detection_method == "llm"
    assert profile.verification["test"] == ["pytest", "-q"]


def test_parse_llm_result_rejects_missing_languages(tmp_path) -> None:
    result = _parse_llm_result({"verification": {}}, tmp_path)
    assert result is None


def test_parse_llm_result_rejects_non_list_languages(tmp_path) -> None:
    result = _parse_llm_result({"languages": "python"}, tmp_path)
    assert result is None


def test_parse_llm_result_rejects_non_dict_verification(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "spec_orch.services.smart_project_analyzer._detect_base_branch",
        lambda _r: "main",
    )
    result = _parse_llm_result({"languages": ["python"], "verification": ["pytest"]}, tmp_path)
    assert result is None


def test_generate_toml_recommends_llm_reviewer_when_key_available(monkeypatch) -> None:
    """SON-209: generate_toml_config recommends llm reviewer when API key is set."""
    from spec_orch.services.project_detector import ProjectProfile, generate_toml_config

    monkeypatch.setenv("SPEC_ORCH_LLM_API_KEY", "test-key")
    profile = ProjectProfile(language="python", verification={"test": ["pytest"]})
    toml_text = generate_toml_config(profile)
    assert 'adapter = "llm"' in toml_text


def test_generate_toml_defaults_to_local_reviewer_without_key(monkeypatch) -> None:
    """SON-209: generate_toml_config defaults to local reviewer when no API key."""
    from spec_orch.services.project_detector import ProjectProfile, generate_toml_config

    monkeypatch.delenv("SPEC_ORCH_LLM_API_KEY", raising=False)
    profile = ProjectProfile(language="python", verification={"test": ["pytest"]})
    toml_text = generate_toml_config(profile)
    assert 'adapter = "local"' in toml_text


def test_generate_toml_uses_shared_model_catalog_defaults() -> None:
    profile = ProjectProfile(language="python", verification={"test": ["pytest"]})

    toml_text = generate_toml_config(profile)

    assert "[llm]" in toml_text
    assert 'default_model_chain = "default_reasoning"' in toml_text
    assert "[models.default_reasoning]" in toml_text
    assert "[model_chains.default_reasoning]" in toml_text
    assert "[planner]" in toml_text
    assert "# inherits [llm].default_model_chain unless overridden" in toml_text
