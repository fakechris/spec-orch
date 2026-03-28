# SpecOrch vs yoyo-evolve: Harness Engineering Roadmap

## Goal

Turn the `yoyo-evolve` comparison into an actionable SpecOrch roadmap, with a one-to-one mapping between roadmap phases and Linear epics.

This document does **not** try to turn SpecOrch into another `yoyo`. The goal is narrower:

- keep SpecOrch's operator-control-plane strengths
- borrow the most valuable harness-engineering patterns from `yoyo`
- avoid importing the parts of `yoyo` that would dilute SpecOrch's product thesis

## Source Material

Primary `yoyo-evolve` sources reviewed:

- `README.md`
- `IDENTITY.md`
- `PERSONALITY.md`
- `JOURNAL.md`
- `CLAUDE.md`
- `CLAUDE_CODE_GAP.md`
- `memory/active_learnings.md`
- `memory/active_social_learnings.md`
- `scripts/evolve.sh`
- `scripts/social.sh`
- `scripts/yoyo_context.sh`
- `.github/workflows/evolve.yml`
- `.github/workflows/synthesize.yml`
- `docs/src/architecture.md`
- `docs/src/features/context.md`
- `docs/src/configuration/system-prompts.md`

Current local SpecOrch references:

- [operator-console.md](../guides/operator-console.md)
- [2026-03-27-acceptance-evaluator-playwright-linear.md](2026-03-27-acceptance-evaluator-playwright-linear.md)
- [2026-03-28-acceptance-prompt-architecture.md](2026-03-28-acceptance-prompt-architecture.md)
- [roadmap.md](roadmap.md)

## Executive Summary

`yoyo-evolve` is strongest where SpecOrch is currently thinnest:

- explicit selfhood and identity continuity
- active memory synthesis instead of archive-only memory
- journaling the agent's growth as a first-class engineering artifact
- social/discussion learnings as part of the system, not as afterthoughts

SpecOrch is strongest where `yoyo` is currently lighter:

- operator-facing control plane
- mission / round / packet observability
- approvals, interventions, acceptance, and budget control
- structured evidence artifacts and governance

So the right move is **not** to clone `yoyo`. The right move is to add:

1. stronger adversarial / exploratory acceptance
2. explicit constitutions and evaluator stance
3. active synthesis for self, delivery, and feedback memory
4. durable feedback learning loops

## Comparison: What Matters

| Dimension | `yoyo-evolve` | SpecOrch today | Borrow / avoid |
|-----------|---------------|----------------|----------------|
| Core object | Agent selfhood | Mission / round / packet / operator | Borrow selfhood mechanics, not product center |
| Stability vs growth | Narrow self-edit aperture + strict rituals | Strong control plane, weaker self-reflection loop | Borrow ritualized growth with hard guardrails |
| Memory | Archive + active synthesis + social learnings | Strong recall infra, weaker active self-memory | Borrow active synthesis and role-specific slices |
| Personality | Explicit `IDENTITY` + `PERSONALITY` + `JOURNAL` layering | Mostly role prompts and config | Borrow layering, avoid turning product into persona theater |
| Social vision | Public growth + discussion ingestion + fork-family narrative | Linear/operator/product workflow centric | Borrow structured feedback ingestion, avoid full social-product pivot |
| Observability | Documentary evolution trail | Strong delivery observability | Keep our control plane; add evolution observability |

## What SpecOrch Should Borrow

### 1. Constitution Layers

SpecOrch should have explicit constitutions for:

- supervisor
- acceptance evaluator
- future evolvers

These should define non-negotiable behavior:

- evidence before conclusions
- honesty about uncertainty
- when to intervene vs when to escalate
- what kinds of automatic changes are allowed

### 2. Active Memory Synthesis

SpecOrch already has stronger memory infrastructure than most agent projects, but it still leans too heavily on stored artifacts and retrieval.

What to add:

- active synthesized memory slices
- separate synthesized context for:
  - delivery learnings
  - evaluator learnings
  - operator/user feedback learnings

### 3. Evolution Journal

`yoyo`'s strongest engineering pattern is that its growth is inspectable.

SpecOrch should add a durable evolution journal for:

- prompt changes
- policy changes
- acceptance threshold changes
- strategy changes
- why each change happened

### 4. Feedback Learning

SpecOrch currently captures a lot of structured evidence, but operator pain often still dies in chats, review comments, or ephemeral notes.

We should capture:

- operator confusion
- UX pain
- false-positive acceptance findings
- false-negative misses
- post-dogfood qualitative notes

and feed them into a persistent learning loop.

## What SpecOrch Should Not Borrow

### 1. Do not shift product center away from operator control

SpecOrch is a control plane, not a personality-first agent product.

### 2. Do not let social/fork narrative replace governance

We may eventually ingest discussion signals, but we should not turn the system into a community-performance artifact before core delivery loops are stronger.

### 3. Do not widen self-edit freedom without hard boundaries

`yoyo` works because its wildness is bounded. If SpecOrch adds more self-evolution, it must come with narrower edit apertures, explicit constitutions, and evaluators that are independent from builders.

## Roadmap

## Phase 0: Baseline Already In Place

These are already real, and should be treated as foundations rather than future promises.

| Track | Linear | Status | Notes |
|------|--------|--------|-------|
| Original self-evolution baseline | `SON-74` + `SON-75..82` | complete | Evidence consumption, harness synthesis, prompt/policy evolution |
| Operator console phase 2 | `SON-234` + `SON-235..241` | backlog/in progress | Transcript, approvals, Visual QA, budgets, dogfood |
| Acceptance evaluator baseline | shipped via PRs, now normalized under next-phase epic | complete baseline | Browser evidence + independent evaluator + Linear filing + dashboard surface |

## Phase 1: Acceptance Harness Phase 2

**Epic:** `SON-242`  
**Why first:** this is the shortest path from today's acceptance evaluator to the adversarial / exploratory harness you asked for.

### Scope

- make acceptance route plans explicit
- support richer interaction-aware browser flows
- define adversarial evaluator policy
- calibrate acceptance with repeatable dogfood fixtures

### Child issues

| Linear | Task |
|--------|------|
| `SON-245` | Acceptance route planning and coverage budgets |
| `SON-246` | Interaction-aware browser operator flows |
| `SON-247` | Adversarial evaluator rubric and filing policy |
| `SON-248` | Acceptance calibration fixtures and dogfood regression suite |

### Exit criteria

- acceptance coverage is explicit
- evaluator can test more than static route snapshots
- issue filing becomes more trustworthy under exploratory mode

## Phase 2: Harness Selfhood and Memory Synthesis

**Epic:** `SON-243`

### Scope

- separate constitution from personality from memory
- add synthesized active memory slices
- inject different memory slices into different roles
- make harness change history inspectable

### Child issues

| Linear | Task |
|--------|------|
| `SON-249` | Supervisor, evaluator, and evolver constitutions |
| `SON-250` | Active memory synthesis pipeline for self, delivery, and feedback learnings |
| `SON-251` | Role-scoped memory injection in ContextAssembler |
| `SON-252` | Evolution journal and strategy-delta logging |

### Exit criteria

- evaluator and supervisor have explicit operating constitutions
- active memory synthesis exists, not just raw archive + retrieval
- the harness can explain how it changed and why

## Phase 3: Operator Feedback and Social Learning

**Epic:** `SON-244`

### Scope

- capture operator feedback inside the product
- synthesize it into durable learning context
- use human feedback to tune acceptance policy
- explore bounded discussion/social ingestion without turning SpecOrch into a social product

### Child issues

| Linear | Task |
|--------|------|
| `SON-253` | Dashboard operator feedback capture |
| `SON-254` | Feedback synthesis into active learnings |
| `SON-255` | Acceptance and human feedback policy loop |
| `SON-256` | External discussion ingestion design spike |

### Exit criteria

- operator pain points become structured, queryable learning assets
- human feedback influences evaluator behavior without ad hoc prompt edits
- any future discussion/social ingestion has explicit scope and guardrails

## Epic Coverage Audit

### Self-Evolution Epic Coverage

**Covered and complete**

- `SON-74` is a real epic
- `SON-75..82` are complete children
- this covers the original self-evolution baseline

### Acceptance / Adversarial Acceptance Coverage

**Baseline acceptance is shipped, but the dedicated roadmap epic was missing until now**

Before this update:

- acceptance evaluator existed in code
- prompt architecture existed in docs
- browser evidence existed in orchestrator
- but there was no dedicated Linear epic for adversarial / exploratory acceptance

After this update:

- `SON-242` now exists as the explicit acceptance-harness phase-2 epic
- `SON-245..248` define the first concrete work slices

### Operator Console / Dogfood Coverage

**Now normalized**

- `SON-234` is now labeled as a real epic
- `SON-235..241` are attached as children

This matters because the roadmap should not point at “floating backlog tasks” with no parent epic.

## Recommended Execution Order

1. `SON-245`
2. `SON-246`
3. `SON-247`
4. `SON-248`
5. `SON-249`
6. `SON-250`
7. `SON-251`
8. `SON-252`
9. `SON-253`
10. `SON-254`
11. `SON-255`
12. `SON-256`

This keeps the order pragmatic:

- first improve acceptance quality
- then strengthen constitutions and memory synthesis
- then close the feedback loop

## Decision

SpecOrch should continue to be a delivery control plane first.

The right lesson from `yoyo-evolve` is not “become a public agent personality.”  
The right lesson is:

- engineer growth explicitly
- synthesize learnings into active context
- separate constitution from personality from memory
- make feedback and evolution inspectable

That is the roadmap reflected in `SON-242`, `SON-243`, and `SON-244`.

## Acceptance Taxonomy Realignment

After the first real dashboard dogfood passes, one product-language problem became obvious:

- `acceptance` was still being used to mean three different things
- strict verification, workflow operability, and exploratory critique were partly mixed together

That is now formalized in:

- [Acceptance Taxonomy and Epic Structure](2026-03-28-acceptance-taxonomy-and-epics.md)

The updated interpretation is:

1. `SON-242` is the **Verification Acceptance** epic
2. a **new Workflow Acceptance** epic should be created for end-to-end operator-task flows
3. a **new Exploratory Acceptance** epic should be created for bounded user-perspective dogfood
4. `SON-244` should be narrowed to **Human Acceptance and Feedback Loop**, not treated as the immediate next implementation step

This changes the recommended order:

1. finish Verification Acceptance
2. make Workflow Acceptance real
3. make Exploratory Acceptance real
4. only then open the human feedback loop in earnest

This ordering better matches the actual maturity path:

- first make findings stable
- then make workflows operable
- then broaden perspective
- then let human feedback reshape policy
