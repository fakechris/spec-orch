# Epic 6 Evolution Linkage Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete Epic 6 by making evolution consume normalized execution/decision/acceptance evidence, adding review-gated promotion governance, and recording supersession/rollback and promotion-origin observability.

**Architecture:** Epic 6 should not invent a parallel evolution state system. It should consume `runtime_core`, `decision_core`, `acceptance_core`, and memory learning views that already exist, then add one explicit governance seam for promotion lifecycle and provenance. The first half wires normalized evidence into `EvolutionTrigger` and selected evolvers; the second half adds promotion review gates, supersession/rollback, and journal observability.

**Tech Stack:** Python 3.13, dataclasses, JSON/JSONL carriers, existing `src/spec_orch/services/evolution/*`, memory service analytics, pytest, ruff.

---

### Task 1: Write Epic 6 plan and baseline audit

**Files:**
- Create: `docs/plans/2026-03-30-epic-6-evolution-linkage-plan.md`
- Reference: `docs/plans/2026-03-30-epic-4-7-program-plan.md`
- Reference: `docs/plans/2026-03-29-linear-ready-epic-mapping.md`

**Step 1: Save the plan**

Write this document as the canonical execution plan for Epic 6.

**Step 2: Record the starting gap**

Capture that current gaps are:
- no normalized evolution signals
- no reviewed-evidence promotion gate
- no explicit supersession / rollback state
- no promotion-origin observability

**Step 3: Commit**

```bash
git add docs/plans/2026-03-30-epic-6-evolution-linkage-plan.md
git commit -m "docs: add epic 6 evolution linkage plan"
```

### Task 2: Add failing tests for normalized evolution signals

**Files:**
- Create: `tests/unit/test_evolution_signal_bridge.py`
- Modify: `tests/unit/test_evolution_journal.py`
- Modify: `tests/unit/test_prompt_evolver.py`

**Step 1: Write failing tests**

Cover:
- `EvolutionTrigger` can derive normalized evolution signals from memory and context
- journal entries include evidence provenance/origin metadata
- prompt evolver can consume reviewed decision failures and recipes from context

**Step 2: Run tests to verify they fail**

Run:

```bash
uv run --python 3.13 python -m pytest tests/unit/test_evolution_signal_bridge.py tests/unit/test_evolution_journal.py tests/unit/test_prompt_evolver.py -q
```

Expected: FAIL because signal bridge / provenance fields do not exist yet.

### Task 3: Implement normalized evolution signal bridge

**Files:**
- Create: `src/spec_orch/services/evolution/signal_bridge.py`
- Modify: `src/spec_orch/services/evolution/evolution_trigger.py`
- Modify: `src/spec_orch/services/memory/service.py`
- Modify: `src/spec_orch/services/memory/analytics.py`

**Step 1: Add minimal bridge types/helpers**

Implement a bridge that can return:
- normalized execution evidence summaries
- reviewed decision evidence summaries
- reviewed acceptance evidence summaries
- promotion provenance summaries

**Step 2: Wire trigger context/journal**

Make `EvolutionTrigger`:
- build normalized signals from current memory/context
- pass them into evolver context
- emit origin/provenance metadata in evolution journal entries

**Step 3: Run focused tests**

Run:

```bash
uv run --python 3.13 python -m pytest tests/unit/test_evolution_signal_bridge.py tests/unit/test_evolution_journal.py -q
```

Expected: PASS

### Task 4: Add failing tests for promotion governance

**Files:**
- Create: `tests/unit/test_evolution_promotion_registry.py`
- Modify: `tests/unit/test_evolution_lifecycle.py`
- Modify: `tests/unit/test_muscle_evolvers.py`

**Step 1: Write failing tests**

Cover:
- high-impact assets require reviewed evidence before promotion
- promoted assets can be superseded
- rollback records a replacement relationship and deactivates the old asset
- promotion records preserve origin class (`execution`, `decision_review`, `acceptance_review`, `self_reflection`)

**Step 2: Run tests to verify they fail**

Run:

```bash
uv run --python 3.13 python -m pytest tests/unit/test_evolution_promotion_registry.py tests/unit/test_evolution_lifecycle.py tests/unit/test_muscle_evolvers.py -q
```

Expected: FAIL because promotion registry and gate do not exist yet.

### Task 5: Implement promotion gate and registry

**Files:**
- Create: `src/spec_orch/services/evolution/promotion_registry.py`
- Modify: `src/spec_orch/domain/models.py`
- Modify: `src/spec_orch/services/evolution/evolution_trigger.py`
- Modify: `src/spec_orch/services/evolution/prompt_evolver.py`
- Modify: `src/spec_orch/services/evolution/flow_policy_evolver.py`
- Modify: `src/spec_orch/services/evolution/gate_policy_evolver.py`
- Modify: `src/spec_orch/services/evolution/intent_evolver.py`

**Step 1: Add minimal governance types**

Introduce explicit promotion lifecycle records:
- promotion record
- supersession record
- rollback record

**Step 2: Gate high-impact promotion**

At minimum:
- `PROMPT_VARIANT`
- `POLICY`
- `HARNESS_RULE`

Require reviewed evidence provenance for these changes before promotion.

**Step 3: Persist promotion lifecycle**

Write file-backed records under `.spec_orch_evolution/` and ensure rollback/supersession are explicit rather than inferred.

**Step 4: Run focused tests**

Run:

```bash
uv run --python 3.13 python -m pytest tests/unit/test_evolution_promotion_registry.py tests/unit/test_evolution_lifecycle.py tests/unit/test_prompt_evolver.py tests/unit/test_muscle_evolvers.py -q
```

Expected: PASS

### Task 6: Add promotion observability and reviewed-decision prompt evolution

**Files:**
- Modify: `src/spec_orch/services/evolution/prompt_evolver.py`
- Modify: `src/spec_orch/services/memory/recorder.py`
- Modify: `src/spec_orch/services/memory/analytics.py`
- Modify: `src/spec_orch/services/context/context_assembler.py`
- Modify: `tests/unit/test_prompt_evolver.py`
- Modify: `tests/unit/test_memory_service.py`
- Modify: `tests/unit/test_context_assembler.py`

**Step 1: Feed reviewed decision evidence into prompt evolution**

Use context / bridge outputs to include:
- reviewed decision failures
- reviewed decision recipes
- reviewed acceptance findings when relevant

**Step 2: Record promotion origin observability**

Ensure promoted changes can later be queried by origin class and provenance.

**Step 3: Run focused tests**

Run:

```bash
uv run --python 3.13 python -m pytest tests/unit/test_prompt_evolver.py tests/unit/test_memory_service.py tests/unit/test_context_assembler.py -q
```

Expected: PASS

### Task 7: Final Epic 6 validation and checkpoint

**Files:**
- Update as needed from previous tasks only

**Step 1: Run final Epic 6 matrix**

```bash
uv run --python 3.13 python -m pytest tests/unit/test_evolution_signal_bridge.py tests/unit/test_evolution_promotion_registry.py tests/unit/test_evolution_journal.py tests/unit/test_evolution_lifecycle.py tests/unit/test_prompt_evolver.py tests/unit/test_muscle_evolvers.py tests/unit/test_memory_service.py tests/unit/test_context_assembler.py -q
uv run --python 3.13 ruff check src/spec_orch/services/evolution src/spec_orch/services/memory src/spec_orch/services/context tests/unit/test_evolution_signal_bridge.py tests/unit/test_evolution_promotion_registry.py tests/unit/test_evolution_journal.py tests/unit/test_evolution_lifecycle.py tests/unit/test_prompt_evolver.py tests/unit/test_muscle_evolvers.py
uv run --python 3.13 ruff format --check src/spec_orch/services/evolution src/spec_orch/services/memory src/spec_orch/services/context tests/unit/test_evolution_signal_bridge.py tests/unit/test_evolution_promotion_registry.py tests/unit/test_evolution_journal.py tests/unit/test_evolution_lifecycle.py tests/unit/test_prompt_evolver.py tests/unit/test_muscle_evolvers.py
```

**Step 2: Update program status**

Update:
- `docs/plans/2026-03-30-epic-4-7-program-plan.md`

**Step 3: Commit**

```bash
git add docs/plans/2026-03-30-epic-6-evolution-linkage-plan.md src/spec_orch/domain/models.py src/spec_orch/services/evolution src/spec_orch/services/memory src/spec_orch/services/context tests/unit
git commit -m "feat: land epic 6 evolution linkage baseline"
```
