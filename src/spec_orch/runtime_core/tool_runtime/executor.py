from __future__ import annotations

import logging
import time

from spec_orch.runtime_core.tool_runtime.hooks import HookDispatcher
from spec_orch.runtime_core.tool_runtime.models import (
    ToolBatchPlan,
    ToolConcurrencyClass,
    ToolExecutionRequest,
    ToolExecutionResult,
    ToolLifecycleEvent,
)
from spec_orch.runtime_core.tool_runtime.permissions import evaluate_permission
from spec_orch.runtime_core.tool_runtime.registry import ToolRegistry
from spec_orch.runtime_core.tool_runtime.telemetry import append_tool_lifecycle_event

logger = logging.getLogger(__name__)


def execute_tool_request(
    request: ToolExecutionRequest,
    *,
    registry: ToolRegistry,
    hooks: HookDispatcher | None = None,
) -> ToolExecutionResult:
    dispatcher = hooks or HookDispatcher()
    try:
        definition = registry.resolve(request.tool_name)
    except KeyError:
        result = ToolExecutionResult(
            tool_name=request.tool_name,
            success=False,
            error=f"Unknown tool: {request.tool_name}",
        )
        _emit(
            request,
            ToolLifecycleEvent(
                tool_name=request.tool_name,
                phase="failed",
                success=False,
                error=result.error,
            ),
        )
        return result

    missing = [field for field in definition.required_fields if field not in request.arguments]
    if missing:
        result = ToolExecutionResult(
            tool_name=definition.name,
            success=False,
            error=f"Missing required fields: {', '.join(missing)}",
        )
        _emit(
            request,
            ToolLifecycleEvent(
                tool_name=definition.name,
                phase="failed",
                success=False,
                error=result.error,
                telemetry_label=definition.telemetry_label,
                arguments=request.arguments,
            ),
        )
        return result

    permission = evaluate_permission(
        definition,
        allowed_permissions=request.allowed_permissions,
    )
    if not permission.allowed:
        result = ToolExecutionResult(
            tool_name=definition.name,
            success=False,
            error=permission.reason,
            permission=permission,
        )
        _emit(
            request,
            ToolLifecycleEvent(
                tool_name=definition.name,
                phase="blocked",
                success=False,
                error=result.error,
                telemetry_label=definition.telemetry_label,
                arguments=request.arguments,
            ),
        )
        return result

    dispatcher.run_pre(definition, request)
    _emit(
        request,
        ToolLifecycleEvent(
            tool_name=definition.name,
            phase="started",
            telemetry_label=definition.telemetry_label,
            arguments=request.arguments,
        ),
    )
    started = time.monotonic()
    try:
        output = definition.adapter(request.arguments)
    except Exception as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        result = ToolExecutionResult(
            tool_name=definition.name,
            success=False,
            error=str(exc),
            duration_ms=duration_ms,
            permission=permission,
        )
        dispatcher.run_failure(definition, request, result)
        _emit(
            request,
            ToolLifecycleEvent(
                tool_name=definition.name,
                phase="failed",
                success=False,
                error=result.error,
                duration_ms=duration_ms,
                telemetry_label=definition.telemetry_label,
                arguments=request.arguments,
            ),
        )
        return result

    duration_ms = int((time.monotonic() - started) * 1000)
    result = ToolExecutionResult(
        tool_name=definition.name,
        success=True,
        output=output,
        duration_ms=duration_ms,
        permission=permission,
    )
    dispatcher.run_post(definition, request, result)
    _emit(
        request,
        ToolLifecycleEvent(
            tool_name=definition.name,
            phase="completed",
            success=True,
            duration_ms=duration_ms,
            telemetry_label=definition.telemetry_label,
            arguments=request.arguments,
        ),
    )
    return result


def plan_tool_batches(
    requests: list[ToolExecutionRequest],
    *,
    registry: ToolRegistry,
) -> ToolBatchPlan:
    batches: ToolBatchPlan = []
    current_parallel: list[ToolExecutionRequest] = []
    for request in requests:
        try:
            definition = registry.resolve(request.tool_name)
        except KeyError:
            if current_parallel:
                batches.append(current_parallel)
                current_parallel = []
            # Unknown tools still get their own batch so execute_tool_request()
            # can turn them into structured failures instead of crashing planning.
            batches.append([request])
            continue
        if definition.concurrency_class is ToolConcurrencyClass.SAFE_PARALLEL:
            current_parallel.append(request)
            continue
        if current_parallel:
            batches.append(current_parallel)
            current_parallel = []
        batches.append([request])
    if current_parallel:
        batches.append(current_parallel)
    return batches


def _emit(request: ToolExecutionRequest, event: ToolLifecycleEvent) -> None:
    if request.telemetry_root is None:
        return
    try:
        append_tool_lifecycle_event(request.telemetry_root, event)
    except Exception:
        logger.debug(
            "tool lifecycle emission failed for %s",
            request.tool_name,
            exc_info=True,
        )
