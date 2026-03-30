# System Primitives Implementation Track

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn the agreed system primitives and high-level organization into a concrete implementation track with visible package boundaries, dependency rules, and an incremental rollout path that can start without a big-bang rewrite.

**Architecture:** spec-orch should evolve from a controller-centric services tree into a core-and-surfaces organization. The first extraction target is not owner unification; it is a visible shared seam for execution semantics, supervision/decision records, and normalized carriers. Existing owners (`RunController`, `RoundOrchestrator`, `MissionLifecycleManager`) keep control of lifecycle timing while delegating shared data shaping to new core packages.

**Tech Stack:** Python 3.13, dataclasses, existing `src/spec_orch` package structure, JSON/JSONL/Markdown file-backed state, pytest unit tests, incremental refactor with compatibility shims.

---

## 1. What This Plan Is Solving

The current repo has:

- meaningful domain objects
- two real runtime spines
- memory and evidence systems
- partial approval / supervision surfaces

But it still lacks:

- a visible package boundary for shared execution semantics
- a visible package boundary for decision review
- a clear dependency direction between cores and surfaces
- a stable place to put newly extracted primitives

If implementation starts without fixing that, new abstractions will be scattered into:

- `services/`
- `dashboard/`
- `domain/models.py`
- ad hoc JSON carriers

This plan exists to stop that from happening.

## 2. Non-Goals

This implementation track does **not**:

- merge `Mission` and `Issue`
- merge `RunController` and `RoundOrchestrator`
- rewrite the whole repo into seven planes in one shot
- move every existing service out of `services/` immediately
- replace existing carriers in one commit

## 3. Target Top-Level Shape

The repo should evolve toward this shape:

```text
src/spec_orch/
  domain/                  # business subjects and stable value objects
  contract_core/           # contract parsing, snapshots, question/decision recording
  runtime_core/            # execution semantics, continuity, normalized readers/writers
  decision_core/           # supervision, decision records, intervention, review loop
  memory_core/             # memory providers, derivation, learning views
  evolution_core/          # evolvers, trigger policy, promotion/review gates
  surfaces/                # CLI/daemon/dashboard-facing bridges (may begin as aliases)
  services/                # compatibility layer during migration
```

This is the **direction**, not the first commit.

## 4. What Stays in `domain/`

`domain/` should remain the home of business subjects and stable cross-core value objects.

Keep in `domain/`:

- `Mission`
- `Issue`
- `ExecutionPlan`
- `Wave`
- `WorkPacket`
- `RunResult`
- current stable contract/result dataclasses that are not runtime-owner specific

Do **not** move owner logic into `domain/`.

Do **not** let `domain/models.py` keep absorbing every new cross-cutting abstraction forever.

Expected medium-term split:

```text
src/spec_orch/domain/
  subjects.py
  planning.py
  contracts.py
  outcomes.py
  interventions.py
  models.py        # temporary compatibility re-exports during migration
```

## 5. First-Class Cores and Their Responsibilities

### 5.1 `contract_core/`

Owns:

- spec import / parsing
- spec snapshot / freeze
- question / answer / decision persistence
- acceptance contract normalization
- constraint normalization

Initial source files to absorb from current tree:

- `src/spec_orch/services/spec_snapshot_service.py`
- `src/spec_orch/cli/spec_commands.py` decision recording paths
- `src/spec_orch/domain/task_contract.py`
- `src/spec_orch/spec_import/`

Do not put runtime execution logic here.

### 5.2 `runtime_core/`

Owns:

- `ExecutionUnit`
- `ExecutionAttempt`
- `ExecutionOutcome`
- `ArtifactRef`
- continuity semantics
- normalized read/write shaping

Initial source files to create or absorb:

- new: `src/spec_orch/runtime_core/models.py`
- new: `src/spec_orch/runtime_core/paths.py`
- new: `src/spec_orch/runtime_core/readers.py`
- new: `src/spec_orch/runtime_core/writers.py`
- new: `src/spec_orch/runtime_core/adapters.py`
- temporary shims:
  - `src/spec_orch/services/execution_semantics_reader.py`
  - `src/spec_orch/services/execution_semantics_writer.py`

This is the first extraction target.

### 5.3 `decision_core/`

Owns:

- `SupervisionCycle`
- `DecisionPoint`
- `DecisionRecord`
- `DecisionReview`
- `Intervention`
- approval / escalation semantics

Initial source files to absorb from current tree:

- `src/spec_orch/services/litellm_supervisor_adapter.py`
- `src/spec_orch/services/round_orchestrator.py` supervision shaping parts only
- `src/spec_orch/dashboard/approvals.py`
- `src/spec_orch/dashboard/missions.py` approval-state derivation helpers

This is the second extraction target after `runtime_core/`.

### 5.4 `memory_core/`

Owns:

- providers and indexes
- memory recording
- derivation queue
- analytics / learning views
- role-aware recall shaping inputs

Initial source files to re-home under alias or rename later:

- current `src/spec_orch/services/memory/*`
- current `src/spec_orch/services/context/*` stays separate at first, then depends on `memory_core`

Do not overload `memory_core` with supervision semantics.

### 5.5 `evolution_core/`

Owns:

- evolver registry
- trigger policy
- promotion / supersession review
- policy-asset evolution

Initial source files to re-home later:

- current `src/spec_orch/services/evolution/*`
- `src/spec_orch/services/evolution_policy.py`

Do not start with this core. It depends on earlier seams.

### 5.6 `surfaces/`

Owns:

- user/operator/system entry points
- no canonical business truth

Initial members:

- CLI commands
- daemon adapters
- dashboard adapters
- external connectors

This can begin as a conceptual grouping before any directory rename.

## 6. Dependency Rules

These dependency rules should be treated as hard constraints.

### Rule 1: `domain` is below all cores

Allowed:

- all cores depend on `domain`

Not allowed:

- `domain` importing `runtime_core`, `decision_core`, `memory_core`, or `surfaces`

### Rule 2: `runtime_core` does not depend on `dashboard` or CLI

Allowed:

- `runtime_core` depends on `domain` and basic IO helpers

Not allowed:

- `runtime_core` importing from `dashboard/`, CLI modules, or external surface logic

### Rule 3: `decision_core` may depend on `runtime_core`, not the reverse

Reason:

- supervision inspects and judges execution attempts/outcomes
- execution should not need knowledge of approval UIs or review queues

### Rule 4: `memory_core` can consume artifacts from runtime/decision, but should not own their schemas

Reason:

- memory stores and derives learnings
- it should not define what an `ExecutionOutcome` or `DecisionRecord` is

### Rule 5: `surfaces` consume cores; cores do not consume surfaces

Reason:

- dashboard and daemon can present, replay, and trigger
- they should not define core truth

## 7. Shared Primitives to Introduce in Code Order

### Tranche A: Execution primitives

Introduce first:

- `ExecutionUnit`
- `ExecutionAttempt`
- `ExecutionOutcome`
- `ArtifactRef`
- `Continuity`

Reason:

- already agreed
- lowest conceptual risk
- highest immediate value for issue/mission convergence

### Tranche B: Supervision primitives

Introduce second:

- `SupervisionCycle`
- `DecisionPoint`
- `DecisionRecord`
- `Intervention`

Reason:

- current repo has partial pieces (`RoundDecision`, approval queue, ask_human)
- this tranche turns them into a system instead of scattered artifacts

### Tranche C: Review and learning linkage

Introduce third:

- `DecisionReview`
- `LearningView`
- `SuccessRecipe`
- `FailurePattern`
- promotion / supersession metadata

Reason:

- this is where memory and evolution start consuming decision artifacts instead of only run summaries

### Tranche D: Contract normalization

Introduce fourth:

- `ContractSubject`
- `ContractSnapshot`
- `AcceptanceContract`
- `ConstraintSet`

Reason:

- contract normalization matters, but it is less urgent than the runtime and supervision seams that are currently missing

## 8. Rollout Tranches

### Tranche 0: Prepare the tree

Goal:

- create stable homes for extracted code before moving behavior

Deliverables:

- `src/spec_orch/runtime_core/`
- `src/spec_orch/decision_core/`
- import-only package skeletons
- architecture note pointing to these packages as canonical homes

No behavior change yet.

### Tranche 1: Runtime core extraction

Goal:

- make shared execution semantics real in code

Deliverables:

- `runtime_core.models`
- `runtime_core.paths`
- `runtime_core.readers`
- `runtime_core.writers`
- compatibility shims in `services/`
- owners delegate normalized shaping to runtime core

This tranche corresponds to the existing shared-semantics and runtime-extraction plans.

### Tranche 2: Decision core extraction

Goal:

- make supervision and approval semantics real in code

Deliverables:

- `decision_core.models`
- `decision_core.records`
- `decision_core.review_queue`
- `decision_core.interventions`
- `RoundDecision` integration without collapsing it into `ExecutionAttempt`

Key rule:

- `DecisionRecord` is new canonical write target for LLM-controlled branch points

### Tranche 3: Memory linkage

Goal:

- connect decision records and execution outcomes into a unified learning loop

Deliverables:

- memory recorder support for decision records
- learning views over decision quality
- latest-first recall of reviewed decisions
- context injection for relevant prior decision cases

### Tranche 4: Evolution linkage

Goal:

- make reviewed execution and decision learnings promotable into policy assets

Deliverables:

- evolvers can consume decision-review slices
- promotion policy can distinguish:
  - execution evidence
  - human-reviewed decision evidence
  - self-reflection-only evidence

## 9. First Concrete Package Layout

The first realistic on-disk layout should be:

```text
src/spec_orch/
  domain/
    models.py
    task_contract.py
    context.py

  runtime_core/
    __init__.py
    models.py
    paths.py
    readers.py
    writers.py
    adapters.py

  decision_core/
    __init__.py
    models.py
    records.py
    interventions.py
    review_queue.py

  services/
    execution_semantics_reader.py   # compatibility shim
    execution_semantics_writer.py   # compatibility shim
    round_orchestrator.py           # owner stays here for now
    run_controller.py               # owner stays here for now
    mission_execution_service.py    # owner stays here for now
```

This keeps owner migration out of the first implementation tranche.

## 10. What to Create First

### Task 1: Add package skeletons

**Files:**
- Create: `src/spec_orch/runtime_core/__init__.py`
- Create: `src/spec_orch/runtime_core/models.py`
- Create: `src/spec_orch/runtime_core/paths.py`
- Create: `src/spec_orch/runtime_core/readers.py`
- Create: `src/spec_orch/runtime_core/writers.py`
- Create: `src/spec_orch/runtime_core/adapters.py`
- Create: `src/spec_orch/decision_core/__init__.py`
- Create: `src/spec_orch/decision_core/models.py`
- Create: `src/spec_orch/decision_core/records.py`
- Create: `src/spec_orch/decision_core/interventions.py`
- Create: `src/spec_orch/decision_core/review_queue.py`
- Test: `tests/unit/test_runtime_core_imports.py`
- Test: `tests/unit/test_decision_core_imports.py`

**Step 1: Write failing import tests**

Run:

```bash
pytest tests/unit/test_runtime_core_imports.py tests/unit/test_decision_core_imports.py -v
```

Expected: FAIL with missing modules.

**Step 2: Create empty packages and simple exports**

Expose placeholder dataclasses or type aliases only. Do not move live behavior yet.

**Step 3: Run tests**

```bash
pytest tests/unit/test_runtime_core_imports.py tests/unit/test_decision_core_imports.py -v
```

**Step 4: Commit**

```bash
git add src/spec_orch/runtime_core src/spec_orch/decision_core tests/unit/test_runtime_core_imports.py tests/unit/test_decision_core_imports.py
git commit -m "feat: add runtime and decision core package skeletons"
```

### Task 2: Land runtime-core read/write seam

Use the previously written plans as execution detail:

- [`2026-03-29-shared-execution-semantics-rollout.md`](./2026-03-29-shared-execution-semantics-rollout.md)
- [`2026-03-29-runtime-extraction-phase-2.md`](./2026-03-29-runtime-extraction-phase-2.md)

Additional constraint:

- all new execution semantic code lands in `runtime_core`, not `services/`

### Task 3: Define `DecisionPoint` inventory and `DecisionRecord` schema

**Files:**
- Create: `src/spec_orch/decision_core/models.py`
- Create: `tests/unit/test_decision_core_models.py`
- Modify: `docs/architecture/evolution-trigger-architecture.md`
- Modify: `docs/architecture/runtime-glossary.md`

**Step 1: Write failing tests for schema shape**

Cover:

- point id
- owner kind
- policy kind (`rule` / `llm` / `human_required`)
- context ref
- chosen action
- confidence
- escalation flag

**Step 2: Define inventory categories**

Minimum categories:

- fixed-rule decision points
- LLM-controlled decision points
- human-required decision points

**Step 3: Run tests**

```bash
pytest tests/unit/test_decision_core_models.py -v
```

**Step 4: Commit**

```bash
git add src/spec_orch/decision_core/models.py tests/unit/test_decision_core_models.py docs/architecture/evolution-trigger-architecture.md docs/architecture/runtime-glossary.md
git commit -m "feat: add decision point and decision record primitives"
```

### Task 4: Integrate mission round writes with decision-core

**Files:**
- Modify: `src/spec_orch/services/litellm_supervisor_adapter.py`
- Modify: `src/spec_orch/services/round_orchestrator.py`
- Modify: `src/spec_orch/dashboard/approvals.py`
- Modify: `src/spec_orch/decision_core/records.py`
- Test: `tests/unit/test_round_orchestrator.py`
- Test: `tests/unit/test_decision_core_records.py`

**Step 1: Write failing tests**

Cover:

- round review creates `DecisionRecord`
- `ask_human` creates `Intervention`
- approval action appends review/response metadata without mutating the execution schema

**Step 2: Implement minimal writer path**

Mission path is the first live adopter of decision-core because it already has real supervision semantics.

**Step 3: Run tests**

```bash
pytest tests/unit/test_round_orchestrator.py tests/unit/test_decision_core_records.py -v
```

**Step 4: Commit**

```bash
git add src/spec_orch/services/litellm_supervisor_adapter.py src/spec_orch/services/round_orchestrator.py src/spec_orch/dashboard/approvals.py src/spec_orch/decision_core/records.py tests/unit/test_round_orchestrator.py tests/unit/test_decision_core_records.py
git commit -m "feat: record mission supervision decisions through decision core"
```

## 11. What Not To Touch In The First Week

Do not touch first:

- `services/evolution/*`
- `services/memory/*` provider internals
- dashboard broad UI rewrites
- `Mission` / `Issue` dataclass unification
- renaming the whole `services/` tree

Reason:

- these are downstream of the first seams
- changing them early makes the rollout noisy and hard to validate

## 12. Success Criteria For This Track

This implementation track is on the right path when:

1. new shared primitives stop landing in `services/` by default
2. `runtime_core` becomes the only normalized execution read/write seam
3. mission supervision writes first-class `DecisionRecord`s
4. dashboard and memory can consume decision artifacts without parsing owner-local ad hoc JSON
5. owners remain separate, but the mental model of the codebase becomes clearer instead of more ambiguous

## 13. Handoff

This plan should now be treated as the top-level implementation track.

Lower-level execution detail already exists in:

- [`2026-03-29-shared-execution-semantics-rollout.md`](./2026-03-29-shared-execution-semantics-rollout.md)
- [`2026-03-29-runtime-extraction-phase-2.md`](./2026-03-29-runtime-extraction-phase-2.md)

Those two plans define the execution tranche for `runtime_core`.

This document adds the missing top-level structure:

- where new code should live
- which primitives come first
- which core comes after runtime extraction
- how to avoid falling back into “same semantics, scattered owners”
