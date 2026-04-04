# Self-Hosting Dogfood Wave 1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** make `spec-orch` use its own hardened intake, Linear mirror, and acceptance protocols as the default internal development workflow.

**Architecture:** build on the already-landed Linear sync and acceptance hardening seams. Add a safe report-first drift layer, enrich the mirrored plan/governance contract, then harden the `chat -> canonical issue -> workspace -> Linear` lifecycle and close the wave with canonical acceptance plus archive write-back.

**Tech Stack:** Python 3.13, Typer CLI, Linear GraphQL client, JSON mission artifacts under `docs/specs/`, markdown `SpecOrch Mirror` blocks, pytest, ruff, mypy, canonical acceptance harness.

## Review Frame

Every tranche must answer these five review dimensions and name the lowest subsystem as the next bottleneck:

1. `Instructions`
2. `State`
3. `Verification`
4. `Scope`
5. `Lifecycle`

Retained information must stay split into:

- `Active Context`
- `Working State`
- `Review Evidence`
- `Archive`
- `Promoted Learning`

## Status

- `Task 1` complete
- `Task 2` complete
- `Task 3` complete
- `Task 4` complete
- Current `5-subsystem` review:
  - `Instructions`: pass
  - `State`: pass
  - `Verification`: pass
  - `Scope`: pass
  - `Lifecycle`: weakest-pass
- Next bottleneck: `Lifecycle`

## Task 1: Linear Drift Inventory and Safe Backfill

**Files:**
- Modify: `src/spec_orch/services/linear_plan_sync.py`
- Modify: `src/spec_orch/services/linear_write_back.py`
- Modify: `src/spec_orch/cli/mission_commands.py`
- Test: `tests/unit/test_linear_plan_sync.py`
- Test: `tests/unit/test_linear_write_back.py`
- Test: `tests/unit/test_cli_smoke.py`

**Intent:**

Do not start with bulk mutation. Add a report-first path that inventories bound missions, compares current runtime/plan truth with the current Linear mirror, and shows which missions are out of sync before writes happen.

**Step 1: Write failing tests for drift report mode**

Add tests that expect:

- `spec-orch linear-sync --report` to emit a per-mission drift report without calling `update_issue_description`
- the report to classify:
  - `missing_mirror`
  - `stale_plan_sync`
  - `workspace_mismatch`
  - `already_synced`

**Step 2: Run the targeted tests and watch them fail**

Run:

```bash
UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-.venv-py313}" uv run --python 3.13 pytest tests/unit/test_linear_plan_sync.py tests/unit/test_linear_write_back.py tests/unit/test_cli_smoke.py -q -k 'linear_sync or drift'
```

**Step 3: Implement the minimal drift inventory layer**

Add a non-mutating comparison helper that:

- loads current mission truth from local artifacts
- parses the current `SpecOrch Mirror` block from Linear
- computes a compact drift status and reason list

Add CLI options:

- `--report` for report-only mode
- `--json` for machine-readable output

**Step 4: Re-run the targeted tests**

Run the same pytest command and make it pass.

**Step 5: Verify style and types**

Run:

```bash
UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-.venv-py313}" uv run --python 3.13 ruff check src/spec_orch/services/linear_plan_sync.py src/spec_orch/services/linear_write_back.py src/spec_orch/cli/mission_commands.py tests/unit/test_linear_plan_sync.py tests/unit/test_linear_write_back.py tests/unit/test_cli_smoke.py
UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-.venv-py313}" uv run --python 3.13 ruff format --check src/spec_orch/services/linear_plan_sync.py src/spec_orch/services/linear_write_back.py src/spec_orch/cli/mission_commands.py tests/unit/test_linear_plan_sync.py tests/unit/test_linear_write_back.py tests/unit/test_cli_smoke.py
UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-.venv-py313}" uv run --python 3.13 mypy src/spec_orch/services/linear_plan_sync.py src/spec_orch/services/linear_write_back.py src/spec_orch/cli/mission_commands.py
```

**Step 6: Commit**

```bash
git add src/spec_orch/services/linear_plan_sync.py src/spec_orch/services/linear_write_back.py src/spec_orch/cli/mission_commands.py tests/unit/test_linear_plan_sync.py tests/unit/test_linear_write_back.py tests/unit/test_cli_smoke.py
git commit -m "feat: add linear drift reporting"
```

## Task 2: Mirror Plan and Governance State Into Linear

**Files:**
- Modify: `src/spec_orch/services/linear_plan_sync.py`
- Modify: `src/spec_orch/services/linear_mirror.py`
- Modify: `src/spec_orch/services/linear_write_back.py`
- Modify: `tests/unit/test_linear_plan_sync.py`
- Modify: `tests/unit/test_linear_mirror.py`
- Modify: `tests/unit/test_linear_write_back.py`

**Intent:**

The current mirror carries mission-local plan state, but the dogfood workflow also needs tranche/governance state visible in Linear: compact status, latest acceptance result, latest release bundle, and current bottleneck.

**Step 1: Write failing tests for governance projection**

Add tests that expect the mirror to carry a stable compact block for:

- `plan_state`
- `current_focus`
- `latest_acceptance_status`
- `latest_release_bundle`
- `next_bottleneck`

**Step 2: Run the targeted tests and confirm failure**

Run:

```bash
UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-.venv-py313}" uv run --python 3.13 pytest tests/unit/test_linear_plan_sync.py tests/unit/test_linear_mirror.py tests/unit/test_linear_write_back.py -q -k 'plan_sync or governance'
```

**Step 3: Implement the enriched mirror contract**

Keep the current `SpecOrch Mirror` shape additive. Add a compact `governance_sync` projection derived from:

- `plan.json`
- `launch.json`
- `intake_workspace.json`
- current acceptance status
- latest release bundle metadata if present

Do not copy raw archive or evidence into active mirror state.

**Step 4: Re-run targeted tests**

Run the same pytest command and make it pass.

**Step 5: Verify style and types**

Run:

```bash
UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-.venv-py313}" uv run --python 3.13 ruff check src/spec_orch/services/linear_plan_sync.py src/spec_orch/services/linear_mirror.py src/spec_orch/services/linear_write_back.py tests/unit/test_linear_plan_sync.py tests/unit/test_linear_mirror.py tests/unit/test_linear_write_back.py
UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-.venv-py313}" uv run --python 3.13 ruff format --check src/spec_orch/services/linear_plan_sync.py src/spec_orch/services/linear_mirror.py src/spec_orch/services/linear_write_back.py tests/unit/test_linear_plan_sync.py tests/unit/test_linear_mirror.py tests/unit/test_linear_write_back.py
UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-.venv-py313}" uv run --python 3.13 mypy src/spec_orch/services/linear_plan_sync.py src/spec_orch/services/linear_mirror.py src/spec_orch/services/linear_write_back.py
```

**Step 6: Commit**

```bash
git add src/spec_orch/services/linear_plan_sync.py src/spec_orch/services/linear_mirror.py src/spec_orch/services/linear_write_back.py tests/unit/test_linear_plan_sync.py tests/unit/test_linear_mirror.py tests/unit/test_linear_write_back.py
git commit -m "feat: mirror governance state into linear"
```

## Task 3: Chat-to-Issue Dogfood Lifecycle

**Files:**
- Modify: `src/spec_orch/services/conversation_service.py`
- Modify: `src/spec_orch/services/linear_conversation_adapter.py`
- Modify: `src/spec_orch/dashboard/launcher.py`
- Modify: `src/spec_orch/services/daemon.py`
- Test: `tests/unit/test_conversation_service.py`
- Test: `tests/unit/test_linear_conversation.py`
- Test: `tests/unit/test_dashboard_launcher.py`
- Test: `tests/unit/test_daemon.py`

**Intent:**

Treat `chat -> freeze -> canonical issue -> workspace -> Linear mirror` as a production flow, not just a capability hiding in service code.

**Step 1: Write failing tests for lifecycle integrity**

Add tests that expect:

- repeated `freeze` on the same converged thread to stay idempotent or explicitly refuse duplicate mission creation
- linked Linear thread metadata to survive handoff and daemon touchpoints
- lifecycle evidence to distinguish `Active Context` from `Review Evidence`

**Step 2: Run the targeted tests and confirm failure**

Run:

```bash
UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-.venv-py313}" uv run --python 3.13 pytest tests/unit/test_conversation_service.py tests/unit/test_linear_conversation.py tests/unit/test_dashboard_launcher.py tests/unit/test_daemon.py -q -k 'freeze or linear or handoff'
```

**Step 3: Implement minimal lifecycle hardening**

Add the smallest changes needed so that:

- thread freeze is safe under retry
- linked Linear issues remain bound across launcher/daemon handoff
- mirror updates stay best-effort and do not corrupt local mission state

**Step 4: Re-run targeted tests**

Run the same pytest command and make it pass.

**Step 5: Run the broader self-hosting suite**

Run:

```bash
UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-.venv-py313}" uv run --python 3.13 pytest tests/unit/test_linear_mirror.py tests/unit/test_linear_plan_sync.py tests/unit/test_conversation_service.py tests/unit/test_dashboard_launcher.py tests/unit/test_daemon.py tests/unit/test_linear_conversation.py tests/unit/test_cli_smoke.py -q
```

**Step 6: Verify style and types**

Run:

```bash
UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-.venv-py313}" uv run --python 3.13 ruff check src/spec_orch/services/conversation_service.py src/spec_orch/services/linear_conversation_adapter.py src/spec_orch/dashboard/launcher.py src/spec_orch/services/daemon.py tests/unit/test_conversation_service.py tests/unit/test_linear_conversation.py tests/unit/test_dashboard_launcher.py tests/unit/test_daemon.py
UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-.venv-py313}" uv run --python 3.13 ruff format --check src/spec_orch/services/conversation_service.py src/spec_orch/services/linear_conversation_adapter.py src/spec_orch/dashboard/launcher.py src/spec_orch/services/daemon.py tests/unit/test_conversation_service.py tests/unit/test_linear_conversation.py tests/unit/test_dashboard_launcher.py tests/unit/test_daemon.py
UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-.venv-py313}" uv run --python 3.13 mypy src/spec_orch/services/conversation_service.py src/spec_orch/services/linear_conversation_adapter.py src/spec_orch/dashboard/launcher.py src/spec_orch/services/daemon.py
```

**Step 7: Commit**

```bash
git add src/spec_orch/services/conversation_service.py src/spec_orch/services/linear_conversation_adapter.py src/spec_orch/dashboard/launcher.py src/spec_orch/services/daemon.py tests/unit/test_conversation_service.py tests/unit/test_linear_conversation.py tests/unit/test_dashboard_launcher.py tests/unit/test_daemon.py tests/unit/test_cli_smoke.py
git commit -m "feat: harden chat-to-issue lifecycle"
```

## Task 4: Dogfood Acceptance and Archive Closeout

**Files:**
- Modify: `docs/plans/2026-04-04-self-hosting-dogfood-wave-1-implementation-plan.md`
- Modify: `docs/acceptance-history/index.json`
- Add: `docs/acceptance-history/releases/self-hosting-dogfood-wave-1-2026-04-04/*`

**Intent:**

Close the wave with the hardened acceptance protocol and archive it as a first-class release bundle.

**Step 1: Run canonical acceptance serially**

Run:

```bash
./tests/e2e/issue_start_smoke.sh --full
./tests/e2e/dashboard_ui_acceptance.sh --full
./tests/e2e/mission_start_acceptance.sh --full
./tests/e2e/exploratory_acceptance_smoke.sh --full
./tests/e2e/update_stability_acceptance_status.sh
```

**Step 2: Classify findings**

Classify any failures into:

- `harness_bug`
- `n2n_bug`
- `ux_gap`

Fix `harness_bug` first, rerun, then continue.

**Step 3: Write the release bundle**

Create a new bundle directory under:

```text
docs/acceptance-history/releases/self-hosting-dogfood-wave-1-2026-04-04/
```

Include:

- `summary.md`
- `manifest.json`
- `status.json`
- `source_runs.json`
- `artifacts.json`
- `findings.json`

Update:

- `docs/acceptance-history/index.json`

**Step 4: Answer the 5-subsystem review**

Record:

- weakest subsystem
- why it is weakest
- what the next bottleneck tranche should be

**Step 5: Final verification sweep**

Run:

```bash
UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-.venv-py313}" uv run --python 3.13 ruff check src/ tests/
UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-.venv-py313}" uv run --python 3.13 ruff format --check src/ tests/
UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-.venv-py313}" uv run --python 3.13 mypy src/spec_orch/
```

**Step 6: Commit**

```bash
git add docs/plans/2026-04-04-self-hosting-dogfood-wave-1-implementation-plan.md docs/acceptance-history/index.json docs/acceptance-history/releases/self-hosting-dogfood-wave-1-2026-04-04
git commit -m "docs: archive self-hosting dogfood wave 1"
```

Plan complete and saved to `docs/plans/2026-04-04-self-hosting-dogfood-wave-1-implementation-plan.md`. Two execution options:

1. Subagent-Driven (this session) - I dispatch fresh subagent per task, review between tasks, fast iteration
2. Parallel Session (separate) - Open new session with executing-plans, batch execution with checkpoints

Which approach?
