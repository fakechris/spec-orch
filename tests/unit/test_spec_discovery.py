"""Tests for Change 05: Spec Discovery Paths — template & example reverse-engineering."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from spec_orch.services.mission_service import MissionService
from spec_orch.services.spec_reverse_engineer import (
    _extract_json_fields,
    _rule_based_fallback,
    reverse_engineer_spec,
)


@pytest.fixture()
def svc(tmp_path: Path) -> MissionService:
    return MissionService(repo_root=tmp_path)


def _seed_template(svc: MissionService, template_id: str = "tpl-demo") -> Path:
    """Create a minimal template mission on disk."""
    tpl_dir = svc.specs_dir / template_id
    tpl_dir.mkdir(parents=True)
    spec = tpl_dir / "spec.md"
    spec.write_text(
        "# Template Title\n\n"
        "## Intent\n\nDeliver value X.\n\n"
        "## Acceptance Criteria\n\n- AC1\n- AC2\n\n"
        "## Constraints\n\n- C1\n"
    )
    meta = tpl_dir / "mission.json"
    meta.write_text(
        json.dumps(
            {
                "mission_id": template_id,
                "title": "Template Title",
                "status": "draft",
                "spec_path": f"docs/specs/{template_id}/spec.md",
                "acceptance_criteria": [],
                "constraints": [],
                "interface_contracts": [],
                "created_at": None,
                "approved_at": None,
                "completed_at": None,
            }
        )
    )
    return spec


class TestCreateMissionFromTemplate:
    def test_copies_structure_with_new_title(self, svc: MissionService) -> None:
        _seed_template(svc)
        m = svc.create_mission_from_template("New Mission", "tpl-demo")
        spec_path = svc.specs_dir / m.mission_id / "spec.md"
        content = spec_path.read_text()
        assert content.startswith("# New Mission\n")
        assert "## Intent" in content
        assert "AC1" in content

    def test_template_not_found_raises(self, svc: MissionService) -> None:
        with pytest.raises(FileNotFoundError, match="Template spec not found"):
            svc.create_mission_from_template("X", "nonexistent")

    def test_empty_template_raises(self, svc: MissionService) -> None:
        tpl_dir = svc.specs_dir / "empty-tpl"
        tpl_dir.mkdir(parents=True)
        (tpl_dir / "spec.md").write_text("   ")
        (tpl_dir / "mission.json").write_text(
            json.dumps(
                {
                    "mission_id": "empty-tpl",
                    "title": "Empty",
                    "status": "draft",
                    "spec_path": "docs/specs/empty-tpl/spec.md",
                    "acceptance_criteria": [],
                    "constraints": [],
                    "interface_contracts": [],
                    "created_at": None,
                    "approved_at": None,
                    "completed_at": None,
                }
            )
        )
        with pytest.raises(ValueError, match="empty"):
            svc.create_mission_from_template("X", "empty-tpl")


class TestCreateMissionFromExample:
    def test_with_planner(self, svc: MissionService) -> None:
        planner = MagicMock()
        planner.generate.return_value = "# Test\n\n## Intent\n\nSome goal.\n"
        m = svc.create_mission_from_example("Test Mission", "example content", planner=planner)
        spec = (svc.specs_dir / m.mission_id / "spec.md").read_text()
        assert "Some goal." in spec
        planner.generate.assert_called_once()

    def test_without_planner_uses_fallback(self, svc: MissionService) -> None:
        m = svc.create_mission_from_example("Fallback", "raw example text")
        spec = (svc.specs_dir / m.mission_id / "spec.md").read_text()
        assert "# Fallback" in spec
        assert "Reference (auto-extracted)" in spec

    def test_planner_failure_falls_back(self, svc: MissionService) -> None:
        planner = MagicMock()
        planner.generate.side_effect = RuntimeError("LLM down")
        m = svc.create_mission_from_example("Fail", "content", planner=planner)
        spec = (svc.specs_dir / m.mission_id / "spec.md").read_text()
        assert "# Fail" in spec
        assert "## Intent" in spec


class TestReverseEngineerSpec:
    def test_with_planner(self) -> None:
        planner = MagicMock()
        planner.generate.return_value = "# Spec\n\n## Intent\n\nDone.\n"
        result = reverse_engineer_spec("content", "Spec", planner=planner)
        assert "Done." in result

    def test_without_planner_fallback(self) -> None:
        result = reverse_engineer_spec("some content", "Title")
        assert "# Title" in result
        assert "Reference (auto-extracted)" in result

    def test_json_extraction(self) -> None:
        data = json.dumps({"summary": "Fix bug", "builder_prompt": "Do X"})
        result = _extract_json_fields(data)
        assert "Fix bug" in result
        assert "Do X" in result

    def test_non_json_passthrough(self) -> None:
        result = _extract_json_fields("plain text")
        assert result == "plain text"

    def test_rule_based_fallback_truncates(self) -> None:
        long_content = "x" * 1000
        result = _rule_based_fallback("T", long_content)
        assert "..." in result


class TestCLIMutualExclusion:
    def test_multiple_sources_error(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from spec_orch.cli import app

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "mission",
                "create",
                "Test",
                "--template",
                "a",
                "--from-example",
                "b",
                "--repo-root",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 1
        assert "mutually exclusive" in result.output

    def test_default_creates_blank(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from spec_orch.cli import app

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "mission",
                "create",
                "Blank Test",
                "--repo-root",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0
        assert "mission created" in result.output

    def test_from_example_file_not_found(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from spec_orch.cli import app

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "mission",
                "create",
                "Test",
                "--from-example",
                "/nonexistent/path.md",
                "--repo-root",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 1
        assert "file not found" in result.output

    def test_template_creates_from_existing(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from spec_orch.cli import app

        svc = MissionService(repo_root=tmp_path)
        _seed_template(svc, "demo-tpl")

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "mission",
                "create",
                "From Template",
                "--template",
                "demo-tpl",
                "--repo-root",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0
        assert "mission created" in result.output
