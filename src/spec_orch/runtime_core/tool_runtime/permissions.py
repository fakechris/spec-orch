from __future__ import annotations

from spec_orch.runtime_core.tool_runtime.models import (
    ToolDefinition,
    ToolPermissionDecision,
)


def evaluate_permission(
    definition: ToolDefinition,
    *,
    allowed_permissions: set | None,
) -> ToolPermissionDecision:
    if allowed_permissions is None:
        return ToolPermissionDecision(allowed=True, reason="implicit_allow")
    if definition.permission_class in allowed_permissions:
        return ToolPermissionDecision(allowed=True, reason="explicit_allow")
    return ToolPermissionDecision(
        allowed=False,
        reason=f"permission denied for {definition.permission_class.value}",
    )
