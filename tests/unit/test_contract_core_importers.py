from __future__ import annotations

from pathlib import Path

import pytest

from spec_orch.contract_core.importers import (
    PARSER_REGISTRY,
    load_spec_structure,
    supported_import_formats,
)
from spec_orch.spec_import.models import SpecStructure


def test_contract_core_importers_export_registry() -> None:
    formats = supported_import_formats()

    assert "spec-kit" in formats
    assert "ears" in formats
    assert "bdd" in formats
    assert PARSER_REGISTRY.get("spec-kit") is not None


def test_load_spec_structure_uses_registry(tmp_path: Path) -> None:
    spec_path = tmp_path / "requirements.md"
    spec_path.write_text(
        "\n".join(
            [
                "# Demo Spec",
                "",
                "- Users can sign in",
                "- Users can reset password",
            ]
        ),
        encoding="utf-8",
    )

    structure = load_spec_structure("spec-kit", spec_path)

    assert isinstance(structure, SpecStructure)
    assert structure.source_format == "spec-kit"
    assert structure.source_path


def test_load_spec_structure_rejects_unknown_format(tmp_path: Path) -> None:
    spec_path = tmp_path / "requirements.md"
    spec_path.write_text("# Demo", encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported format"):
        load_spec_structure("unknown", spec_path)
