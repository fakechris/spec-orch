# Post-Workbench Program Execution Order

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn the already-landed intake/substrate/workbench/showcase system into a governed, trustworthy operator runtime by prioritizing runtime admission enforcement, deterministic structural judgment, and stricter learning promotion before more surface expansion.

**Architecture:** Treat the current workbench stack as implemented baseline, not as a design hypothesis. Reuse the standing formal acceptance plus archive-bundle discipline as the closeout gate for every tranche. The next wave should harden three existing seams in order: execution governance, judgment calibration, and learning promotion discipline. Only after those are stable should the narrative/showcase layer expand further.

**Tech Stack:** Python 3.13, FastAPI, existing dashboard HTML/JS shell, pytest, mypy, ruff, canonical acceptance harness, acceptance-history archive

## Current State To Assume

The following are already in code and should be treated as baseline:

- conversational intake through canonical issue/workspace handoff
- shared operator semantics
- runtime and execution substrate read models
- execution, judgment, and learning workbenches
- surface cleanup / workbench cutover core path
- showcase narrative layer tranche 1
- rolling `docs/acceptance-history/` release archive

This means the next phase is **not** another architecture-definition round.
It is a **post-workbench hardening program**.

## Program Order

1. Keep acceptance freeze as the standing tranche gate
2. Implement `SON-412` tranche 1 runtime admission enforcement
3. Add a deterministic structural judgment channel inside the judgment stack
4. Tighten learning promotion discipline and archive lineage joins
5. Only then continue `SON-363` showcase expansion (`SON-364..369`)

## Standing Closeout Rule For Every Tranche

Every tranche in this document closes the same way:

1. run canonical acceptance
2. classify `harness_bug` / `n2n_bug` / `ux_gap`
3. fix `harness_bug` first if present
4. rerun
5. write a new release acceptance bundle
6. refresh `docs/acceptance-history/index.json`
7. record `source_run` compare notes against the previous relevant tranche bundle

### Task 1: Keep acceptance freeze as the standing gate

**Files:**
- Reference: `docs/agent-guides/run-pipeline.md`
- Reference: `docs/plans/2026-04-02-release-acceptance-history-and-archive-program.md`
- Reference: `docs/plans/2026-03-30-stability-acceptance-status.md`
- Modify per tranche: `docs/acceptance-history/index.json`
- Modify per tranche: `.spec_orch/acceptance/stability_acceptance_status.json`

**Step 1: Do not open a separate acceptance-improvement epic**

Treat acceptance as the release discipline for all later work, not as a competing feature track.

**Step 2: Reuse the canonical closeout command set**

Run:

```bash
./tests/e2e/issue_start_smoke.sh --full
./tests/e2e/dashboard_ui_acceptance.sh --full
./tests/e2e/mission_start_acceptance.sh --full
./tests/e2e/exploratory_acceptance_smoke.sh --full
./tests/e2e/update_stability_acceptance_status.sh
```

Expected: a fresh consolidated status plus source runs that can be archived into a new release bundle.

**Step 3: Keep archive hygiene in scope**

When acceptance artifacts are written, they must remain portable, sanitized, and suitable for dashboard/showcase consumption.

### Task 2: Implement `SON-412` tranche 1 runtime admission enforcement

**Files:**
- Create: `src/spec_orch/services/admission_governor.py`
- Modify: `src/spec_orch/services/execution_substrate.py`
- Modify: `src/spec_orch/services/daemon.py`
- Modify: `src/spec_orch/dashboard/control.py`
- Modify: `src/spec_orch/dashboard/app.py`
- Modify: `src/spec_orch/services/execution_workbench.py`
- Test: `tests/unit/test_execution_substrate.py`
- Test: `tests/unit/test_dashboard_api.py`
- Add: `tests/unit/test_admission_governor.py`

**Step 1: Write the failing tests**

Add tests that require:

- explicit global budget carriers for daemon, mission, worker, and verifier scopes
- a real governor decision function that returns `admit`, `defer`, `reject`, or `degrade`
- queue entries backed by governor output rather than read-side inference only
- dashboard/control payloads that expose real refusal or degrade reasons
- execution workbench summaries that surface current pressure source and granted budgets

**Step 2: Run tests to verify they fail**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_admission_governor.py tests/unit/test_execution_substrate.py tests/unit/test_dashboard_api.py -q
```

Expected: `FAIL` because runtime admission is still inferred, not enforced.

**Step 3: Write the minimal implementation**

Implement:

- `AdmissionGovernor` as the canonical enforcement seam
- explicit budget snapshots and decision records
- daemon integration that evaluates mission admission before execution starts
- first refusal / defer / degrade reasons that survive into control and execution workbench views

Keep the actual mission execution model conservative:

- no new parallel wave model
- no speculative provider expansion
- serial mission-internal execution stays intact

**Step 4: Run focused verification**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_admission_governor.py tests/unit/test_execution_substrate.py tests/unit/test_dashboard_api.py -q
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 ruff check src/spec_orch/services/admission_governor.py src/spec_orch/services/execution_substrate.py src/spec_orch/services/daemon.py src/spec_orch/services/execution_workbench.py src/spec_orch/dashboard/control.py src/spec_orch/dashboard/app.py tests/unit/test_admission_governor.py tests/unit/test_execution_substrate.py tests/unit/test_dashboard_api.py
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 mypy src/spec_orch/services/admission_governor.py src/spec_orch/services/execution_substrate.py src/spec_orch/services/daemon.py
```

Expected: `PASS`

**Step 5: Close the tranche with formal acceptance and archive**

Run the standing closeout commands and archive the new tranche bundle under `docs/acceptance-history/releases/`.

### Task 3: Add a deterministic structural judgment channel

**Files:**
- Create: `src/spec_orch/services/structural_judgment.py`
- Modify: `src/spec_orch/services/judgment_substrate.py`
- Modify: `src/spec_orch/services/judgment_workbench.py`
- Modify: `src/spec_orch/dashboard/app.py`
- Modify: `src/spec_orch/dashboard/missions.py`
- Test: `tests/unit/test_judgment_substrate.py`
- Test: `tests/unit/test_dashboard_api.py`
- Add: `tests/unit/test_structural_judgment.py`

**Step 1: Write the failing tests**

Add tests that require a structural judgment channel with:

- `quality_signal`
- `bottleneck`
- `rule_violations`
- `baseline_diff`
- `current_state`

Require that:

- mission-level judgment payloads include this structural channel beside semantic acceptance output
- global judgment workbench views can summarize structural regressions and bottlenecks
- archive-ready payloads can serialize the structural judgment cleanly

**Step 2: Run tests to verify they fail**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_structural_judgment.py tests/unit/test_judgment_substrate.py tests/unit/test_dashboard_api.py -q
```

Expected: `FAIL` because structural judgment does not exist yet as a first-class channel.

**Step 3: Write the minimal implementation**

Implement:

- a structural read model built from deterministic runtime/workbench signals
- rule and baseline diff helpers that do not depend on semantic evaluator output
- mission and global workbench projections that surface structural regressions distinctly from semantic findings

Do not:

- replace semantic acceptance
- introduce a second review stack
- add write actions

**Step 4: Run focused verification**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_structural_judgment.py tests/unit/test_judgment_substrate.py tests/unit/test_dashboard_api.py -q
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 ruff check src/spec_orch/services/structural_judgment.py src/spec_orch/services/judgment_substrate.py src/spec_orch/services/judgment_workbench.py src/spec_orch/dashboard/app.py src/spec_orch/dashboard/missions.py tests/unit/test_structural_judgment.py tests/unit/test_judgment_substrate.py tests/unit/test_dashboard_api.py
```

Expected: `PASS`

**Step 5: Close the tranche with formal acceptance and archive**

Run the standing closeout commands and write the next release bundle.

### Task 4: Tighten learning promotion discipline

**Files:**
- Create: `src/spec_orch/services/learning_promotion_policy.py`
- Modify: `src/spec_orch/services/learning_workbench.py`
- Modify: `src/spec_orch/services/promotion_service.py`
- Modify: `src/spec_orch/services/evolution/promotion_registry.py`
- Modify: `src/spec_orch/services/memory/service.py`
- Test: `tests/unit/test_learning_workbench.py`
- Test: `tests/unit/test_evolution_promotion_registry.py`
- Test: `tests/unit/test_memory_service.py`
- Add: `tests/unit/test_learning_promotion_policy.py`

**Step 1: Write the failing tests**

Add tests that require:

- reviewed-only promotion eligibility
- explicit memory-write eligibility
- fixture promotion rules
- high-impact promotion review gates
- rollback / retirement / supersession states
- archive lineage joins that explain why an item was promoted, held, rolled back, or retired

**Step 2: Run tests to verify they fail**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_learning_promotion_policy.py tests/unit/test_learning_workbench.py tests/unit/test_evolution_promotion_registry.py tests/unit/test_memory_service.py -q
```

Expected: `FAIL` because Learning Workbench is currently a visibility layer, not a disciplined promotion governor.

**Step 3: Write the minimal implementation**

Implement:

- a policy seam that classifies reviewed outcomes into `promote`, `hold`, `reject`, `rollback`, or `retire`
- provenance-aware registry entries
- lineage joins from archive bundle back to promoted learning objects
- read-side exposure in Learning Workbench without adding large new UI first

Do not:

- auto-promote broad classes of findings
- expand learning UI before policy discipline is explicit

**Step 4: Run focused verification**

Run:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 python -m pytest tests/unit/test_learning_promotion_policy.py tests/unit/test_learning_workbench.py tests/unit/test_evolution_promotion_registry.py tests/unit/test_memory_service.py -q
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 ruff check src/spec_orch/services/learning_promotion_policy.py src/spec_orch/services/learning_workbench.py src/spec_orch/services/promotion_service.py src/spec_orch/services/evolution/promotion_registry.py src/spec_orch/services/memory/service.py tests/unit/test_learning_promotion_policy.py tests/unit/test_learning_workbench.py tests/unit/test_evolution_promotion_registry.py tests/unit/test_memory_service.py
```

Expected: `PASS`

**Step 5: Close the tranche with formal acceptance and archive**

Run the standing closeout commands and archive the learning-discipline tranche.

### Task 5: Continue showcase only after governance and judgment hardening

**Files:**
- Modify later: `src/spec_orch/services/showcase_workbench.py`
- Modify later: `src/spec_orch/dashboard/app.py`
- Modify later: `tests/unit/test_showcase_workbench.py`
- Modify later: `tests/unit/test_dashboard_api.py`
- Reference: `docs/plans/2026-04-03-son-363-showcase-narrative-layer-tranche-1.md`

**Step 1: Hold showcase expansion until Tasks 2-4 are closed**

Do not expand `SON-364..369` first.

**Step 2: After Tasks 2-4, open the next showcase tranche**

The first follow-up showcase tranche should consume, not invent:

- admission history
- structural judgment history
- learning promotion / rollback lineage

Expected showcase additions:

- richer release timeline
- compare-oriented storyline pivots
- lineage drilldowns from release bundle to workspace to promoted outcome

## Immediate Recommendation

If only one new tranche starts now, start:

### `SON-412` Tranche 1: Runtime Admission Enforcement

Reason:

- it hardens the already-landed runtime/workbench system
- it is upstream of trustworthy execution behavior
- it is upstream of meaningful structural judgment
- it reduces risk before further learning/showcase expansion

## Verification Checklist For This Program

Before saying a tranche is complete:

- [ ] focused pytest for the tranche is green
- [ ] `ruff check` is green
- [ ] `mypy` is green where the tranche adds new service seams
- [ ] canonical acceptance suite has been rerun fresh
- [ ] findings are classified
- [ ] harness bugs are fixed before archive write
- [ ] release bundle is written
- [ ] `docs/acceptance-history/index.json` is refreshed

