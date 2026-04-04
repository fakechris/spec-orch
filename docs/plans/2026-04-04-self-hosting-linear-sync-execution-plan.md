# Self-Hosting Linear Sync Execution Plan

> **Purpose:** turn the now-hardened spec-orch runtime into a self-hosting workflow where Linear reflects real program state, plans are mirrored structurally, and conversational intake can complete the path from chat to canonical issue to workspace handoff.

## Goal

Use the already-landed intake, substrate, workbench, hardening, and acceptance/archive systems as baseline. Do **not** redesign them. Add the missing coordination layer that makes Linear a trustworthy control plane for the next self-hosting wave.

## Governance Frame

This plan adopts the `llm_planner_orch` handoff in `docs/plans/2026-04-04-harness-review-checklist-and-context-taxonomy.md`:

- review with the `5-subsystem` checklist:
  - `Instructions`
  - `State`
  - `Verification`
  - `Scope`
  - `Lifecycle`
- improve `bottleneck-first`
- keep retained information split into:
  - `Active Context`
  - `Working State`
  - `Review Evidence`
  - `Archive`
  - `Promoted Learning`

The role of this frame is review discipline and naming. It is not a replacement architecture.

## What Already Exists

- Linear-native conversational intake
- dashboard intake workspace
- canonical issue schema
- intake-to-workspace handoff
- shared operator semantics
- execution/judgment/learning workbenches
- release acceptance archive and `source_run` lineage
- phase-2 hardening for context layering, verification independence, admission control, structural judgment, and learning promotion

## What Is Still Missing

1. Linear does not yet mirror spec-orch runtime truth as a structured contract.
2. Plan/tranche state exists in local docs and runtime artifacts, but not yet as a structured Linear surface.
3. The conversation stack exists, but the full `chat -> canonical issue -> Linear -> workspace handoff` path is not yet treated as a mainline product flow.

## Program Order

1. `Structured Linear mirror contract`
2. `Plan mirroring into Linear`
3. `Chat-to-issue end-to-end`

## Standing Review Questions

Before closing each tranche, answer:

- `Instructions`: are operator and agent instructions coherent and discoverable?
- `State`: can we tell active state from archive and promoted learning?
- `Verification`: are completion claims grounded in explicit checks?
- `Scope`: does the tranche stay inside the declared work boundary?
- `Lifecycle`: is the path from intake to archive and Linear status understandable?

Record the weakest subsystem and make it the next hardening target if it becomes the bottleneck.

## Tranche 1: Structured Linear Mirror Contract

**Goal:** make Linear issue descriptions/comments reflect current spec-orch truth in a structured, parse-safe way.

**Files:**
- Add: `src/spec_orch/services/linear_mirror.py`
- Modify: `src/spec_orch/services/linear_write_back.py`
- Modify: `src/spec_orch/services/linear_intake.py`
- Modify: `src/spec_orch/services/canonical_issue.py`
- Modify: `src/spec_orch/services/intake_handoff.py`
- Add: `tests/unit/test_linear_mirror.py`
- Modify: `tests/unit/test_linear_write_back.py`
- Modify: `tests/unit/test_linear_intake.py`

**Requirements:**
- preserve the current Linear intake parser behavior
- add a structured `SpecOrch Mirror` section that can carry:
  - intake state
  - handoff state
  - workspace id
  - blockers
  - next action
  - plan summary
  - source refs
- let write-back update this section without destroying the core intake document

**Verification:**

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 pytest tests/unit/test_linear_mirror.py tests/unit/test_linear_write_back.py tests/unit/test_linear_intake.py tests/unit/test_canonical_issue.py -q
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 ruff check src/spec_orch/services/linear_mirror.py src/spec_orch/services/linear_write_back.py src/spec_orch/services/linear_intake.py src/spec_orch/services/canonical_issue.py src/spec_orch/services/intake_handoff.py tests/unit/test_linear_mirror.py tests/unit/test_linear_write_back.py tests/unit/test_linear_intake.py tests/unit/test_canonical_issue.py
```

## Tranche 2: Plan Mirroring Into Linear

**Goal:** make the current spec-orch plan/progress visible in Linear in a structured and compact form.

**Files:**
- Add: `src/spec_orch/services/linear_plan_sync.py`
- Modify: `src/spec_orch/services/linear_write_back.py`
- Modify: `src/spec_orch/services/daemon.py`
- Modify: `src/spec_orch/dashboard/launcher.py`
- Add: `tests/unit/test_linear_plan_sync.py`
- Modify: `tests/unit/test_linear_write_back.py`

**Requirements:**
- mirror tranche/phase status into a stable markdown section or comment format
- keep summary compact enough to be readable in Linear
- avoid treating archive or review evidence as active instructions
- support updating previously-created Linear issues so historical status drift can be corrected

**Current implementation direction:**
- add an additive `plan_sync` carrier inside the existing `SpecOrch Mirror` block
- derive it from `plan.json + launch.json + intake_workspace.json`
- keep launcher and daemon on the same sync seam so they do not diverge in how they rewrite Linear

**Verification:**

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 pytest tests/unit/test_linear_plan_sync.py tests/unit/test_linear_mirror.py tests/unit/test_linear_write_back.py tests/unit/test_linear_intake.py tests/unit/test_canonical_issue.py tests/unit/test_dashboard_launcher.py tests/unit/test_daemon.py -q
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 ruff check src/spec_orch/services/linear_plan_sync.py src/spec_orch/services/linear_mirror.py src/spec_orch/services/linear_write_back.py src/spec_orch/services/linear_intake.py src/spec_orch/services/daemon.py src/spec_orch/dashboard/launcher.py tests/unit/test_linear_plan_sync.py tests/unit/test_linear_mirror.py tests/unit/test_linear_write_back.py tests/unit/test_linear_intake.py tests/unit/test_canonical_issue.py tests/unit/test_dashboard_launcher.py tests/unit/test_daemon.py
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 mypy src/spec_orch/services/linear_plan_sync.py src/spec_orch/services/linear_mirror.py src/spec_orch/services/linear_write_back.py src/spec_orch/services/linear_intake.py src/spec_orch/services/daemon.py src/spec_orch/dashboard/launcher.py
```

## Tranche 3: Chat-to-Issue End-to-End

**Goal:** make discussion threads a first-class intake surface that can converge into canonical issue truth and then mirror into Linear/workspace state.

**Files:**
- Modify: `src/spec_orch/services/conversation_service.py`
- Modify: `src/spec_orch/services/linear_conversation_adapter.py`
- Modify: `src/spec_orch/services/linear_write_back.py`
- Modify: `src/spec_orch/dashboard/routes.py`
- Add: `tests/unit/test_conversation_service.py`
- Add: `tests/unit/test_linear_conversation.py`

**Requirements:**
- preserve the current conversation thread model
- add an explicit path from thread convergence to canonical issue + Linear mirror update
- keep verification separate from implementation-originated claims

**Current implementation direction:**
- let `ConversationService.freeze` reuse the existing dashboard intake workspace seam instead of inventing a parallel conversation-only handoff
- if a thread originated from Linear, persist the linked issue in `launch.json` and sync the current mirror immediately
- keep adapter changes thin: cache thread -> issue IDs so reply/write-back does not re-resolve unnecessarily

**Verification:**

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 pytest tests/unit/test_conversation_service.py tests/unit/test_linear_conversation.py tests/unit/test_linear_plan_sync.py tests/unit/test_linear_write_back.py tests/unit/test_dashboard_launcher.py tests/unit/test_cli_smoke.py -q -k 'linear_sync_backfills_bound_linear_issue_descriptions or freeze_command_persists_intake_workspace_and_syncs_linear_issue or reply_uses_cached_linear_issue_id_from_polled_thread or plan_sync or sync_issue_mirror_from_mission or create_linear_issue_for_mission or bind_linear_issue_to_mission'
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 ruff check src/spec_orch/services/conversation_service.py src/spec_orch/services/linear_conversation_adapter.py src/spec_orch/services/linear_plan_sync.py src/spec_orch/services/linear_write_back.py src/spec_orch/dashboard/launcher.py src/spec_orch/cli/mission_commands.py tests/unit/test_conversation_service.py tests/unit/test_linear_conversation.py tests/unit/test_linear_plan_sync.py tests/unit/test_linear_write_back.py tests/unit/test_dashboard_launcher.py tests/unit/test_cli_smoke.py
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 mypy src/spec_orch/services/conversation_service.py src/spec_orch/services/linear_conversation_adapter.py src/spec_orch/services/linear_plan_sync.py src/spec_orch/services/linear_write_back.py src/spec_orch/dashboard/launcher.py src/spec_orch/cli/mission_commands.py
```

## Closeout Rule

For every tranche:

1. run focused tests for the touched seam
2. run `ruff` and `mypy` on touched files
3. if the tranche changes runtime lifecycle or acceptance-relevant behavior, run canonical acceptance and archive a bundle
4. answer the `5-subsystem` review questions
5. name the next bottleneck before starting the next tranche
