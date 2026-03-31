from __future__ import annotations

from pathlib import Path

from spec_orch.runtime_core.tool_runtime.executor import execute_tool_request, plan_tool_batches
from spec_orch.runtime_core.tool_runtime.hooks import HookDispatcher
from spec_orch.runtime_core.tool_runtime.models import (
    ToolConcurrencyClass,
    ToolDefinition,
    ToolExecutionRequest,
    ToolPermissionClass,
)
from spec_orch.runtime_core.tool_runtime.registry import ToolRegistry
from spec_orch.runtime_core.tool_runtime.telemetry import read_tool_lifecycle_events


def test_execute_tool_request_validates_permissions_and_emits_lifecycle(
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []

    def adapter(arguments: dict[str, object]) -> dict[str, object]:
        calls.append(arguments)
        return {"ok": True, "echo": arguments["value"]}

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="demo.echo",
            aliases=("echo",),
            adapter=adapter,
            required_fields=("value",),
            permission_class=ToolPermissionClass.WORKSPACE_WRITE,
            concurrency_class=ToolConcurrencyClass.SAFE_PARALLEL,
            telemetry_label="demo-echo",
        )
    )
    hook_events: list[str] = []
    hooks = HookDispatcher(
        pre_hooks=[lambda definition, request: hook_events.append(f"pre:{definition.name}")],
        post_hooks=[
            lambda definition, request, result: hook_events.append(f"post:{result.tool_name}")
        ],
    )

    result = execute_tool_request(
        ToolExecutionRequest(
            tool_name="echo",
            arguments={"value": "hello"},
            allowed_permissions={ToolPermissionClass.WORKSPACE_WRITE},
            telemetry_root=tmp_path,
        ),
        registry=registry,
        hooks=hooks,
    )

    assert result.success is True
    assert result.output == {"ok": True, "echo": "hello"}
    assert calls == [{"value": "hello"}]
    assert hook_events == ["pre:demo.echo", "post:demo.echo"]
    lifecycle = read_tool_lifecycle_events(tmp_path)
    assert [event.phase for event in lifecycle] == ["started", "completed"]
    assert lifecycle[0].tool_name == "demo.echo"
    assert lifecycle[1].success is True


def test_execute_tool_request_blocks_missing_permission(tmp_path: Path) -> None:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="demo.admin",
            adapter=lambda arguments: {"ok": True},
            permission_class=ToolPermissionClass.SESSION_ADMIN,
        )
    )

    result = execute_tool_request(
        ToolExecutionRequest(
            tool_name="demo.admin",
            arguments={},
            allowed_permissions={ToolPermissionClass.READ_ONLY},
            telemetry_root=tmp_path,
        ),
        registry=registry,
    )

    assert result.success is False
    assert "permission" in result.error.lower()
    lifecycle = read_tool_lifecycle_events(tmp_path)
    assert [event.phase for event in lifecycle] == ["blocked"]


def test_plan_tool_batches_respects_concurrency_classes() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="serial.tool",
            adapter=lambda arguments: {},
            concurrency_class=ToolConcurrencyClass.SERIAL,
        )
    )
    registry.register(
        ToolDefinition(
            name="parallel.tool",
            adapter=lambda arguments: {},
            concurrency_class=ToolConcurrencyClass.SAFE_PARALLEL,
        )
    )

    plan = plan_tool_batches(
        [
            ToolExecutionRequest(tool_name="parallel.tool", arguments={}),
            ToolExecutionRequest(tool_name="parallel.tool", arguments={}),
            ToolExecutionRequest(tool_name="serial.tool", arguments={}),
            ToolExecutionRequest(tool_name="parallel.tool", arguments={}),
        ],
        registry=registry,
    )

    assert [[request.tool_name for request in batch] for batch in plan] == [
        ["parallel.tool", "parallel.tool"],
        ["serial.tool"],
        ["parallel.tool"],
    ]


def test_execute_tool_request_rejects_missing_required_fields(tmp_path: Path) -> None:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="demo.required",
            adapter=lambda arguments: {},
            required_fields=("value",),
        )
    )

    result = execute_tool_request(
        ToolExecutionRequest(
            tool_name="demo.required",
            arguments={},
            telemetry_root=tmp_path,
        ),
        registry=registry,
    )

    assert result.success is False
    assert "missing required fields" in result.error.lower()
    lifecycle = read_tool_lifecycle_events(tmp_path)
    assert lifecycle[0].phase == "failed"
    assert lifecycle[0].success is False
