"""Tests for Epic B: Doctor health file and selftest."""

from __future__ import annotations

import json
from pathlib import Path

from spec_orch.services.doctor import Doctor


def test_write_health_file(tmp_path: Path) -> None:
    config = tmp_path / "spec-orch.toml"
    config.write_text("[general]\nproject_name = 'test'\n")
    doc = Doctor(config_path=config)
    output_dir = tmp_path / ".spec_orch"
    health_path = doc.write_health_file(output_dir=output_dir)
    assert health_path.exists()
    data = json.loads(health_path.read_text())
    assert "checks" in data
    assert "summary" in data
    assert isinstance(data["summary"]["pass"], int)


def test_health_file_contains_all_checks(tmp_path: Path) -> None:
    config = tmp_path / "spec-orch.toml"
    config.write_text("[general]\nproject_name = 'test'\n")
    doc = Doctor(config_path=config)
    health_path = doc.write_health_file(output_dir=tmp_path)
    data = json.loads(health_path.read_text())
    names = [c["name"] for c in data["checks"]]
    assert "env:git" in names
    assert "env:python" in names


def test_doctor_reviewer_check_local_without_key(tmp_path: Path, monkeypatch) -> None:
    """SON-209: doctor reports reviewer=local as pass when no LLM key is set."""
    monkeypatch.delenv("SPEC_ORCH_LLM_API_KEY", raising=False)
    config = tmp_path / "spec-orch.toml"
    config.write_text('[reviewer]\nadapter = "local"\n')
    doc = Doctor(config_path=config)
    checks = doc.run_all()
    reviewer_checks = [c for c in checks if c.name == "reviewer:adapter"]
    assert len(reviewer_checks) == 1
    assert reviewer_checks[0].status == "pass"


def test_doctor_reviewer_check_local_with_key(tmp_path: Path, monkeypatch) -> None:
    """SON-209: doctor warns about local reviewer when LLM key is available."""
    monkeypatch.setenv("SPEC_ORCH_LLM_API_KEY", "test-key")
    config = tmp_path / "spec-orch.toml"
    config.write_text('[reviewer]\nadapter = "local"\n')
    doc = Doctor(config_path=config)
    checks = doc.run_all()
    reviewer_checks = [c for c in checks if c.name == "reviewer:adapter"]
    assert len(reviewer_checks) == 1
    assert reviewer_checks[0].status == "warn"
    assert "llm" in (reviewer_checks[0].fix_hint or "").lower()


def test_doctor_reviewer_check_llm(tmp_path: Path) -> None:
    """SON-209: doctor reports reviewer=llm as pass."""
    config = tmp_path / "spec-orch.toml"
    config.write_text('[reviewer]\nadapter = "llm"\n')
    doc = Doctor(config_path=config)
    checks = doc.run_all()
    reviewer_checks = [c for c in checks if c.name == "reviewer:adapter"]
    assert len(reviewer_checks) == 1
    assert reviewer_checks[0].status == "pass"


def test_doctor_env_check_accepts_shared_worktree_dotenv(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "worktrees" / "feature" / "spec-orch.toml"
    shared_root = tmp_path / "shared"
    config.parent.mkdir(parents=True)
    shared_root.mkdir(parents=True)
    config.write_text(
        "\n".join(
            [
                "[planner]",
                'api_key_env = "MINIMAX_API_KEY"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    (shared_root / ".env").write_text("SPEC_ORCH_LLM_API_KEY=shared-key\n", encoding="utf-8")
    monkeypatch.delenv("SPEC_ORCH_LLM_API_KEY", raising=False)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    monkeypatch.setattr(
        "spec_orch.services.env_files.resolve_git_common_dir",
        lambda start=None: shared_root / ".git",
    )

    doc = Doctor(config_path=config)
    checks = doc.run_all()
    env_checks = [c for c in checks if c.name == "env:dotenv"]
    assert len(env_checks) == 1
    assert env_checks[0].status == "pass"
    assert str((shared_root / ".env").resolve()) in env_checks[0].message
