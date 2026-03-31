# Agentic Runtime Best Practices

**Date:** 2026-03-31  
**Program Fit:** Epics 2-4, with downstream impact on Epics 5-7  
**Status:** Research synthesis

## Goal

Capture the best practices for building a long-running agentic runtime that is:

- tool-safe
- context-stable
- memory-aware
- observable
- compatible with later acceptance judgment and calibration

This document does not describe one implementation. It defines the operating
principles we should treat as the default standard for complex agent runtime
work inside SpecOrch.

Companion package documents:

- `2026-03-31-tool-runtime-package.md`
- `2026-03-31-compaction-package.md`
- `2026-03-31-memory-package.md`
- `2026-03-31-long-task-observability-package.md`

## Executive Summary

The hardest agent systems problems are not solved by bigger prompts.

They are solved by a runtime that treats these as first-class systems:

1. tool orchestration
2. context compaction
3. memory extraction and consolidation
4. progress and stall observability
5. explicit judgment and calibration layers

The most important design principle is:

**Execution control, context survival, and memory persistence must be code-owned.**

Prompts should remain bounded reasoning surfaces, not the primary owner of:

- control flow
- lifecycle state
- safety policy
- context repair
- review queues

## 1. Separate Runtime Control From Judgment

Do not collapse everything into one "agent mode."

At minimum, the system should keep these layers distinct:

- execution runtime
- judgment model
- calibration layer
- memory layer

### Runtime layer

Owns:

- tool orchestration
- graph execution
- permission gating
- hook execution
- compaction
- artifact persistence

### Judgment layer

Owns:

- `confirmed_issue`
- `candidate_finding`
- `observation`
- review-state transitions
- promotion and dismissal semantics

### Calibration layer

Owns:

- compare overlay
- fixture-backed regression
- drift detection
- candidate-to-fixture graduation

### Memory layer

Owns:

- session memory
- extracted long-term notes
- consolidated reflective memory
- shared/team memory

If these are mixed into one prompt or one service blob, the system becomes hard
to tune and impossible to reason about.

## 2. Tool Calls Must Be Runtime-Owned

Tool use should be treated as a controlled runtime, not a raw model capability.

### Required controls

- explicit tool registry
- input validation
- permission gating
- pre/post tool hook support
- telemetry and timing
- in-progress tracking
- failure classification
- pairing repair between tool calls and tool results

### Concurrency rule

Only run tool calls concurrently when the runtime can prove they are
concurrency-safe.

The system should partition tool calls into:

- concurrency-safe batches
- serial batches

This must be a runtime decision, not a prompt convention.

### Dynamic tool loading

Do not assume all tools should be fully declared and fully active all the time.

Prefer:

- deferred tools
- discovered tools
- model-aware schema filtering

This reduces context pressure and keeps tool state explicit.

## 3. Long-Running Tasks Need More Than "Keep Going"

A mature long-running agent needs explicit controls for:

- continuation
- diminishing returns
- stall detection
- intermediate progress summaries
- safe abort behavior

### Budget tracking

Every long-running path should have a budget tracker with:

- total budget
- continuation count
- token delta since last check
- diminishing-returns heuristic

The runtime should be able to stop or nudge continuation based on:

- budget exhaustion
- repeated low-yield turns
- duration

### Progress summaries

Periodic background summarization is valuable when:

- the task is long
- a user or operator needs a compact view of what the agent is doing
- subagents or background loops need visible progress

Progress summaries should be:

- short
- non-authoritative
- derived from current transcript state

They are observability aids, not acceptance judgments.

### Advisor / second-opinion support

It is useful to support a stronger reviewer or advisor pass:

- before substantive work
- when stuck
- before declaring completion

But this is a guidance layer, not a replacement for acceptance judgment.

## 4. Compaction Must Preserve Workability, Not Just Shrink Tokens

Conversation compaction is not a summarization feature.

It is a context-survival subsystem.

### Minimum requirements

After compaction, the runtime should preserve or restore:

- current task/plan state
- invoked skill state
- discovered tool state
- recent relevant file state
- hook-relevant session state
- enough transcript linkage to continue safely

### Compaction design rules

- compaction must have explicit recursion guards
- compaction failures need retry strategy for prompt-too-long scenarios
- post-compact cleanup must be centralized
- restored context should be attached in structured form, not implied

### Session-memory compaction

When session memory exists, it should be considered as a compaction source, not
just a side feature.

This allows:

- more stable long sessions
- resumed sessions to inherit useful continuity

## 5. Memory Must Be A Dedicated Subsystem

Memory should not be implemented as a loose collection of notes, ad hoc
summaries, or prompt appendices.

At minimum, a mature system should distinguish:

- session memory
- extracted durable memory
- reflective consolidation
- shared or team memory

These have different:

- write cadence
- trust posture
- retention needs
- safety requirements

The runtime should never assume that "memory exists" is enough. It must know:

- what kind of memory it is using
- how fresh it is
- who was allowed to write it
- whether it is safe to reuse in the current run

## 6. Observability Must Explain The Run, Not Just Display Motion

A long-running agent is not understandable through raw transcript alone.

The runtime should expose:

- budget posture
- continuation count
- progress summaries
- step or batch summaries
- stall and diminishing-returns signals
- handoff recaps
- structured event trail

These are required for:

- operator trust
- debugging
- workflow tuning
- compare calibration later

Without this layer, the system may look active while being effectively blind.

## 7. Workflow Tuning Is Distinct From Prompt Tuning

Prompt tuning changes how a model reasons inside a bounded step.

Workflow tuning changes:

- graph shape
- step boundaries
- loop placement
- gate placement
- artifact persistence points
- retry and stop policy

These should be treated as different activities, with different artifacts and
different review criteria.

Do not let runtime quality work collapse into prompt editing alone.

## 8. Complete-Mechanism Adoption Rule

For mature runtime patterns, the correct default is:

**adopt by subsystem seam, not by isolated feature fragment.**

This means:

- if we improve tool execution, we should adopt a full Tool Runtime Package
- if we improve compaction, we should adopt a full Compaction Package
- if we improve memory, we should adopt a full Memory Package
- if we improve long-run visibility, we should adopt a full Long-Task
  Observability Package

The reason is simple:

partial adoption creates systems that demo well but fail under long, branching,
or high-volume workloads.

## 9. What SpecOrch Should Adopt As Standard

SpecOrch should treat the following as default runtime standards:

### Adopt as full subsystem packages

- Tool Runtime Package
- Compaction Package
- Memory Package
- Long-Task Observability Package

### Keep as SpecOrch-owned product semantics

- acceptance judgment classes
- candidate-finding review lifecycle
- compare overlay semantics
- candidate-to-fixture graduation
- surface pack design

In other words:

- the lower runtime should follow proven subsystem practice
- the upper judgment layer should remain our product layer

## 10. Recommended Sequencing

The safest sequence is:

1. stabilize `runtime_core` seams for tool execution, compaction, and
   observability
2. stabilize `decision_core` seams for memory lifecycle
3. connect Epic 4 routing and graph execution to those seams
4. only then deepen candidate-finding review and compare calibration

This avoids building judgment features on top of unstable runtime behavior.

## 11. Final Conclusion

The strongest conclusion from this research is:

**complex agent systems become reliable when runtime mechanisms are owned in
code as complete subsystems, while judgment and calibration remain explicit,
later layers.**

For SpecOrch, this means:

- do not treat tool control, compaction, memory, or observability as optional
  helpers
- do not partially imitate mature long-task mechanisms
- do not mix runtime control with acceptance judgment

The practical takeaway is:

- adopt the runtime packages whole
- keep Epic 4 focused on judgment governance
- let calibration build on stable runtime artifacts rather than prompt-only
  behavior
- reduced pressure on transcript-only compaction

## 5. Memory Must Be A Dedicated Subsystem

Memory should not be treated as one blob or one command.

At minimum, use a layered model:

1. session memory
2. extracted durable memories
3. reflective consolidation
4. shared/team memory

### Session memory

Purpose:

- preserve broader session context
- support compaction
- support "return after being away" summaries

Update cadence should be threshold-driven:

- minimum token growth
- tool-call count
- natural conversation break

### Extracted durable memories

Use a dedicated memory-extraction runtime with:

- restricted tool permissions
- explicit write scope
- bounded turn count
- duplicate avoidance

This should be a subagent or forked-agent workflow, not an uncontrolled
continuation of the main task loop.

### Reflective consolidation

Periodic consolidation should exist separately from per-session extraction.

This layer should:

- scan recent sessions
- merge or rewrite durable memories
- delete contradicted facts
- keep memory indexes short and navigable

### Shared/team memory

If shared memory exists, it needs:

- secret scanning
- sync discipline
- repo/team scoping
- watcher and conflict behavior

Shared memory is not just a folder. It is a distributed state surface.

## 6. Observability Must Be Per-Step, Not Just End-of-Run

A runtime that only emits final summaries is too opaque.

The system should make step-level state observable through structured artifacts.

### Per-step observability should include

- step key
- graph profile
- inputs
- outputs
- timing
- warnings
- transition decision

This matters for:

- debugging
- runtime tuning
- compare drift analysis
- provenance for candidate findings

Observability artifacts are especially important when the runtime uses:

- tuned graphs
- loops
- gates
- retries
- compare overlays

## 7. Workflow Tuning Is A First-Class Engineering Activity

Prompt tuning is not enough.

The runtime should recognize `workflow tuning` as a separate discipline.

### Prompt tuning changes

- instruction wording
- evaluator phrasing
- schema wording
- localized reasoning guidance

### Workflow tuning changes

- graph shape
- step ordering
- loop placement
- gate placement
- step-scoped artifact contracts
- handoff structure

If workflow tuning is not named explicitly, teams tend to hide orchestration
problems inside prompt churn.

## 8. Unknown Surfaces Need A Conservative Fallback

When the system cannot confidently activate a known contract, graph, or surface
pack, it should not force strong judgment.

Use a fallback mode with these goals:

- surface mapping
- candidate route discovery
- evidence capture
- cheap next promotion test

This should produce:

- `observation`
- or at most a weak `candidate_finding`

It should not aggressively promote or file.

## 9. Acceptance Judgment Is A Later Layer, Not A Tool Runtime Detail

The runtime must be built so that acceptance judgment can sit on top cleanly.

That means the runtime should already preserve:

- step provenance
- graph identity
- route identity
- evidence references
- compare-ready artifacts

Without those, later judgment layers are forced to guess.

### Practical rule

Runtime artifacts should make it possible for acceptance judgment to answer:

- what step created this signal?
- what evidence supports it?
- what baseline could it be compared to?
- was this a graph design issue, a prompt issue, or a surface issue?

## 10. Recommended Default Architecture For SpecOrch

### Code-owned

- `runtime_core`
- `decision_core`
- `acceptance_runtime`
- tool hooks and permission gates
- compaction and post-compaction restoration
- memory extraction and consolidation runtimes
- artifact persistence

### Prompt-owned

- local reasoning inside a step
- critique wording
- evidence interpretation
- bounded review writing
- memory synthesis content

### Never prompt-owned

- state transitions
- graph shape
- queue semantics
- tool permissions
- compaction policy
- acceptance ontology

## 11. Recommended Near-Term Priorities

Given the current program structure, the best next steps are:

1. keep strengthening `runtime_core` and `decision_core`
2. keep `acceptance_runtime` explicit and graph-based
3. preserve provenance-rich step artifacts
4. keep memory as a dedicated subsystem, not a sidecar utility
5. let Epic 4 build on top of these seams instead of bypassing them

## 12. Bottom Line

The best agent systems are not defined by bigger prompts or more model freedom.

They are defined by a runtime that:

- controls tools explicitly
- survives context pressure
- maintains durable memory
- emits structured observability
- leaves clean seams for later judgment and calibration

That is the standard we should build toward.
