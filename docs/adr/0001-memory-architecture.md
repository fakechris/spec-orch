# ADR-0001: Layered Memory Architecture for SpecOrch

**Status:** Accepted  
**Date:** 2026-03-21

## Context

SpecOrch has a pluggable memory abstraction. `MemoryProvider` defines five
synchronous methods (`store`, `recall`, `forget`, `list_keys`, `get`); the
default implementation is `FileSystemMemoryProvider`, which stores entries as
Markdown files with YAML front-matter and maintains a lightweight JSON index.

Current `recall` capability is limited: the filesystem provider's text
retrieval is essentially `layer/tag/filter + substring match`. Meanwhile,
`ContextAssembler` consumes memory primarily to recall failed issue-result
samples; procedural assets (scoper hints, policies) are still read directly
from files.

The goal is **not** to turn memory into a new single-point complex dependency,
but to enhance cross-session learning and similar-case recall without
sacrificing Git/Markdown auditability.

## Decision

### 1. Keep FileSystemMemoryProvider as source of truth

All memory entries remain persisted as Markdown + YAML front-matter files.
`_index.json` continues to serve as the lightweight index and audit trail.

### 2. Add Qdrant semantic index layer (does not replace the file layer)

- Use `qdrant-client` with `FastEmbed` for local embedding generation.
- Development defaults to local mode: `QdrantClient(path=...)` or `:memory:`.
- Initial model: `BAAI/bge-small-zh-v1.5`; switchable to
  `paraphrase-multilingual-*` for mixed-language scenarios.

### 3. QMD is not a MemoryProvider; it serves as an external document retriever for ContextAssembler

QMD searches docs, ADRs, postmortems, knowledge notebooks, spec archives —
static corpora only. It does not participate in runtime memory lifecycle.

### 4. Procedural memory stays in Git assets

ADRs, policies, skills, playbooks, and scoper hints are explicitly not
migrated into auto-extraction memory backends.

### 5. Mem0 is deferred, retained as a future experimental provider

Evaluate after validating memory consumption-point value (Phase 5).

## Memory Layer Boundaries

| Layer       | File Layer | Qdrant | Notes                                              |
|-------------|------------|--------|----------------------------------------------------|
| WORKING     | Yes        | No     | Per-run temporary context; short-lived              |
| EPISODIC    | Yes        | Yes    | issue-result, mission-event, gate-failure           |
| SEMANTIC    | Yes        | Yes    | run-summary, cross-run learnings                    |
| PROCEDURAL  | Yes (Git)  | No     | ADR, policies, skills, playbooks — Git assets only  |

## Consequences

### Positive

- Immediately improves `recall()` semantic capability beyond substring matching.
- Preserves file-backed memory's readability, auditability, and version control.
- Low deployment cost: local models start at ~90 MB.
- Does not change the `MemoryProvider` protocol; full backward compatibility.

### Negative

- Must maintain dual-layer storage: file truth source + vector index.
- Requires reindex / migration / embedding model versioning design.
- If memory consumption points are not expanded, benefit stays limited to
  "better failure sample recall."

### Explicitly Not Doing

- QMD is not mixed into the runtime memory provider.
- Mem0 is not the default core layer.
- Procedural assets are not migrated out of Git/Markdown.
