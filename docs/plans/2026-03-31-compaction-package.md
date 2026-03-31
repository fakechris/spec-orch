# Compaction Package

**Date:** 2026-03-31  
**Program Fit:** Epics 2-3, with downstream impact on Epic 4  
**Status:** Adopted subsystem standard

## Goal

Define the minimum complete package for context compaction in long-running agent
sessions.

Compaction should preserve workability, not just shrink token count.

## Core Position

Compaction is not a summarization feature.

It is a context-survival subsystem.

Partial adoption is risky.

Examples of risky partial adoption:

- generating a summary without restoring runtime attachments
- triggering compaction without recursion guards
- compacting transcript text without carrying forward discovered tools
- retrying prompt-too-long failures without a formal fallback path

These failures often look acceptable in short demos but create silent memory and
control-flow loss in real work.

## Package Boundary

The Compaction Package owns:

- compaction triggers
- budget-aware compaction thresholds
- recursion guards
- compaction retry policy
- transcript boundary management
- restored state attachments
- post-compact cleanup
- compaction telemetry

It does **not** own:

- long-term memory extraction policy
- acceptance judgment semantics
- calibration review

## Required Capabilities

### 1. Explicit Trigger Policy

Compaction should trigger through runtime policy, not ad hoc prompt choices.

Inputs should include:

- effective context window
- reserved output budget
- current transcript size
- recent growth rate
- active run posture

### 2. Recursion And Collapse Guards

The runtime should explicitly prevent:

- compaction recursively triggering compaction
- memory update flows recursively triggering compaction loops
- repeated failed compaction attempts creating collapse storms

### 3. Retry Path For Prompt-Too-Long Failures

If compaction itself exceeds prompt limits, the system should have a bounded
fallback path.

Examples:

- truncate oldest message groups by policy
- retry with a smaller source slice
- fall back to memory-backed compact input

### 4. Structured State Restoration

After compaction, the runtime should restore or reattach:

- current plan state
- active skills or task attachments
- discovered or deferred tool state
- session-start or environment context
- essential recent file references

The summary alone is not enough.

### 5. Boundary Marking

The runtime should keep explicit compact boundaries so later systems know:

- where the session was compacted
- what survived the boundary
- what was intentionally dropped

### 6. Telemetry

Compaction should emit structured events for:

- trigger reason
- source size
- output size
- retries
- fallback path used
- restored state count
- post-compact effective budget

## Adoption Rule

If SpecOrch introduces compaction into long-running execution, it should adopt
this as a complete package.

Do not ship compaction as "generate a summary and continue."

## Recommended Runtime Shape

Suggested ownership split:

- `runtime_core.compaction.triggers`
- `runtime_core.compaction.runner`
- `runtime_core.compaction.restore`
- `runtime_core.compaction.telemetry`

Suggested supporting objects:

- `CompactionTriggerDecision`
- `CompactionInputSlice`
- `CompactionResult`
- `CompactionRestoreBundle`
- `CompactionTelemetryEvent`

## Relationship To Memory

Compaction and memory should be separate subsystems.

However, session memory may be a valid compaction source when:

- it is recent enough
- it is trustworthy enough
- runtime policy allows it

That should be a first-class path, not a hidden trick.

## Failure Modes When Adopted Incompletely

### Summary-only compaction

Creates apparent continuity but loses operational state.

### Thresholds without restore logic

Creates brittle sessions that resume in the wrong posture.

### Restore logic without cleanup

Creates duplicated or contradictory context after compaction.

### Compaction without telemetry

Makes long-task debugging almost impossible.

## SpecOrch Recommendation

Adopt the Compaction Package as an Epic 2 runtime-core concern and treat it as
prerequisite infrastructure for:

- long-running graph execution
- memory extraction
- acceptance runtime continuity

Epic 4 should assume compaction exists, not reinvent it locally.

## Success Criteria

The package should be considered complete when:

- compaction triggers by explicit runtime policy
- compaction cannot recurse uncontrollably
- prompt-too-long failures have a bounded fallback
- critical state is restored after compaction
- compact boundaries are explicit
- operators can inspect compaction telemetry when tasks drift

## Completion Snapshot

This package is now absorbed into `runtime_core.compaction`.

Implemented baseline:

- explicit trigger evaluation
- recursion/collapse guard via runtime lock
- prompt-too-long retry and fallback path
- restore bundles from compact boundaries
- explicit boundary markers and last-compaction status
- operator-readable compaction telemetry
