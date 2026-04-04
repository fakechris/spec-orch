# Phase 2 Hardening Execution Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Harden the already-landed SpecOrch runtime so the next self-hosting wave can rely on clear memory/context boundaries, independent verification, stronger runtime governance, and stricter learning discipline before we force Linear sync and chat-to-issue through the system.

**Architecture:** Treat the current intake/substrate/workbench/showcase stack as baseline already implemented on `main`. This plan is not an architecture rewrite. It adds stricter contracts on top of the existing seams in this order: memory/context layering, verification independence, `SON-412` tranche 2, structural judgment tranche 2, and learning promotion tranche 2. Every tranche still closes with the canonical acceptance/archive gate.

**Tech Stack:** Python 3.13, FastAPI, existing dashboard HTML/JS shell, pytest, ruff, mypy, canonical acceptance harness, acceptance-history archive, shared `uv` environment

## Ground Rules

- Start from the latest `main` only.
- Do not reopen surface-design work unless a hardening task strictly requires it.
- Treat `execution`, `judgment`, `archive`, and `promoted learning` as separate stores/contracts.
- Keep `research` or `implementation` artifacts from implicitly self-certifying `verification`.
- Use the standing canonical acceptance and release-bundle closeout rule at the end of every tranche.

## Standing Closeout Rule

Run after each tranche:

```bash
./tests/e2e/issue_start_smoke.sh --full
./tests/e2e/dashboard_ui_acceptance.sh --full
./tests/e2e/mission_start_acceptance.sh --full
./tests/e2e/exploratory_acceptance_smoke.sh --full
./tests/e2e/update_stability_acceptance_status.sh
```

If a `harness_bug` appears, fix it before rerunning. Then:

1. classify `harness_bug` / `n2n_bug` / `ux_gap`
2. rerun after `harness_bug` fixes
3. write a new release bundle under `docs/acceptance-history/releases/`
4. refresh `docs/acceptance-history/index.json`
5. write `source_run` compare notes against the immediately previous relevant bundle

## Task 1: Memory / Context Layering Contract

**Status:** Closed on `2026-04-04` after focused verification passed, canonical acceptance returned to `overall_status=pass`, and a release bundle was written under `docs/acceptance-history/releases/`.

**Files:**
- Modify: `src/spec_orch/domain/context.py`
- Modify: `src/spec_orch/services/context_assembler.py`
- Modify: `src/spec_orch/services/context/context_assembler.py`
- Modify: `src/spec_orch/services/memory/service.py`
- Modify: `src/spec_orch/services/operator_semantics.py`
- Modify: `src/spec_orch/services/showcase_workbench.py`
- Add: `tests/unit/test_context_layering.py`
- Modify: `tests/unit/test_memory_service.py`
- Modify: `tests/unit/test_operator_semantics.py`

**Step 1: Write the failing tests**

Add tests that require:

- execution context to remain separate from transcript/evidence context
- archive lineage to remain separate from promoted learning context
- context assembly to declare which layer each payload belongs to
- read models to consume only the layers they are allowed to read

**Step 2: Run tests to verify they fail**

Run:

```bash
UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-<path-to-shared-py313-venv>}" uv run --python 3.13 pytest tests/unit/test_context_layering.py tests/unit/test_memory_service.py tests/unit/test_operator_semantics.py -q
```

Expected: `FAIL` because the current context/memory seams still blur execution, evidence, archive, and promoted learning.

**Step 3: Write the minimal implementation**

Implement:

- explicit layer labels or contracts for:
  - execution context
  - transcript/evidence context
  - archive lineage context
  - promoted learning context
- assembler rules that preserve those boundaries
- memory-service helpers that stop returning one undifferentiated bucket

Do not:

- add a new global memory product surface
- migrate the whole repo to a new storage engine
- rewrite archive format

**Step 4: Run focused verification**

Run:

```bash
UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-<path-to-shared-py313-venv>}" uv run --python 3.13 pytest tests/unit/test_context_layering.py tests/unit/test_memory_service.py tests/unit/test_operator_semantics.py -q
UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-<path-to-shared-py313-venv>}" uv run --python 3.13 ruff check src/spec_orch/domain/context.py src/spec_orch/services/context_assembler.py src/spec_orch/services/context/context_assembler.py src/spec_orch/services/memory/service.py src/spec_orch/services/operator_semantics.py src/spec_orch/services/showcase_workbench.py tests/unit/test_context_layering.py tests/unit/test_memory_service.py tests/unit/test_operator_semantics.py
UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-<path-to-shared-py313-venv>}" uv run --python 3.13 mypy src/spec_orch/domain/context.py src/spec_orch/services/context_assembler.py src/spec_orch/services/memory/service.py src/spec_orch/services/operator_semantics.py
```

Expected: `PASS`

**Step 5: Commit**

```bash
git add src/spec_orch/domain/context.py src/spec_orch/services/context_assembler.py src/spec_orch/services/context/context_assembler.py src/spec_orch/services/memory/service.py src/spec_orch/services/operator_semantics.py src/spec_orch/services/showcase_workbench.py tests/unit/test_context_layering.py tests/unit/test_memory_service.py tests/unit/test_operator_semantics.py
git commit -m "feat: harden context layering contract"
```

## Task 2: Verification Independence Contract

**Status:** Closed on `2026-04-04` after focused verification passed, canonical acceptance returned to `overall_status=pass`, and a release bundle was written under `docs/acceptance-history/releases/`.

**Files:**
- Modify: `src/spec_orch/domain/protocols.py`
- Modify: `src/spec_orch/services/round_orchestrator.py`
- Modify: `src/spec_orch/services/mission_execution_service.py`
- Modify: `src/spec_orch/services/judgment_substrate.py`
- Modify: `src/spec_orch/services/acceptance/litellm_acceptance_evaluator.py`
- Modify: `src/spec_orch/services/acceptance/browser_evidence.py`
- Add: `tests/unit/test_verification_independence.py`
- Modify: `tests/unit/test_round_orchestrator.py`
- Modify: `tests/unit/test_judgment_substrate.py`

**Step 1: Write the failing tests**

Add tests that require:

- implementer/execution artifacts to be tagged separately from verifier/judgment artifacts
- verification routes to refuse self-certifying evidence bundles
- orchestration to preserve an explicit verification role boundary

**Step 2: Run tests to verify they fail**

Run:

```bash
UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-<path-to-shared-py313-venv>}" uv run --python 3.13 pytest tests/unit/test_verification_independence.py tests/unit/test_round_orchestrator.py tests/unit/test_judgment_substrate.py -q
```

Expected: `FAIL` because verification and implementation are not yet governed as an explicit independence contract.

**Step 3: Write the minimal implementation**

Implement:

- explicit verifier-versus-implementer provenance in review/evidence carriers
- substrate guards that keep semantic acceptance from blindly trusting implementation-originated claims
- orchestration helpers that preserve independent verification semantics

Do not:

- add a new verifier UI
- introduce a separate job scheduler
- change acceptance archive schema unless required for provenance tagging

**Step 4: Run focused verification**

Run:

```bash
UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-<path-to-shared-py313-venv>}" uv run --python 3.13 pytest tests/unit/test_verification_independence.py tests/unit/test_round_orchestrator.py tests/unit/test_judgment_substrate.py -q
UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-<path-to-shared-py313-venv>}" uv run --python 3.13 ruff check src/spec_orch/domain/protocols.py src/spec_orch/services/round_orchestrator.py src/spec_orch/services/mission_execution_service.py src/spec_orch/services/judgment_substrate.py src/spec_orch/services/acceptance/litellm_acceptance_evaluator.py src/spec_orch/services/acceptance/browser_evidence.py tests/unit/test_verification_independence.py tests/unit/test_round_orchestrator.py tests/unit/test_judgment_substrate.py
UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-<path-to-shared-py313-venv>}" uv run --python 3.13 mypy src/spec_orch/domain/protocols.py src/spec_orch/services/round_orchestrator.py src/spec_orch/services/judgment_substrate.py
```

Expected: `PASS`

**Step 5: Commit**

```bash
git add src/spec_orch/domain/protocols.py src/spec_orch/services/round_orchestrator.py src/spec_orch/services/mission_execution_service.py src/spec_orch/services/judgment_substrate.py src/spec_orch/services/acceptance/litellm_acceptance_evaluator.py src/spec_orch/services/acceptance/browser_evidence.py tests/unit/test_verification_independence.py tests/unit/test_round_orchestrator.py tests/unit/test_judgment_substrate.py
git commit -m "feat: enforce verification independence"
```

## Task 3: `SON-412` Tranche 2

**Status:** Closed on `2026-04-04` after focused verification passed, canonical acceptance returned to `overall_status=pass`, and a release bundle was written under `docs/acceptance-history/releases/`.

**Files:**
- Modify: `src/spec_orch/services/admission_governor.py`
- Modify: `src/spec_orch/services/daemon.py`
- Modify: `src/spec_orch/services/execution_substrate.py`
- Modify: `src/spec_orch/services/execution_workbench.py`
- Modify: `src/spec_orch/dashboard/control.py`
- Modify: `src/spec_orch/dashboard/app.py`
- Modify: `tests/unit/test_admission_governor.py`
- Modify: `tests/unit/test_daemon.py`
- Modify: `tests/unit/test_execution_substrate.py`
- Modify: `tests/unit/test_execution_workbench.py`
- Modify: `tests/unit/test_dashboard_api.py`

**Step 1: Write the failing tests**

Require:

- budget scopes beyond the current daemon-level defer path
- degrade/reject posture with explicit reasons
- carrier propagation into execution workbench and control overview
- mission/worker/verifier budget visibility

**Step 2: Run tests to verify they fail**

Run:

```bash
UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-<path-to-shared-py313-venv>}" uv run --python 3.13 pytest tests/unit/test_admission_governor.py tests/unit/test_daemon.py tests/unit/test_execution_substrate.py tests/unit/test_execution_workbench.py tests/unit/test_dashboard_api.py -q
```

Expected: `FAIL`

**Step 3: Write the minimal implementation**

Extend tranche 1 to:

- persist richer admission posture
- distinguish pressure source by runtime role
- expose degrade/reject counts and reasons in the read model

**Step 4: Run focused verification**

Run:

```bash
UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-<path-to-shared-py313-venv>}" uv run --python 3.13 pytest tests/unit/test_admission_governor.py tests/unit/test_daemon.py tests/unit/test_execution_substrate.py tests/unit/test_execution_workbench.py tests/unit/test_dashboard_api.py -q
UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-<path-to-shared-py313-venv>}" uv run --python 3.13 ruff check src/spec_orch/services/admission_governor.py src/spec_orch/services/daemon.py src/spec_orch/services/execution_substrate.py src/spec_orch/services/execution_workbench.py src/spec_orch/dashboard/control.py src/spec_orch/dashboard/app.py tests/unit/test_admission_governor.py tests/unit/test_daemon.py tests/unit/test_execution_substrate.py tests/unit/test_execution_workbench.py tests/unit/test_dashboard_api.py
```

Expected: `PASS`

**Step 5: Commit**

```bash
git add src/spec_orch/services/admission_governor.py src/spec_orch/services/daemon.py src/spec_orch/services/execution_substrate.py src/spec_orch/services/execution_workbench.py src/spec_orch/dashboard/control.py src/spec_orch/dashboard/app.py tests/unit/test_admission_governor.py tests/unit/test_daemon.py tests/unit/test_execution_substrate.py tests/unit/test_execution_workbench.py tests/unit/test_dashboard_api.py
git commit -m "feat: extend admission governor posture"
```

## Task 4: Deterministic Structural Judgment Tranche 2

**Status:** Closed on `2026-04-04` after focused verification passed, canonical acceptance returned to `overall_status=pass`, and a release bundle was written under `docs/acceptance-history/releases/`.

**Files:**
- Modify: `src/spec_orch/services/structural_judgment.py`
- Modify: `src/spec_orch/services/judgment_substrate.py`
- Modify: `src/spec_orch/services/judgment_workbench.py`
- Modify: `src/spec_orch/dashboard/app.py`
- Modify: `src/spec_orch/dashboard/missions.py`
- Modify: `tests/unit/test_structural_judgment.py`
- Modify: `tests/unit/test_judgment_substrate.py`
- Modify: `tests/unit/test_dashboard_api.py`

**Step 1: Write the failing tests**

Require:

- richer deterministic rule families
- bottleneck/root-cause decomposition
- stable baseline diff summaries
- workbench projections that separate structural signals from semantic verdicts

**Step 2: Run tests to verify they fail**

Run:

```bash
UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-<path-to-shared-py313-venv>}" uv run --python 3.13 pytest tests/unit/test_structural_judgment.py tests/unit/test_judgment_substrate.py tests/unit/test_dashboard_api.py -q
```

Expected: `FAIL`

**Step 3: Write the minimal implementation**

Extend tranche 1 to:

- normalize more deterministic rules
- make baseline drift readable and archive-friendly
- preserve structural signals as independent first-class judgment carriers

**Step 4: Run focused verification**

Run:

```bash
UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-<path-to-shared-py313-venv>}" uv run --python 3.13 pytest tests/unit/test_structural_judgment.py tests/unit/test_judgment_substrate.py tests/unit/test_dashboard_api.py -q
UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-<path-to-shared-py313-venv>}" uv run --python 3.13 ruff check src/spec_orch/services/structural_judgment.py src/spec_orch/services/judgment_substrate.py src/spec_orch/services/judgment_workbench.py src/spec_orch/dashboard/app.py src/spec_orch/dashboard/missions.py tests/unit/test_structural_judgment.py tests/unit/test_judgment_substrate.py tests/unit/test_dashboard_api.py
```

Expected: `PASS`

**Step 5: Commit**

```bash
git add src/spec_orch/services/structural_judgment.py src/spec_orch/services/judgment_substrate.py src/spec_orch/services/judgment_workbench.py src/spec_orch/dashboard/app.py src/spec_orch/dashboard/missions.py tests/unit/test_structural_judgment.py tests/unit/test_judgment_substrate.py tests/unit/test_dashboard_api.py
git commit -m "feat: deepen structural judgment signals"
```

## Task 5: Learning Promotion Discipline Tranche 2

**Status:** Closed on `2026-04-04` after focused verification passed, canonical acceptance returned to `overall_status=pass`, and a release bundle was written under `docs/acceptance-history/releases/`.

**Files:**
- Modify: `src/spec_orch/services/learning_promotion_policy.py`
- Modify: `src/spec_orch/services/learning_workbench.py`
- Modify: `src/spec_orch/services/evolution/promotion_registry.py`
- Modify: `src/spec_orch/services/memory/service.py`
- Modify: `tests/unit/test_learning_promotion_policy.py`
- Modify: `tests/unit/test_learning_workbench.py`
- Modify: `tests/unit/test_evolution_promotion_registry.py`
- Modify: `tests/unit/test_memory_service.py`
- Modify: `tests/unit/test_dashboard_api.py`

**Step 1: Write the failing tests**

Require:

- explicit keep/discard/promote/rollback style verdict discipline
- clearer separation between raw archive lineage and promoted knowledge
- workbench summaries that expose experiment outcome rather than just lineage accumulation

**Step 2: Run tests to verify they fail**

Run:

```bash
UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-<path-to-shared-py313-venv>}" uv run --python 3.13 pytest tests/unit/test_learning_promotion_policy.py tests/unit/test_learning_workbench.py tests/unit/test_evolution_promotion_registry.py tests/unit/test_memory_service.py tests/unit/test_dashboard_api.py -q
```

Expected: `FAIL`

**Step 3: Write the minimal implementation**

Extend tranche 1 to:

- add explicit verdict semantics
- encode rollback/retire-ready states
- keep raw archive history distinct from promoted artifacts

**Step 4: Run focused verification**

Run:

```bash
UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-<path-to-shared-py313-venv>}" uv run --python 3.13 pytest tests/unit/test_learning_promotion_policy.py tests/unit/test_learning_workbench.py tests/unit/test_evolution_promotion_registry.py tests/unit/test_memory_service.py tests/unit/test_dashboard_api.py -q
UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-<path-to-shared-py313-venv>}" uv run --python 3.13 ruff check src/spec_orch/services/learning_promotion_policy.py src/spec_orch/services/learning_workbench.py src/spec_orch/services/evolution/promotion_registry.py src/spec_orch/services/memory/service.py tests/unit/test_learning_promotion_policy.py tests/unit/test_learning_workbench.py tests/unit/test_evolution_promotion_registry.py tests/unit/test_memory_service.py tests/unit/test_dashboard_api.py
UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-<path-to-shared-py313-venv>}" uv run --python 3.13 mypy src/spec_orch/services/learning_promotion_policy.py src/spec_orch/services/learning_workbench.py src/spec_orch/services/evolution/promotion_registry.py src/spec_orch/services/memory/service.py
```

Expected: `PASS`

**Step 5: Commit**

```bash
git add src/spec_orch/services/learning_promotion_policy.py src/spec_orch/services/learning_workbench.py src/spec_orch/services/evolution/promotion_registry.py src/spec_orch/services/memory/service.py tests/unit/test_learning_promotion_policy.py tests/unit/test_learning_workbench.py tests/unit/test_evolution_promotion_registry.py tests/unit/test_memory_service.py tests/unit/test_dashboard_api.py
git commit -m "feat: extend learning promotion discipline"
```

## After This Plan

Do **not** start the self-hosting Linear wave until the five tasks above are complete and archived.

The next plan after this one should cover:

- Linear epic/issue synchronization with actual work and tranche state
- structured plan projection into Linear
- end-to-end chat-to-issue flow
