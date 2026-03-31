# Epic 7 Contract Core Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extract contract-specific concerns into a visible `contract_core` seam, starting with contract models and spec snapshot/freeze behavior, then use that seam from surfaces.

**Architecture:** Epic 7 should not begin with surface cleanup. The safe first cut is to establish `contract_core/` as the canonical home for contract models and snapshot lifecycle helpers, then delegate `run_controller` and `cli/spec_commands.py` into that seam while keeping compatibility shims in `domain/` and `services/`. This mirrors the earlier `runtime_core` and `decision_core` extraction pattern: move truth first, then thin shells.

**Tech Stack:** Python 3.13, Typer CLI, dataclasses, file-backed JSON artifacts, pytest, ruff.

## Current Progress

- `E7-I1` completed locally: `contract_core/` package exists and owns canonical contract/snapshot primitives.
- `E7-I2` completed locally: snapshot approval / auto-approval / draft creation now sit behind `contract_core.snapshots`, and `run_controller` plus spec CLI consume that seam.
- `E7-I3` completed locally: question/answer/decision recording now sits behind `contract_core.decisions`, and spec CLI no longer mutates snapshot question/decision objects ad hoc.
- `E7-I4` completed locally: spec import registry access now sits behind `contract_core.importers`, and spec CLI import consumes that seam.
- `E7-I5` remains pending: surface cleanup pass across dashboard / daemon / remaining CLI paths.

## First Batch Scope

### E7-I1: Create contract-core package skeleton

**Files:**
- Create: `src/spec_orch/contract_core/__init__.py`
- Create: `src/spec_orch/contract_core/contracts.py`
- Create: `src/spec_orch/contract_core/snapshots.py`
- Create: `src/spec_orch/contract_core/importers/__init__.py`
- Test: `tests/unit/test_contract_core_imports.py`

**Intent:**
- Establish a visible `contract_core` package.
- Move canonical ownership for `TaskContract` and snapshot helpers into `contract_core`.
- Keep compatibility shims in `domain/task_contract.py` and `services/spec_snapshot_service.py`.

### E7-I2: Extract contract snapshot and freeze logic

**Files:**
- Modify: `src/spec_orch/services/run_controller.py`
- Modify: `src/spec_orch/cli/spec_commands.py`
- Modify: `src/spec_orch/services/spec_snapshot_service.py`
- Test: `tests/unit/test_contract_core_snapshots.py`
- Test: `tests/unit/test_spec_snapshot.py`
- Test: `tests/unit/test_planner_and_spec_cli.py`

**Intent:**
- Put snapshot approval / auto-approval / draft creation helpers behind `contract_core`.
- Keep behavior stable for issue runs and spec CLI.

## Deferred To Later Epic 7 Batches

- E7-I5 surface cleanup pass across CLI/daemon/dashboard

## Verification

```bash
uv run --python 3.13 python -m pytest tests/unit/test_contract_core_imports.py tests/unit/test_contract_core_snapshots.py tests/unit/test_contract_core_decisions.py tests/unit/test_contract_core_importers.py tests/unit/test_spec_snapshot.py tests/unit/test_spec_import.py tests/unit/test_task_contract.py tests/unit/test_planner_and_spec_cli.py tests/unit/test_run_controller.py -q
uv run --python 3.13 ruff check src/spec_orch/contract_core src/spec_orch/domain/task_contract.py src/spec_orch/services/spec_snapshot_service.py src/spec_orch/services/run_controller.py src/spec_orch/cli/spec_commands.py tests/unit/test_contract_core_imports.py tests/unit/test_contract_core_snapshots.py tests/unit/test_contract_core_decisions.py tests/unit/test_contract_core_importers.py tests/unit/test_spec_snapshot.py tests/unit/test_spec_import.py tests/unit/test_task_contract.py tests/unit/test_planner_and_spec_cli.py
```
