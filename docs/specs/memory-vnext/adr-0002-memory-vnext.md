# ADR-0002: Memory vNext — Scope, Strategy, and Non-Goals

**Status:** Proposed
**Date:** 2026-03-22
**Supersedes:** —
**Builds on:** [ADR-0001: Layered Memory Architecture](../../adr/0001-memory-architecture.md)

## Context

ADR-0001 established the layered memory architecture: filesystem as source of truth,
SQLite WAL for indexing, optional Qdrant for semantic recall, four memory layers
(WORKING / EPISODIC / SEMANTIC / PROCEDURAL). The Memory Architecture v2 Epic
(SON-219) completed the following on top of ADR-0001:

- SQLite WAL index replacing `_index.json` (SON-220)
- LLM-based episodic distillation in `compact()` (SON-222)
- PROCEDURAL layer activated in ContextAssembler (SON-223)
- Builder telemetry ingestion into episodic memory (SON-224)
- Human acceptance feedback storage + trend aggregation (SON-225)
- Enriched run summaries with builder adapter / verification / key learnings (SON-226)

The system now has a working write → store → recall → consume loop. However,
several structural gaps prevent memory from meaningfully improving delivery
outcomes:

1. **No relation semantics.** `MemoryEntry.metadata` (`types.py:46`) is an
   untyped `dict[str, Any]`. Entries for the same issue across runs have no
   explicit version chain; `compact()` does TTL-based cleanup, not
   update/extend/derive evolution.

2. **No project-level profile.** `get_trend_summary()` aggregates success rates
   but does not capture stable project facts (tech stack, common failures,
   architecture constraints). `LearningContext` (`context.py:48-59`) has seven
   fields but no `project_profile`.

3. **No hybrid retrieval.** `_text_matches()` (`fs_provider.py:125-131`) uses
   tokenized overlap matching. SQLite FTS5 is not used. Recall is either
   pure-semantic (Qdrant) or pure-lexical (token matching), never fused.

4. **Synchronous heavy work.** `_finalize_run` runs `_consolidate_run_memory`,
   `compact`, and `_maybe_trigger_evolution` sequentially in the main thread
   (`run_controller.py:1008-1196`). At scale, this blocks the pipeline.

5. **No recall provenance.** Items injected into LLM context carry truncated
   content but no metadata about why they were recalled, when they were created,
   or whether they represent the latest conclusion.

## Decision

Adopt a **"lightweight relation layer + async distillation + hybrid retrieval +
project profile"** strategy. Do not rewrite the underlying provider stack.

### Architecture delta

```
Current:
  FS (md) ←→ SQLite (index) ←→ Qdrant (optional semantic)
       ↕                            ↕
  MemoryService                VectorEnhancedProvider
       ↕
  ContextAssembler → LLM nodes

vNext additions (no replacement):
  FS (md) ←→ SQLite (index + FTS5 + relation columns) ←→ Qdrant
       ↕                            ↕
  MemoryService + ProjectProfile + Learning Views
       ↕                   ↕
  Hybrid Recall (RRF)    Async Derivation Queue
       ↕
  ContextAssembler (role-aware injection) → LLM nodes
```

### Concrete changes

| Layer | Change | Files affected |
|-------|--------|----------------|
| SQLite schema | Add `entity_scope`, `entity_id`, `relation_type` columns + indexes | `fs_provider.py` |
| SQLite schema | Add FTS5 virtual table `memory_fts` | `fs_provider.py` |
| Write path | Populate relation fields in `consolidate_run`, `record_builder_telemetry`, `record_acceptance`, `compact` | `service.py`, `run_controller.py` |
| Recall path | `recall_latest(entity_scope, entity_id)` API; lexical (FTS5) + semantic (Qdrant) → RRF merge | `service.py`, `fs_provider.py`, `vector_provider.py` |
| Context | `ProjectProfile` dataclass; four learning views; role-aware injection | `context.py`, `context_assembler.py` |
| Evolution | Async derivation queue; profile refresh; skill patch suggestion | `run_controller.py`, new `derivation.py` |
| Recall output | Provenance fields on injected learning items | `context_assembler.py` |

### Metadata field conventions

All new fields live in `MemoryEntry.metadata` **and** are mirrored to SQLite
columns for SQL-level filtering:

| Field | Type | Values | Purpose |
|-------|------|--------|---------|
| `entity_scope` | str | `issue`, `mission`, `repo`, `project` | Scope of the entity this entry relates to |
| `entity_id` | str | e.g. `SON-215`, `websocket-realtime` | Identifier within the scope |
| `relation_type` | str | `observed`, `update`, `extend`, `derive`, `summarize` | Relationship to prior entries |
| `supersedes_key` | str | Key of the entry this one replaces | Only in metadata dict |
| `confidence` | str | `low`, `medium`, `high` | Only in metadata dict |
| `source_run_id` | str | Run ID | Only in metadata dict |
| `source_artifact` | str | e.g. `gate-verdict`, `builder-events` | Only in metadata dict |

## Design Goals

1. **More accurate context for each node.** Reduce irrelevant memories reaching
   builder/planner/reviewer by role-aware injection and latest-entry preference.
2. **More stable experience reuse.** Especially failure patterns, verification
   strategies, and fix recipes — surfaced as structured views, not raw recall.
3. **Clear separation of latest vs. historical.** Prevent stale conclusions from
   polluting new runs via `relation_type` and `supersedes_key`.
4. **Async distillation.** Move heavy learning (profile refresh, issue-level
   summarization, skill patch suggestions) off the main pipeline.

All four goals serve the `spec → execute → verify → gate → evolve` flywheel.

## Non-Goals (written as hard constraints)

### NG-1: No general-purpose Memory SaaS / Memory API

spec-orch is a delivery control plane, not a memory product. We will not build
APIs, dashboards, or SDK wrappers aimed at external memory consumers.

### NG-2: No heavy knowledge graph first

No Neo4j, no entity-relation graph DB, no global contradiction reasoning engine.
The relation semantics we add are lightweight metadata fields, not a graph model.

### NG-3: No multi-platform conversation system first

Slack / Feishu / Telegram / webhook session unification is not a prerequisite
for memory evolution. Platform ingress is an outer-layer concern.

### NG-4: No "smarter memory" replacing "stronger gate / evidence"

Memory must serve the control plane, not replace it. If a process must be
reliably enforced, it belongs in gate/policy/harness — not in a memory recall
path that might miss.

These boundaries extend the project's existing "don't do" list (no multi-agent
bus, no graph-first workflow builder, no AI IDE).

## Phased Rollout

| Phase | Scope | Depends on |
|-------|-------|------------|
| 1 | Minimal relation layer: SQLite columns + write-side population + `recall_latest` + ContextAssembler latest-first | — |
| 2 | ProjectProfile + four learning views + role-aware injection | Phase 1 |
| 3 | Hybrid retrieval: FTS5 + RRF + exact token boost + provenance | Phase 1 |
| 4 | Async derivation queue: profile refresh, issue summarize, skill patch, stale soft-delete | Phase 2, Phase 3 |

## Success Metrics

1. Builder first-pass success rate improvement
2. Verification first-pass success rate improvement
3. Reduction in repeated gate failure reasons
4. Effective learning context ratio in injected tokens
5. Human relevance score of similar failure recall
6. External project E2E success rate (tied to Milestone 1 in roadmap)

## Reference: Borrowing Boundaries

| Project | Borrow | Do not borrow |
|---------|--------|---------------|
| **Hermes** | Rhythmic review, background review fork, skill patch/edit, subtask isolation | Personal agent shell, prompt-text-as-memory |
| **Supermemory** | Update/extend/derive, static/dynamic profile, auto-forget | Memory product narrative, benchmark-driven roadmap |
| **Honcho** | Entity-centered memory, async derivation, summary/detail split | Heavy reasoning infra first, complex conclusion types first |
| **CC-Connect** | Unified session key pattern (future ingress) | Platform ingress as memory evolution mainline |
