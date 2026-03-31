from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from spec_orch.runtime_core.tool_runtime.models import ToolDefinition


@dataclass(slots=True)
class ToolActivationContext:
    active_tags: set[str] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_tags": sorted(self.active_tags),
            "metadata": dict(self.metadata),
        }


def tool_is_active(definition: ToolDefinition, context: ToolActivationContext) -> bool:
    if definition.activation_tags and not set(definition.activation_tags).issubset(
        context.active_tags
    ):
        return False
    if definition.activate_when is not None:
        return bool(definition.activate_when(context.metadata))
    return True


__all__ = [
    "ToolActivationContext",
    "tool_is_active",
]
