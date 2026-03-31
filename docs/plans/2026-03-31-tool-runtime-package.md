# Tool Runtime Package

**Date:** 2026-03-31  
**Program Fit:** Epics 2-4  
**Status:** Recommended subsystem standard

## Goal

Define the minimum complete package for safe, long-running tool execution in an
agentic runtime.

This document treats tool use as a runtime subsystem, not a prompt convention.

## Core Position

For complex agent systems, tool calling should be adopted as a complete runtime
seam.

Partial adoption is risky.

Examples of risky partial adoption:

- adding permission checks without lifecycle hooks
- adding hooks without pairing repair
- adding concurrency without in-progress tracking
- adding dynamic tools without schema/state observability

The result is usually a system that appears capable in short runs but becomes
fragile under long, branching, or parallel workloads.

## Package Boundary

The Tool Runtime Package owns:

- tool registry
- tool schema validation
- permission gating
- concurrency policy
- pre-tool hooks
- post-tool hooks
- failure hooks
- tool execution telemetry
- tool-use / tool-result pairing integrity
- deferred or dynamic tool activation
- tool progress events

It does **not** own:

- acceptance judgment
- candidate-finding review semantics
- calibration or compare overlays
- product-specific UX critique

## Required Capabilities

### 1. Registry-Owned Tool Identity

Every tool must resolve through a registry-owned identity layer.

The runtime should know:

- canonical tool name
- aliases or deprecated names
- input schema
- execution adapter
- permission class
- concurrency class
- telemetry label

The model should never be the only source of truth for what a tool is.

### 2. Validation Before Execution

Every tool call should pass through:

- tool existence check
- input parsing
- schema validation
- permission check
- pre-execution hook chain

Execution should not begin until all of these pass.

### 3. Concurrency Policy In Code

Concurrency should be decided by the runtime.

The runtime should partition tool calls into:

- concurrency-safe batches
- serial-only calls

This decision should depend on tool-level semantics, not prompt wording.

### 4. Lifecycle Hooks

Tool execution should support:

- pre-tool hooks
- post-tool hooks
- failure hooks

Hooks are not just for logging. They are the seam for:

- policy enforcement
- contextual warnings
- additional artifact generation
- stop / retry decisions

### 5. Pairing Integrity

The runtime should maintain explicit integrity between:

- tool request
- tool execution
- tool result

If the transcript or message structure drifts, the runtime should be able to
repair or reject broken pairings.

### 6. Dynamic Tool Activation

The runtime should support:

- deferred tools
- discovered tools
- schema filtering based on active context

This keeps context smaller and makes tool availability explicit.

### 7. Telemetry And Progress

Every tool execution should emit structured runtime data:

- start/end time
- duration
- tool key
- success/failure
- validation failure type
- permission outcome
- hook outcome
- retry count

Long-running tools should also be able to emit progress updates.

## Adoption Rule

If SpecOrch upgrades tool execution, it should adopt this package as a whole
subsystem.

Do not treat these as optional embellishments around raw model tool calling.

## Recommended Runtime Shape

Suggested ownership split:

- `runtime_core.tool_registry`
- `runtime_core.tool_executor`
- `runtime_core.tool_permissions`
- `runtime_core.tool_hooks`
- `runtime_core.tool_telemetry`
- `runtime_core.tool_pairing`

Suggested supporting objects:

- `ToolDefinition`
- `ToolExecutionRequest`
- `ToolExecutionResult`
- `ToolPermissionDecision`
- `ToolLifecycleEvent`
- `ToolBatchPlan`

## Failure Modes When Adopted Incompletely

### Hooks without execution ownership

Results in policy being bypassed by edge paths.

### Concurrency without explicit safety classes

Results in state corruption or misleading transcript ordering.

### Dynamic tools without state carryover

Results in missing tools after compaction or resume.

### Telemetry without lifecycle semantics

Results in dashboards that show activity but cannot explain what happened.

## SpecOrch Recommendation

Adopt the Tool Runtime Package as an Epic 2 runtime-core concern first.

Epic 4 should depend on this seam rather than growing its own custom tool
control rules.

This keeps:

- execution policy in `runtime_core`
- judgment policy in `acceptance_core`

## Success Criteria

The package should be considered complete when:

- every tool call is registry-owned
- every execution path is validated and permission-gated
- concurrency decisions are code-owned
- tool request/result integrity is enforced
- hooks and telemetry are first-class
- deferred tool state survives long-running session behavior
