"""Tests for Change 06: Spec import parsers (SON-105)."""

from __future__ import annotations

from pathlib import Path

from spec_orch.spec_import.bdd import BddParser
from spec_orch.spec_import.ears import EarsParser
from spec_orch.spec_import.models import SpecStructure
from spec_orch.spec_import.parser import PARSER_REGISTRY
from spec_orch.spec_import.spec_kit import SpecKitParser


class TestSpecStructure:
    def test_to_markdown(self) -> None:
        s = SpecStructure(
            intent="Ship feature",
            acceptance_criteria=["AC1", "AC2"],
            constraints=["C1"],
        )
        md = s.to_markdown("Test Feature")
        assert md.startswith("# Test Feature")
        assert "## Intent" in md
        assert "Ship feature" in md
        assert "- AC1" in md
        assert "- C1" in md

    def test_empty_structure(self) -> None:
        s = SpecStructure()
        md = s.to_markdown("Empty")
        assert "# Empty" in md
        assert "<!-- describe the user value -->" in md


class TestSpecKitParser:
    def test_parse_directory(self, tmp_path: Path) -> None:
        specify = tmp_path / ".specify"
        specify.mkdir()
        (specify / "spec.md").write_text(
            "# Login Feature\n\n"
            "## Intent\n\nUsers can log in.\n\n"
            "## Requirements\n\n- Must support OAuth\n- Must support email\n"
        )
        (specify / "plan.md").write_text("Use OAuth2 + email auth flow.\n")

        parser = SpecKitParser()
        result = parser.parse(specify)

        assert result.source_format == "spec-kit"
        assert "log in" in result.intent.lower() or "Users can log in" in result.intent
        assert len(result.acceptance_criteria) == 2
        assert "OAuth2" in result.raw_sections.get("Implementation Notes", "")

    def test_parse_file_in_dir(self, tmp_path: Path) -> None:
        specify = tmp_path / ".specify"
        specify.mkdir()
        spec = specify / "spec.md"
        spec.write_text("# X\n\n## Intent\n\nDo Y.\n")

        parser = SpecKitParser()
        result = parser.parse(spec)
        assert "Do Y" in result.intent


class TestEarsParser:
    def test_parse_ears_statements(self, tmp_path: Path) -> None:
        ears_file = tmp_path / "reqs.md"
        ears_file.write_text(
            "# System Requirements\n\n"
            "WHEN the user clicks submit, THE SYSTEM SHALL save the form.\n"
            "WHILE the system is processing, THE SYSTEM SHALL show a spinner.\n"
        )

        parser = EarsParser()
        result = parser.parse(ears_file)

        assert result.source_format == "ears"
        assert result.intent == "System Requirements"
        assert len(result.acceptance_criteria) >= 2

    def test_no_ears_yields_empty_ac(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.md"
        f.write_text("# Nothing here\n\nJust plain text.\n")
        result = EarsParser().parse(f)
        assert result.acceptance_criteria == []


class TestBddParser:
    def test_parse_gherkin(self, tmp_path: Path) -> None:
        feature = tmp_path / "login.feature"
        feature.write_text(
            "Feature: User Login\n\n"
            "Scenario: Successful login\n"
            "  Given a registered user\n"
            "  When they enter valid credentials\n"
            "  Then they are redirected to dashboard\n\n"
            "Scenario: Failed login\n"
            "  Given a registered user\n"
            "  When they enter invalid password\n"
            "  Then they see an error message\n"
        )

        parser = BddParser()
        result = parser.parse(feature)

        assert result.source_format == "bdd"
        assert result.intent == "User Login"
        assert len(result.acceptance_criteria) == 2
        assert any("Successful login" in ac for ac in result.acceptance_criteria)


class TestParserRegistry:
    def test_supported_formats(self) -> None:
        fmts = PARSER_REGISTRY.supported_formats()
        assert "spec-kit" in fmts
        assert "ears" in fmts
        assert "bdd" in fmts

    def test_unknown_returns_none(self) -> None:
        assert PARSER_REGISTRY.get("tessl") is None


class TestSpecImportCLI:
    def test_unsupported_format(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from spec_orch.cli import app

        runner = CliRunner()
        result = runner.invoke(
            app, ["spec", "import", "--format", "tessl", "--path", str(tmp_path)]
        )
        assert result.exit_code == 1
        assert "unsupported format" in result.output

    def test_path_not_found(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from spec_orch.cli import app

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["spec", "import", "--format", "ears", "--path", "/nonexistent/path.md"],
        )
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_dry_run(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from spec_orch.cli import app

        ears_file = tmp_path / "reqs.md"
        ears_file.write_text("# Test\nWHEN x happens, THE SYSTEM SHALL do y.\n")
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "spec",
                "import",
                "--format",
                "ears",
                "--path",
                str(ears_file),
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert "## Intent" in result.output

    def test_import_creates_mission(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from spec_orch.cli import app

        feature = tmp_path / "login.feature"
        feature.write_text(
            "Feature: Login\n\nScenario: OK login\n  Given user\n  When login\n  Then success\n"
        )
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "spec",
                "import",
                "--format",
                "bdd",
                "--path",
                str(feature),
                "--title",
                "Login Import",
                "--repo-root",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0
        assert "mission created" in result.output
