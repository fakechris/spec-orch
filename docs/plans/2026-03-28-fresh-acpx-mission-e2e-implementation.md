# Fresh Acpx Mission E2E Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the first repeatable `Fresh Acpx Mission E2E` path so SpecOrch can prove a brand-new mission can be created, planned, launched, picked up by daemon/runner, executed by a fresh ACPX builder flow, and then validated through dashboard acceptance.

**Architecture:** Reuse the now-proven `Workflow Replay E2E` harness for the post-launch dashboard half, but prepend a fresh mission bootstrap phase that creates a new mission, binds a live execution path, and waits for real round artifacts before replay begins. Treat freshness and workflow operability as separate proof layers, with explicit artifacts for each.

**Tech Stack:** Python 3.13, SpecOrch CLI/dashboard/daemon, ACPX builder adapter, Playwright browser evidence runner, LiteLLM/MiniMax-style evaluator adapters, repo-local `.spec_orch/skills/` manifests, JSON artifact contracts.

## Success Criteria

- A new mission can be created without reusing existing mission state.
- The mission can be approved and planned from the supported entry path.
- Launch produces real lifecycle state and real issue ids for the fresh mission.
- Daemon or equivalent live mission runner picks up the mission and produces a real round directory.
- A fresh ACPX builder execution occurs for at least one packet.
- Post-run dashboard `Workflow Replay E2E` can validate the resulting mission surfaces.
- Final report distinguishes:
  - what was proven by fresh execution
  - what was proven by post-run workflow replay
  - what remains unproven

## Constraints

- Do not claim full freshness from reused smoke artifacts.
- Do not treat workflow replay as a substitute for daemon/builder execution.
- Keep the first path narrow: one mission, one wave, minimal packet count.
- Prefer local-only repeatability over broad provider abstraction in the first increment.

## Artifact Contract

The first `Fresh Acpx Mission E2E` run should emit:

- `mission_bootstrap.json`
- `launch.json`
- `daemon_run.json`
- `fresh_round_summary.json`
- `builder_execution_summary.json`
- `browser_evidence.json`
- `acceptance_review.json`
- `fresh_acpx_mission_e2e_report.md`

## Task 1: Freeze the proof boundary

**Files:**
- Modify: `docs/plans/2026-03-28-workflow-replay-e2e-skill-contract.md`
- Create: `docs/plans/2026-03-28-fresh-acpx-mission-e2e-design.md`

**Step 1: Write the failing documentation assertions**

Document the exact distinction that must remain true:

- `Workflow Replay E2E` proves dashboard workflow operability.
- `Fresh Acpx Mission E2E` proves fresh mission execution plus post-run workflow validation.

**Step 2: Review current docs to locate ambiguity**

Run:

```bash
rg -n "Fresh Acpx Mission E2E|Workflow Replay E2E|fresh mission" docs
```

Expected:

- current docs mention the distinction, but no dedicated fresh-path design exists

**Step 3: Write the minimal design doc**

Define:

- fresh mission boundary
- freshness proof checkpoints
- artifact list
- failure classes:
  - mission bootstrap failure
  - launch failure
  - daemon pickup failure
  - builder execution failure
  - post-run replay failure

**Step 4: Re-read the new doc**

Expected:

- no ambiguity remains about what counts as fresh proof

## Task 2: Standardize fresh mission seed data

**Files:**
- Create: `tests/fixtures/fresh_acpx_mission_request.json`
- Create: `tests/fixtures/fresh_acpx_campaign.json`
- Test: `tests/unit/test_acceptance_models.py`

**Step 1: Write the failing test**

Add a test that validates the fixture payloads can round-trip and include:

- fresh mission id prefixing / uniqueness expectations
- launcher or CLI bootstrap fields
- post-run workflow replay routes

**Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/unit/test_acceptance_models.py -q
```

Expected:

- fail because the fixtures do not yet exist

**Step 3: Write minimal fixture files**

Add:

- fresh mission request JSON
- fresh campaign JSON for post-run replay

Keep the first flow narrow and deterministic.

**Step 4: Re-run test**

Expected:

- pass

## Task 3: Add a fresh-mission bootstrap helper

**Files:**
- Modify: `src/spec_orch/dashboard/launcher.py`
- Modify: `src/spec_orch/services/round_orchestrator.py`
- Test: `tests/unit/test_dashboard_launcher.py`

**Step 1: Write the failing test**

Add a test for a helper that produces a unique fresh mission request and marks it as:

- fresh
- local-only
- safe for replay / cleanup

**Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/unit/test_dashboard_launcher.py -q
```

Expected:

- fail because the helper does not exist

**Step 3: Write minimal implementation**

The helper should:

- generate a fresh mission id
- define minimal acceptance / constraints
- record enough metadata for later artifact correlation

**Step 4: Re-run test**

Expected:

- pass

## Task 4: Add fresh execution evidence plumbing

**Files:**
- Modify: `src/spec_orch/services/round_orchestrator.py`
- Modify: `src/spec_orch/services/visual/playwright_visual_eval.py`
- Modify: `src/spec_orch/services/acceptance/litellm_acceptance_evaluator.py`
- Test: `tests/unit/test_round_orchestrator.py`
- Test: `tests/unit/test_playwright_visual_eval.py`
- Test: `tests/unit/test_litellm_acceptance_evaluator.py`

**Step 1: Write the failing tests**

Require the system to distinguish:

- freshness evidence
- replay evidence

within the same acceptance artifact set.

**Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/unit/test_round_orchestrator.py tests/unit/test_playwright_visual_eval.py tests/unit/test_litellm_acceptance_evaluator.py -q
```

Expected:

- fail because no fresh-proof contract exists yet

**Step 3: Write minimal implementation**

Add fields that make freshness explicit:

- builder execution summary
- daemon pickup evidence
- fresh round path
- replay-vs-fresh proof split

**Step 4: Re-run tests**

Expected:

- pass

## Task 5: Define the first executable dogfood path

**Files:**
- Create: `tests/e2e/fresh_acpx_mission_smoke.sh`
- Modify: `docs/guides/supervised-mission-e2e-playbook.md`
- Modify: `docs/guides/operator-console.md`

**Step 1: Write the failing shell-level expectation**

The script should describe:

- create fresh mission
- approve / plan
- launch
- wait for daemon/builder evidence
- run post-run workflow replay
- emit report paths

**Step 2: Draft the script skeleton**

Do not over-automate the first version.
Focus on reproducibility and explicit checkpoints.

**Step 3: Update operator docs**

Explain:

- when to run `Workflow Replay E2E`
- when to run `Fresh Acpx Mission E2E`
- why both are needed

## Task 6: Run the first real fresh path

**Files:**
- Create: `docs/specs/<fresh-mission-id>/operator/fresh-acpx-mission-e2e/...`
- Modify: `docs/plans/2026-03-28-dashboard-workflow-acceptance-judgment.md`
- Modify: `progress.md`

**Step 1: Execute the first fresh path**

Expected checkpoints:

- mission exists
- launch recorded
- lifecycle state active
- round directory created
- at least one builder execution artifact exists
- post-run workflow replay produces evidence

**Step 2: Record the real result**

Do not massage the outcome.
If it fails mid-pipeline, record which proof boundary failed.

**Step 3: Update the judgment docs**

Add:

- proven fresh path capabilities
- still-unproven areas
- whether a second iteration is needed before claiming success

## Verification Commands

Use these as the minimum verification set while implementing:

```bash
uv run pytest tests/unit/test_skill_format.py -q
uv run pytest tests/unit/test_dashboard_package.py -q
uv run pytest tests/unit/test_dashboard_launcher.py tests/unit/test_round_orchestrator.py tests/unit/test_litellm_acceptance_evaluator.py tests/unit/test_playwright_visual_eval.py -q
uv run mypy src/
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
```

## Recommended Execution Order

1. Freeze proof boundary
2. Standardize fresh mission fixtures
3. Add bootstrap helper
4. Add fresh evidence plumbing
5. Add first e2e smoke script
6. Run one real fresh mission
7. Only then claim the first `Fresh Acpx Mission E2E`

## Handoff

Plan complete and saved to `docs/plans/2026-03-28-fresh-acpx-mission-e2e-implementation.md`.

Recommended next execution mode:

- Start with subagent-driven implementation only after this branch is cleaned for PR or split, because the current worktree still mixes workflow-quality code changes with local replay artifacts.
