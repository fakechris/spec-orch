from __future__ import annotations

from pathlib import Path


def test_pyproject_includes_fresh_resource_json_package_data() -> None:
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")

    assert "[tool.setuptools.package-data]" in text
    assert '"resources/*.json"' in text
