"""Parser protocol and registry for spec import formats."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from spec_orch.spec_import.models import SpecStructure


@runtime_checkable
class SpecParser(Protocol):
    """Interface for spec format parsers."""

    @property
    def format_id(self) -> str: ...

    def parse(self, path: Path) -> SpecStructure: ...


class ParserRegistry:
    """Registry mapping format IDs to parser instances."""

    def __init__(self) -> None:
        self._parsers: dict[str, SpecParser] = {}

    def register(self, parser: SpecParser) -> None:
        self._parsers[parser.format_id] = parser

    def get(self, format_id: str) -> SpecParser | None:
        return self._parsers.get(format_id)

    def supported_formats(self) -> list[str]:
        return sorted(self._parsers.keys())


def _build_default_registry() -> ParserRegistry:
    from spec_orch.spec_import.bdd import BddParser
    from spec_orch.spec_import.ears import EarsParser
    from spec_orch.spec_import.spec_kit import SpecKitParser

    registry = ParserRegistry()
    registry.register(SpecKitParser())
    registry.register(EarsParser())
    registry.register(BddParser())
    return registry


PARSER_REGISTRY = _build_default_registry()
