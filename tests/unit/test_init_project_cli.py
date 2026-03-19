from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from spec_orch.cli import app
from spec_orch.services.project_detector import ProjectProfile


def _profile(method: str) -> ProjectProfile:
    return ProjectProfile(
        language="python",
        framework="fastapi",
        verification={"test": ["pytest", "-q"]},
        base_branch="main",
        detection_method=method,
    )


def test_init_defaults_to_llm(monkeypatch, tmp_path: Path) -> None:
    calls: dict[str, bool] = {}

    def fake_detect(root: Path, *, offline: bool = False, model=None, api_key=None, api_base=None):
        calls["offline"] = offline
        return _profile("llm"), "llm"

    monkeypatch.setattr(
        "spec_orch.services.smart_project_analyzer.smart_detect_project", fake_detect
    )
    monkeypatch.setattr("spec_orch.services.config_checker.ConfigChecker.check_toml", lambda *_: [])

    runner = CliRunner()
    result = runner.invoke(app, ["init", "--repo-root", str(tmp_path), "--yes"])

    assert result.exit_code == 0
    assert calls["offline"] is False
    assert "via LLM analysis" in result.stdout
    content = (tmp_path / "spec-orch.toml").read_text(encoding="utf-8")
    assert '[init]\ndetection_mode = "llm"' in content


def test_init_offline_forces_rules(monkeypatch, tmp_path: Path) -> None:
    calls: dict[str, bool] = {}

    def fake_detect(root: Path, *, offline: bool = False, model=None, api_key=None, api_base=None):
        calls["offline"] = offline
        return _profile("rules"), "rules"

    monkeypatch.setattr(
        "spec_orch.services.smart_project_analyzer.smart_detect_project", fake_detect
    )
    monkeypatch.setattr("spec_orch.services.config_checker.ConfigChecker.check_toml", lambda *_: [])

    runner = CliRunner()
    result = runner.invoke(app, ["init", "--repo-root", str(tmp_path), "--yes", "--offline"])

    assert result.exit_code == 0
    assert calls["offline"] is True
    assert "via rule-based detection" in result.stdout


def test_init_reconfigure_uses_persisted_rules_mode(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "spec-orch.toml").write_text('[init]\ndetection_mode = "rules"\n', encoding="utf-8")
    calls: dict[str, bool] = {}

    def fake_detect(root: Path, *, offline: bool = False, model=None, api_key=None, api_base=None):
        calls["offline"] = offline
        return _profile("rules"), "rules"

    monkeypatch.setattr(
        "spec_orch.services.smart_project_analyzer.smart_detect_project", fake_detect
    )
    monkeypatch.setattr("spec_orch.services.config_checker.ConfigChecker.check_toml", lambda *_: [])

    runner = CliRunner()
    result = runner.invoke(app, ["init", "--repo-root", str(tmp_path), "--yes", "--reconfigure"])

    assert result.exit_code == 0
    assert calls["offline"] is True


def test_init_existing_config_requires_force_or_reconfigure(tmp_path: Path) -> None:
    (tmp_path / "spec-orch.toml").write_text('[issue]\nsource = "fixture"\n', encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(app, ["init", "--repo-root", str(tmp_path), "--yes"])
    assert result.exit_code == 1
    assert "Use --force or --reconfigure to overwrite." in result.stdout
