# Runtime Package Absorption Plan

> **Execution Note:** Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Absorb the 2026-03-31 runtime package research into SpecOrch as a coherent architecture program that strengthens runtime completeness without collapsing acceptance judgment into execution control.

**Architecture:** Treat the research as package guidance, not as a request to rewrite the current core seams. `runtime_core`, `runtime_chain`, `decision_core`, `services/memory`, and `acceptance_runtime` remain the existing anchors. The work is to make those anchors package-complete in the places where they are still partial: tool runtime, compaction, memory lifecycle, and long-task observability. `acceptance_core` continues to own judgment and calibration semantics and should consume these packages rather than reimplement them.

**Tech Stack:** Python 3.13, `runtime_core`, `runtime_chain`, `decision_core`, `acceptance_core`, `acceptance_runtime`, file-backed telemetry, shell-based e2e harnesses, Linear, FastAPI dashboard surfaces.

---

## 1. Source Documents

This plan absorbs the following research documents:

- `docs/plans/2026-03-31-agentic-runtime-best-practices.md`
- `docs/plans/2026-03-31-tool-runtime-package.md`
- `docs/plans/2026-03-31-compaction-package.md`
- `docs/plans/2026-03-31-memory-package.md`
- `docs/plans/2026-03-31-long-task-observability-package.md`

They should be treated as architecture inputs and subsystem standards, not as a second product roadmap competing with Epic 4.

## 2. Core Architecture Decision

SpecOrch should absorb this research through three package lines:

1. `runtime_core` package completion
2. `decision_core` / memory lifecycle completion
3. `acceptance_core` / `acceptance_runtime` alignment on top of those packages

This preserves a critical separation:

- runtime packages explain how work executes, survives, and remains inspectable
- acceptance packages explain how results are judged, calibrated, promoted, or dismissed

This plan explicitly rejects pushing tool control, compaction, or memory lifecycle down into Epic 4 local logic.

## 3. Current State Assessment

### Already aligned

- `runtime_core` exists and owns shared execution semantics plus normalized readers/writers.
- `decision_core` exists and owns `DecisionRecord`, `DecisionReview`, intervention queues, and review state.
- `acceptance_core` and `acceptance_runtime` already separate routing/judgment from graph execution.
- `runtime_chain` already provides a root observability substrate with chain events and status snapshots.
- memory already has recorder / analytics / distillation / service layers.

### Still partial

- tool execution is not yet a complete runtime-owned package
- compaction is not yet a first-class runtime subsystem
- long-task observability has chain lineage but not full budget/stall/recap coverage
- memory has useful services but not yet a fully explicit lifecycle package

## 4. Package Absorption Map

### Package A: Tool Runtime Package

**Target owner:** `runtime_core`

**Why:** The research is explicit that tool orchestration must be runtime-owned, not prompt-owned. Today SpecOrch has worker execution, some concurrency control, and telemetry, but not a single package that owns tool identity, validation, permissions, hooks, and pairing integrity as one seam.

**Target modules:**

- `runtime_core/tool_registry.py`
- `runtime_core/tool_executor.py`
- `runtime_core/tool_permissions.py`
- `runtime_core/tool_hooks.py`
- `runtime_core/tool_pairing.py`
- `runtime_core/tool_telemetry.py`

**Completion requirements:**

- registry-owned tool identity
- validation before execution
- runtime-owned concurrency classes
- lifecycle hooks
- tool request/result pairing integrity
- deferred or dynamic tool activation
- progress telemetry for long-running tools

### Package B: Compaction Package

**Target owner:** `runtime_core`

**Why:** Current memory compaction is not runtime context compaction. Long-running execution still lacks a dedicated subsystem for compact boundaries, restore bundles, retries, and recursion guards.

**Target modules:**

- `runtime_core/compaction/triggers.py`
- `runtime_core/compaction/runner.py`
- `runtime_core/compaction/restore.py`
- `runtime_core/compaction/telemetry.py`

**Completion requirements:**

- explicit compaction trigger policy
- recursion and collapse guards
- prompt-too-long retry path
- structured state restoration
- explicit compact boundary markers
- compaction telemetry visible to operators

### Package C: Memory Lifecycle Package

**Target owner:** `decision_core` plus `services/memory`

**Why:** Memory is already useful, but still presents as service slices rather than a clearly declared lifecycle with cadence, write scope, hygiene, and shared-memory discipline.

**Target shape:**

- session memory
- extracted memory
- reflective consolidation
- shared/team memory

**Completion requirements:**

- explicit cadence and write gating
- restricted write scope
- dedupe and freshness tracking
- consolidation locking and anti-recursion rules
- provenance-aware shared-memory hygiene

### Package D: Long-Task Observability Package

**Target owner:** `runtime_chain` plus `runtime_core`

**Why:** `runtime_chain` solves lineage and phase status, but the research package requires more than chain events. Operators need budget posture, stall signals, run recaps, and step/batch summaries.

**Target modules:**

- `runtime_core/observability/budget.py`
- `runtime_core/observability/progress.py`
- `runtime_core/observability/events.py`
- `runtime_core/observability/recap.py`

**Completion requirements:**

- budget visibility
- progress summaries
- step/batch summaries
- stall and diminishing-returns signals
- structured event trail
- human-readable recaps

## 5. Relationship To Acceptance

The package documents do not invalidate Epic 4. They sharpen its boundary.

`acceptance_core` should continue to own:

- routing semantics
- judgment classes
- disposition and review transitions
- compare and calibration semantics
- candidate-to-fixture graduation semantics

`acceptance_runtime` should consume package capabilities from runtime and memory layers:

- tool runtime
- compaction continuity
- observability summaries
- memory-fed routing or tuning inputs

It should not grow its own duplicate implementations of these concerns.

## 6. Recommended Execution Order

### Tranche P1: Runtime package completion

Focus:

- Tool Runtime Package
- Compaction Package
- Long-Task Observability completion

Why first:

- these are execution survival and inspection primitives
- later acceptance and memory behavior becomes easier to tune once these exist

### Tranche P2: Memory lifecycle completion

Focus:

- cadence
- scoped writes
- consolidation hygiene
- shared/team memory discipline

Why second:

- memory becomes safer and more reusable once runtime boundaries are stable

### Tranche P3: Acceptance alignment and deeper calibration

Focus:

- make `acceptance_runtime` consume the new packages
- improve workflow tuning on top of stable runtime surfaces
- deepen compare / candidate review / fixture generation only after package support exists

## 7. Linear Mapping

**Linear epic:** `SON-346` `[Epic] Runtime Package Completion and Architecture Absorption`

Child issues:

1. `SON-347` package-level runtime architecture alignment
2. `SON-348` tool runtime package completion
3. `SON-349` compaction package completion
4. `SON-350` memory lifecycle package completion
5. `SON-351` long-task observability package completion
6. `SON-352` acceptance-runtime alignment on top of those packages

The epic should be managed separately from Epic 4 historical work so the architecture package program can move independently without rewriting prior completion state.

## 8. Completion Gate

This architecture absorption should be considered complete when:

- runtime control, compaction, observability, and memory all exist as explicit packages rather than scattered behaviors
- acceptance runtime consumes those packages instead of duplicating them
- operators can diagnose long work through one canonical runtime view
- long context survival is a runtime-owned mechanism rather than an ad hoc prompt behavior
- the remaining deep acceptance work is clearly product-layer work, not missing infrastructure

## 9. Current Completion Status

As of 2026-03-31, the runtime package absorption program is implemented to completion for
the baseline defined in this plan.

### Implemented packages

- `SON-348` Tool Runtime Package
  - `runtime_core.tool_runtime` now owns registry, validation, permission gating, lifecycle
    hooks, batch planning, and lifecycle telemetry.
  - ACPX session ensure/cancel flows now run through this package.
- `SON-349` Compaction Package
  - `runtime_core.compaction` now owns trigger evaluation, restore bundles, boundary markers,
    and compaction event/status persistence.
  - `run_controller` now performs compaction through explicit runtime-owned decisions.
- `SON-350` Memory Lifecycle Package
  - `services.memory.lifecycle` now owns session snapshot cadence, consolidation locks, and
    shared-memory freshness gating.
  - `MemoryService` now exposes lifecycle methods instead of keeping this logic implicit.
- `SON-351` Long-Task Observability Package
  - `runtime_core.observability` now owns budget visibility, progress events, live summaries,
    step summaries, batch summaries, stall signals, and human-readable recaps.
- `SON-352` Acceptance Runtime Alignment
  - `acceptance_runtime.runner` now consumes runtime-owned observability and memory lifecycle
    packages.
  - `round_orchestrator` now wires those package surfaces into real acceptance graph runs.

### Verification snapshot

- runtime/acceptance package matrix: `106 passed`
- focused observability/acceptance runner regression matrix: `10 passed`
- `ruff check`: passed
- `ruff format --check`: passed
- `mypy`: passed
