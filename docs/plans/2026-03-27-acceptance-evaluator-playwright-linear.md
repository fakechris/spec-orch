# Acceptance Evaluator with Playwright and Linear Filing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an independent acceptance evaluator that uses browser evidence plus a separate LLM to assess mission output and file actionable Linear issues when confidence is high enough.

**Architecture:** Reuse the existing supervised mission seams instead of inventing a parallel orchestration path. Add a new acceptance-evaluator layer that runs after a supervised round, collects Playwright/browser evidence, sends that evidence to a separate evaluator model, persists a structured acceptance result, and optionally files Linear issues behind a configurable policy gate.

**Tech Stack:** FastAPI dashboard/operator console, existing `RoundOrchestrator` and `VisualEvaluatorAdapter` seams, Playwright-based browser capture, LiteLLM-backed evaluator adapter, Linear GraphQL client, pytest, ruff, mypy.

---

## Context

The operator console is now strong enough to observe supervised missions, but dogfooding still depends too much on a human operator reading evidence manually:

- open the dashboard
- inspect transcript, visual QA, and costs
- decide if the mission output is acceptable
- manually create follow-up issues

That is too slow and too subjective. We already have the right primitives:

- `SupervisorAdapter`
- `VisualEvaluatorAdapter`
- command-based Playwright visual evaluation
- Linear issue creation/binding
- dedicated operator surfaces for approvals, evidence, visual QA, and costs

The next slice is to add an **independent acceptance evaluator**:

- not the builder judging itself
- not the supervisor reusing the same evidence in the same role
- but a separate evaluator path that can operate like an external QA operator

## Scope

This slice should deliver the smallest useful acceptance loop:

1. collect browser/visual/runtime evidence for a completed round
2. pass the evidence to a separate evaluator LLM
3. persist a structured `acceptance_review.json`
4. surface the result in the operator console
5. optionally file a Linear issue when the evaluator says the run should be rejected

This slice does **not** need:

- autonomous bug fixing
- multi-agent debate loops
- full UI diff authoring
- broad product analytics or benchmark infrastructure
- a general-purpose issue triage AI

## Task 1: Acceptance domain models and protocol seam

**Files:**
- Modify: `src/spec_orch/domain/models.py`
- Modify: `src/spec_orch/domain/protocols.py`
- Test: `tests/unit/test_acceptance_models.py`
- Test: `tests/unit/test_pluggable_adapters.py`

**Step 1: Write the failing tests**

Add tests for:

- `AcceptanceFinding`
- `AcceptanceIssueProposal`
- `AcceptanceReviewResult`
- protocol conformance for a stub `AcceptanceEvaluatorAdapter`

The result model should cover:

- `status` (`pass`, `warn`, `fail`)
- `summary`
- `confidence`
- `findings`
- `issue_proposals`
- `artifacts`
- `tested_routes`
- `evaluator`

**Step 2: Run test to verify it fails**

Run:

```bash
uv run --python 3.13 python -m pytest tests/unit/test_acceptance_models.py tests/unit/test_pluggable_adapters.py -q
```

Expected:
- model or protocol import failures because acceptance types do not exist yet

**Step 3: Write minimal implementation**

Add the smallest typed domain model set plus a protocol:

- `AcceptanceFinding`
- `AcceptanceIssueProposal`
- `AcceptanceReviewResult`
- `AcceptanceEvaluatorAdapter`

Keep serialization simple:

- `to_dict()`
- `from_dict()`
- no extra hierarchy unless the tests need it

**Step 4: Run test to verify it passes**

Run:

```bash
uv run --python 3.13 python -m pytest tests/unit/test_acceptance_models.py tests/unit/test_pluggable_adapters.py -q
```

Expected:
- PASS

**Step 5: Commit**

```bash
git add src/spec_orch/domain/models.py src/spec_orch/domain/protocols.py tests/unit/test_acceptance_models.py tests/unit/test_pluggable_adapters.py
git commit -m "feat: add acceptance evaluator domain models"
```

## Task 2: Browser evidence collector for acceptance review

**Files:**
- Create: `src/spec_orch/services/acceptance/browser_evidence.py`
- Modify: `src/spec_orch/services/visual/playwright_visual_eval.py`
- Test: `tests/unit/test_browser_evidence.py`

**Step 1: Write the failing tests**

Cover:

- building an acceptance browser request from mission/round context
- collecting stable evidence paths for:
  - screenshots
  - console errors
  - page errors
  - visited routes
- reusing existing Playwright sample machinery where possible

**Step 2: Run test to verify it fails**

Run:

```bash
uv run --python 3.13 python -m pytest tests/unit/test_browser_evidence.py -q
```

Expected:
- module or function import failures

**Step 3: Write minimal implementation**

Create a small service that turns round context into browser evidence payloads.

Do not add a second Playwright stack. Reuse the existing sample concepts:

- `VisualEvalRequest`
- `PageSnapshot`
- screenshot collection

But return a dashboard/operator-friendly structure with:

- `tested_routes`
- `screenshots`
- `console_errors`
- `page_errors`
- `artifact_paths`

**Step 4: Run test to verify it passes**

Run:

```bash
uv run --python 3.13 python -m pytest tests/unit/test_browser_evidence.py -q
```

Expected:
- PASS

**Step 5: Commit**

```bash
git add src/spec_orch/services/acceptance/browser_evidence.py src/spec_orch/services/visual/playwright_visual_eval.py tests/unit/test_browser_evidence.py
git commit -m "feat: add acceptance browser evidence collector"
```

## Task 3: LiteLLM acceptance evaluator adapter

**Files:**
- Create: `src/spec_orch/services/acceptance/litellm_acceptance_evaluator.py`
- Test: `tests/unit/test_litellm_acceptance_evaluator.py`

**Step 1: Write the failing tests**

Cover:

- prompt payload includes:
  - mission metadata
  - round summary
  - browser evidence
  - transcript/visual/cost review routes or artifact paths
- successful parse into `AcceptanceReviewResult`
- malformed LLM output degrades to a safe `warn` or `fail` result instead of crashing

**Step 2: Run test to verify it fails**

Run:

```bash
uv run --python 3.13 python -m pytest tests/unit/test_litellm_acceptance_evaluator.py -q
```

Expected:
- import failures because adapter does not exist yet

**Step 3: Write minimal implementation**

Add a separate acceptance evaluator adapter, distinct from the supervisor.

The adapter should:

- call LiteLLM with a dedicated evaluator prompt
- request structured JSON only
- return:
  - `pass`, `warn`, or `fail`
  - findings
  - issue proposals
  - confidence
- degrade safely when parsing fails

Do not reuse supervisor prompt wording. Acceptance review should explicitly answer:

- did the run meet the intended result?
- what is broken?
- what should be filed as a follow-up issue?

**Step 4: Run test to verify it passes**

Run:

```bash
uv run --python 3.13 python -m pytest tests/unit/test_litellm_acceptance_evaluator.py -q
```

Expected:
- PASS

**Step 5: Commit**

```bash
git add src/spec_orch/services/acceptance/litellm_acceptance_evaluator.py tests/unit/test_litellm_acceptance_evaluator.py
git commit -m "feat: add litellm acceptance evaluator"
```

## Task 4: Persist acceptance review artifacts and policy-gated Linear filing

**Files:**
- Create: `src/spec_orch/services/acceptance/linear_filing.py`
- Modify: `src/spec_orch/services/round_orchestrator.py`
- Modify: `src/spec_orch/services/launcher.py`
- Test: `tests/unit/test_acceptance_linear_filing.py`
- Test: `tests/unit/test_round_orchestrator.py`

**Step 1: Write the failing tests**

Cover:

- round orchestrator writes `acceptance_review.json`
- when policy says “file issue”, a Linear issue proposal is turned into a real issue payload
- low-confidence warnings do not auto-file
- filing failures are recorded in artifacts, not raised as fatal round errors

**Step 2: Run test to verify it fails**

Run:

```bash
uv run --python 3.13 python -m pytest tests/unit/test_acceptance_linear_filing.py tests/unit/test_round_orchestrator.py -q
```

Expected:
- missing acceptance persistence/filer integration

**Step 3: Write minimal implementation**

Wire the new acceptance evaluator into the round flow **after** core round artifacts exist.

Persist:

- `docs/specs/<mission_id>/rounds/round-XX/acceptance_review.json`

Add a small filing policy:

- auto-file only when:
  - `status == "fail"`
  - confidence crosses threshold
  - proposal severity is high enough

Record filed issues back into the acceptance artifact.

Do not make acceptance filing block round completion.

**Step 4: Run test to verify it passes**

Run:

```bash
uv run --python 3.13 python -m pytest tests/unit/test_acceptance_linear_filing.py tests/unit/test_round_orchestrator.py -q
```

Expected:
- PASS

**Step 5: Commit**

```bash
git add src/spec_orch/services/acceptance/linear_filing.py src/spec_orch/services/round_orchestrator.py src/spec_orch/services/launcher.py tests/unit/test_acceptance_linear_filing.py tests/unit/test_round_orchestrator.py
git commit -m "feat: persist acceptance review and file follow-up issues"
```

## Task 5: Operator console acceptance surface

**Files:**
- Modify: `src/spec_orch/dashboard/surfaces.py`
- Modify: `src/spec_orch/dashboard/routes.py`
- Modify: `src/spec_orch/dashboard/app.py`
- Modify: `src/spec_orch/dashboard_assets/static/operator-console.js`
- Modify: `src/spec_orch/dashboard_assets/static/operator-console.css`
- Test: `tests/unit/test_dashboard_api.py`
- Test: `tests/unit/test_dashboard_package.py`

**Step 1: Write the failing tests**

Cover:

- `GET /api/missions/{mission_id}/acceptance-review`
- mission detail links into acceptance review
- acceptance findings and filed issues appear in the operator console
- empty state when no acceptance review exists yet

**Step 2: Run test to verify it fails**

Run:

```bash
uv run --python 3.13 python -m pytest tests/unit/test_dashboard_api.py tests/unit/test_dashboard_package.py -q -k acceptance
```

Expected:
- no acceptance route or UI anchors yet

**Step 3: Write minimal implementation**

Add a dedicated acceptance surface, separate from generic visual QA.

Show:

- latest acceptance result
- evaluator model
- tested routes
- screenshots / artifacts
- findings
- filed Linear issues
- next operator action

Keep the visual language operator-first:

- clear pass/warn/fail hierarchy
- issue filing status visible
- no chat-like presentation

**Step 4: Run test to verify it passes**

Run:

```bash
uv run --python 3.13 python -m pytest tests/unit/test_dashboard_api.py tests/unit/test_dashboard_package.py -q -k acceptance
```

Expected:
- PASS

**Step 5: Commit**

```bash
git add src/spec_orch/dashboard/surfaces.py src/spec_orch/dashboard/routes.py src/spec_orch/dashboard/app.py src/spec_orch/dashboard_assets/static/operator-console.js src/spec_orch/dashboard_assets/static/operator-console.css tests/unit/test_dashboard_api.py tests/unit/test_dashboard_package.py
git commit -m "feat: add acceptance review operator surface"
```

## Task 6: Config, docs, and dogfood path

**Files:**
- Modify: `spec-orch.toml`
- Modify: `docs/reference/spec-orch-toml.md`
- Modify: `docs/guides/operator-console.md`
- Modify: `docs/guides/supervised-mission-e2e-playbook.md`
- Modify: `tests/e2e/supervised_mission_minimax.sh`

**Step 1: Write the failing test or assertion**

At minimum, add doc/config assertions or focused tests that prove:

- config can declare an acceptance evaluator
- the E2E script can enable it

**Step 2: Run verification to prove the gap**

Run:

```bash
uv run --python 3.13 python -m pytest tests/unit/test_daemon_config.py -q
```

Expected:
- no acceptance evaluator wiring yet

**Step 3: Write minimal implementation**

Document:

- how acceptance evaluation differs from supervisor review
- how to enable:
  - browser evidence capture
  - evaluator model
  - auto-file policy
- how to dogfood with a different LLM than the builder/supervisor

Update the E2E path so a real operator can run:

- builder
- supervisor
- acceptance evaluator

in one controlled loop.

**Step 4: Run verification to prove it passes**

Run:

```bash
uv run --python 3.13 python -m pytest tests/unit/test_daemon_config.py -q
```

Expected:
- PASS

**Step 5: Commit**

```bash
git add spec-orch.toml docs/reference/spec-orch-toml.md docs/guides/operator-console.md docs/guides/supervised-mission-e2e-playbook.md tests/e2e/supervised_mission_minimax.sh
git commit -m "docs: wire acceptance evaluator into config and dogfood flow"
```

## Full Verification

Run the full project verification before opening a PR for this feature:

```bash
uv run --python 3.13 python -m ruff check src/ tests/
uv run --python 3.13 python -m ruff format --check src/ tests/
uv run --python 3.13 python -m mypy src/
uv run --python 3.13 python -m pytest -q
uv run --python 3.13 python -c "print('build ok')"
```

Expected:

- `ruff check` clean
- `ruff format --check` clean
- `mypy` clean
- `pytest` all green
- `build ok`

## Notes for Implementation

- Keep the acceptance evaluator independent from the builder and supervisor roles.
- Do not auto-file noisy low-confidence findings.
- Prefer policy-gated filing plus operator visibility over fully autonomous bug spam.
- Reuse existing mission/round artifact directories instead of inventing a second storage layout.
- Keep the first version narrow: one round, one acceptance result, one filing policy.

Plan complete and saved to `docs/plans/2026-03-27-acceptance-evaluator-playwright-linear.md`. Two execution options:

1. Subagent-Driven (this session) - I dispatch fresh subagent per task, review between tasks, fast iteration
2. Parallel Session (separate) - Open new session with executing-plans, batch execution with checkpoints

Which approach?
