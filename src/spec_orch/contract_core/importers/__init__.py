"""Contract-core import registry and normalization entrypoints."""

from pathlib import Path

from spec_orch.spec_import.models import SpecStructure
from spec_orch.spec_import.parser import PARSER_REGISTRY, SpecParser


def supported_import_formats() -> list[str]:
    """Return supported external spec import formats."""
    return PARSER_REGISTRY.supported_formats()


def load_spec_structure(format_id: str, source_path: Path) -> SpecStructure:
    """Load a normalized spec structure using the registered parser."""
    parser = PARSER_REGISTRY.get(format_id)
    if parser is None:
        supported = ", ".join(supported_import_formats())
        raise ValueError(f"unsupported format '{format_id}'. Supported: {supported}")
    return parser.parse(source_path)


__all__ = [
    "PARSER_REGISTRY",
    "SpecParser",
    "SpecStructure",
    "load_spec_structure",
    "supported_import_formats",
]
