from __future__ import annotations

from spec_orch.runtime_core.tool_runtime.activation import (
    ToolActivationContext,
    tool_is_active,
)
from spec_orch.runtime_core.tool_runtime.models import ToolDefinition


class ToolRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, ToolDefinition] = {}
        self._aliases: dict[str, str] = {}

    def register(self, definition: ToolDefinition) -> None:
        self._definitions[definition.name] = definition
        for alias in definition.aliases:
            self._aliases[alias] = definition.name

    def resolve(self, name: str) -> ToolDefinition:
        canonical = self._aliases.get(name, name)
        if canonical not in self._definitions:
            raise KeyError(name)
        return self._definitions[canonical]

    def resolve_active(self, name: str, context: ToolActivationContext) -> ToolDefinition:
        definition = self.resolve(name)
        if not tool_is_active(definition, context):
            raise KeyError(name)
        return definition

    def active_definitions(self, context: ToolActivationContext) -> list[ToolDefinition]:
        return [
            definition
            for definition in self._definitions.values()
            if tool_is_active(definition, context)
        ]

    def __contains__(self, name: str) -> bool:
        canonical = self._aliases.get(name, name)
        return canonical in self._definitions
