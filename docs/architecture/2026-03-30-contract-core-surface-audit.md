# Contract Core Surface Audit

## Scope

This audit records the `E7-I5` surface cleanup pass after `contract_core` extraction.

The goal is not to force every shell to import `contract_core`; the goal is to stop shells from owning contract business truth directly.

## Updated Surfaces

- `cli/spec_commands.py`
  - now consumes `contract_core.snapshots`
  - now consumes `contract_core.decisions`
  - now consumes `contract_core.importers`
- `cli/run_commands.py`
  - now consumes `contract_core.snapshots` for spec compliance display
- `cli/evolution_commands.py`
  - now consumes `contract_core.contracts`
- `services/run_controller.py`
  - now consumes `contract_core.snapshots`

## Compatibility Shims

- `domain/task_contract.py`
  - remains as a legacy shim over `contract_core.contracts`
- `services/spec_snapshot_service.py`
  - remains as a legacy shim over `contract_core.snapshots`

These shims stay in place so existing imports do not break while Epic 7 finishes.

## Surfaces Intentionally Not Changed

- `dashboard/*`
  - current dashboard modules do not own contract truth
  - they primarily render runtime, decision, and acceptance state
  - references to `blocking_questions` are decision/supervision concerns, not contract-core concerns
- `services/daemon.py`
  - daemon does not currently own spec snapshot or task contract logic
  - no direct `task_contract` or `spec_snapshot_service` dependency required cleanup in this pass

## Remaining Surface Work

Still deferred inside Epic 7:

- broader dashboard/daemon import normalization once any new contract-facing surfaces appear
- potential future migration of legacy shim call sites still outside CLI/run-controller
- cleanup of historical docs and internal references that still talk about contract behavior as a `services/` concern

## Conclusion

`E7-I5` is complete for the current codebase shape:

- shells no longer define the main contract primitives
- core contract behavior now lives in `contract_core`
- dashboard and daemon were reviewed and intentionally left unchanged because they did not encode contract business truth in this tranche
