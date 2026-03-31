from __future__ import annotations

from collections.abc import Callable
from typing import Any

from spec_orch.runtime_core.tool_runtime.models import (
    ToolDefinition,
    ToolExecutionRequest,
    ToolExecutionResult,
)

PreHook = Callable[[ToolDefinition, ToolExecutionRequest], Any]
PostHook = Callable[[ToolDefinition, ToolExecutionRequest, ToolExecutionResult], Any]
FailureHook = Callable[[ToolDefinition, ToolExecutionRequest, ToolExecutionResult], Any]


class HookDispatcher:
    def __init__(
        self,
        *,
        pre_hooks: list[PreHook] | None = None,
        post_hooks: list[PostHook] | None = None,
        failure_hooks: list[FailureHook] | None = None,
    ) -> None:
        self.pre_hooks = pre_hooks or []
        self.post_hooks = post_hooks or []
        self.failure_hooks = failure_hooks or []

    def run_pre(self, definition: ToolDefinition, request: ToolExecutionRequest) -> None:
        for hook in self.pre_hooks:
            hook(definition, request)

    def run_post(
        self,
        definition: ToolDefinition,
        request: ToolExecutionRequest,
        result: ToolExecutionResult,
    ) -> None:
        for hook in self.post_hooks:
            hook(definition, request, result)

    def run_failure(
        self,
        definition: ToolDefinition,
        request: ToolExecutionRequest,
        result: ToolExecutionResult,
    ) -> None:
        for hook in self.failure_hooks:
            hook(definition, request, result)
