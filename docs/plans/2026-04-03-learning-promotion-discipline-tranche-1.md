# Learning Promotion Discipline Tranche 1

> **Date:** 2026-04-03
> **Epic:** post-workbench hardening
> **Program slot:** learning promotion discipline

## Goal

Turn Learning Workbench from a visibility-only surface into a governed read model that
shows:

- whether a reviewed finding is eligible for promotion
- which durable targets it actually reached
- which archive releases now carry its lineage

## Scope

This tranche adds:

- a deterministic `learning_promotion_policy` seam
- explicit mission-scoped memory refs for active learning slices
- provenance-aware promotion registry fields and retirement state
- archive lineage joins from release bundles back to workspace learning rows

This tranche does **not** add:

- new learning write actions
- broad auto-promotion
- large new dashboard surface expansion

## Files

- Create: `src/spec_orch/services/learning_promotion_policy.py`
- Modify: `src/spec_orch/services/learning_workbench.py`
- Modify: `src/spec_orch/services/evolution/promotion_registry.py`
- Modify: `src/spec_orch/services/memory/service.py`
- Test: `tests/unit/test_learning_promotion_policy.py`
- Test: `tests/unit/test_learning_workbench.py`
- Test: `tests/unit/test_evolution_promotion_registry.py`
- Test: `tests/unit/test_memory_service.py`
- Test: `tests/unit/test_dashboard_api.py`

## Acceptance

Focused verification:

```bash
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 pytest tests/unit/test_learning_promotion_policy.py tests/unit/test_learning_workbench.py tests/unit/test_evolution_promotion_registry.py tests/unit/test_memory_service.py tests/unit/test_dashboard_api.py -q
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 ruff check src/spec_orch/services/learning_promotion_policy.py src/spec_orch/services/learning_workbench.py src/spec_orch/services/evolution/promotion_registry.py src/spec_orch/services/memory/service.py tests/unit/test_learning_promotion_policy.py tests/unit/test_learning_workbench.py tests/unit/test_evolution_promotion_registry.py tests/unit/test_memory_service.py tests/unit/test_dashboard_api.py
UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 mypy src/spec_orch/services/learning_promotion_policy.py src/spec_orch/services/learning_workbench.py src/spec_orch/services/evolution/promotion_registry.py src/spec_orch/services/memory/service.py
```

Closeout gate:

```bash
./tests/e2e/issue_start_smoke.sh --full
./tests/e2e/dashboard_ui_acceptance.sh --full
./tests/e2e/mission_start_acceptance.sh --full
./tests/e2e/exploratory_acceptance_smoke.sh --full
./tests/e2e/update_stability_acceptance_status.sh
```
