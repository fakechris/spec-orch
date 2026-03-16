"""Spec import — parse external spec formats into SpecStructure."""

from spec_orch.spec_import.models import SpecStructure
from spec_orch.spec_import.parser import PARSER_REGISTRY, SpecParser

__all__ = [
    "PARSER_REGISTRY",
    "SpecParser",
    "SpecStructure",
]
