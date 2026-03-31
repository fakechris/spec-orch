# Memory Package

**Date:** 2026-03-31  
**Program Fit:** Epics 3-6  
**Status:** Adopted subsystem standard

## Goal

Define the minimum complete package for memory in a long-running agent system.

Memory should be treated as a subsystem with lifecycle, scope, and hygiene
rules.

## Core Position

Memory is not "extra prompt context."

It is a managed system for preserving useful knowledge across:

- a session
- multiple sessions
- multiple operators or agents

Partial adoption is risky.

Examples of risky partial adoption:

- auto-writing notes without extraction cadence
- storing memory without write-scope controls
- adding reflective consolidation without locking or dedupe
- syncing shared memory without hygiene or secret checks

These usually produce noisy memory, stale memory, or unsafe memory.

## Package Boundary

The Memory Package owns:

- session memory
- extracted memory
- reflective consolidation
- shared or team memory
- memory hygiene and write-scope rules
- memory cadence and gating

It does **not** own:

- acceptance finding review state
- calibration fixtures
- runtime compaction triggers

## Memory Layers

### 1. Session Memory

Captures the compact, useful state of the current session.

Purpose:

- survive long work
- improve compact continuity
- keep local project context stable

### 2. Extracted Memory

Promotes useful durable facts from transcript activity into more stable memory.

Purpose:

- preserve reusable lessons
- keep session memory from bloating
- give later runs useful project knowledge

### 3. Reflective Consolidation

Periodically rewrites or consolidates prior memory into a cleaner long-term
form.

Purpose:

- reduce duplication
- resolve stale or conflicting entries
- keep memory coherent over time

### 4. Shared / Team Memory

Supports controlled reuse of durable knowledge across collaborators, agents, or
worktrees.

Purpose:

- make known policies and lessons portable
- avoid relearning the same environment truths repeatedly

## Required Capabilities

### 1. Explicit Cadence

Memory writes should be gated by policy.

Examples:

- token-growth thresholds
- tool-call thresholds
- natural task breakpoints
- end-of-run extraction
- scheduled reflective windows

### 2. Restricted Write Scope

Memory-writing flows should be limited to explicit memory targets.

Do not give memory extraction or consolidation flows broad write access to the
codebase.

### 3. Dedupe And Freshness

The package should track:

- duplicate facts
- stale facts
- conflicting facts
- last-refresh timing

### 4. Consolidation With Locking

Reflective consolidation should be guarded against:

- concurrent writers
- partial overwrite
- runaway recursive reflection

### 5. Shared-Memory Hygiene

Shared memory should support:

- path or repo scoping
- secret scanning or equivalent hygiene
- sync conflict handling
- provenance or source attribution

## Adoption Rule

If SpecOrch adopts memory as a core capability, it should adopt the full
lifecycle:

- session capture
- extraction
- consolidation
- shared-memory hygiene

Do not stop at "write a memory file sometimes."

## Recommended Runtime Shape

Suggested ownership split:

- `decision_core.memory.session`
- `decision_core.memory.extract`
- `decision_core.memory.consolidate`
- `decision_core.memory.shared`

Suggested supporting objects:

- `SessionMemorySnapshot`
- `MemoryExtractionCandidate`
- `ExtractedMemoryEntry`
- `MemoryConsolidationRun`
- `SharedMemorySyncEvent`

## Relationship To Acceptance Judgment

Memory and acceptance findings should remain separate.

However, the systems may later connect through controlled seams:

- reviewed candidate findings may inform memory
- stable repeated findings may inform future surface packs
- memory may inform routing and recon behavior

This connection should be explicit and policy-owned, not implied.

## Failure Modes When Adopted Incompletely

### Session memory without extraction

Leads to bloated, local-only memory with poor reuse.

### Extraction without write-scope control

Leads to unsafe agent behavior and overreach.

### Consolidation without locking

Leads to corrupted or conflicting memory state.

### Shared memory without hygiene

Leads to unsafe or low-trust collaboration artifacts.

## SpecOrch Recommendation

Adopt the Memory Package as a Decision Core and Evolution linkage concern.

Epic 4 should consume memory through explicit routing and judgment seams, but
should not own memory lifecycle itself.

## Success Criteria

The package should be considered complete when:

- session memory updates on explicit cadence
- extraction is bounded and write-scoped
- consolidation reduces duplication without corrupting state
- shared memory has hygiene controls
- later routing and acceptance systems can consume memory through stable APIs

## Completion Snapshot

This package is now absorbed into `services.memory.lifecycle` and exposed through
`MemoryService`.

Implemented baseline:

- explicit session snapshot cadence decisions
- append-only session memory snapshots with dedupe
- consolidation locking with stale-lock reclamation
- shared-memory freshness gates
- shared-memory hygiene validation
- provenance-aware shared-memory sync events
