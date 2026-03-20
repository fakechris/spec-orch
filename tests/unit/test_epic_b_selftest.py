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
