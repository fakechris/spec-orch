# Tranche A Execution Pack

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn Tranche A into a real execution packet with explicit ownership, order, and verification so engineering can start immediately without reopening sequencing questions.

**Architecture:** Tranche A is the semantic-foundation slice of the 7-epic program. It should establish the shared execution language and read path before any dual-write or runtime-core extraction begins. These issues are intentionally narrow and sequential: shared models first, then read normalizers, then consumer migration.

**Tech Stack:** Python 3.13, dataclasses, pathlib, pytest, current `src/spec_orch` package tree, current issue/mission artifact layout.

---

## 1. Tranche A Scope

Tranche A contains:

1. `E1-I1` `Add shared execution semantic models`
2. `E1-I2` `Add read-side normalizers for issue and mission artifacts`
3. `E1-I3` `Migrate read-side consumers to normalized execution reads`

These three issues are the current execution horizon and are the only ones that should be `Ready` right now.

## 2. Ownership Model

### Primary workstream owner

- `Core Extraction Lead`

This owner is responsible for:

- semantic correctness
- keeping issue and mission paths aligned
- refusing premature writer/cutover work

### Supporting review owner

- `Architecture Review`

This owner is responsible for:

- checking that `Round` does not collapse into `ExecutionAttempt`
- checking that acceptance/supervision semantics do not leak into Tranche A

### Practical assignment rule

Until the team creates a finer assignee split, all three cards should be treated as one tightly coupled execution packet owned by the same workstream.

## 3. Exact Execution Order

Tranche A must run in this order:

1. `SON-281 / E1-I1`
2. `SON-282 / E1-I2`
3. `SON-283 / E1-I3`

No parallelization is recommended inside Tranche A because:

- `E1-I2` depends on the semantic model shape from `E1-I1`
- `E1-I3` depends on the normalized read surface from `E1-I2`

## 4. Issue Package Details

### SON-281 / E1-I1

**Title:** `Add shared execution semantic models`

**Owner:** `Core Extraction Lead`

**Execution Order:** `1 of 3`

**Files expected to change:**

- Create: `src/spec_orch/domain/execution_semantics.py`
- Test: `tests/unit/test_execution_semantics.py`

**Verification commands:**

```bash
pytest tests/unit/test_execution_semantics.py -v
```

**Key checks:**

- enums are narrow and explicit
- nullable fields are intentional, not accidental
- `Round` is not modeled as an `ExecutionAttempt`

### SON-282 / E1-I2

**Title:** `Add read-side normalizers for issue and mission artifacts`

**Owner:** `Core Extraction Lead`

**Execution Order:** `2 of 3`

**Files expected to change:**

- Create: `src/spec_orch/services/execution_semantics_reader.py`
- Test: `tests/unit/test_execution_semantics_reader.py`

**Verification commands:**

```bash
pytest tests/unit/test_execution_semantics_reader.py -v
```

**Key checks:**

- issue workspace normalization works
- mission worker normalization works
- mission round normalization works
- round normalization yields supervision-shaped data, not execution-shaped data

### SON-283 / E1-I3

**Title:** `Migrate read-side consumers to normalized execution reads`

**Owner:** `Core Extraction Lead`

**Execution Order:** `3 of 3`

**Files expected to change:**

- Modify: `src/spec_orch/services/evidence_analyzer.py`
- Modify: `src/spec_orch/services/eval_runner.py`
- Modify: `src/spec_orch/services/context/context_assembler.py`
- Modify: `src/spec_orch/dashboard/control.py`
- Modify: `src/spec_orch/dashboard/missions.py`
- Modify: `src/spec_orch/dashboard/transcript.py`
- Modify: `src/spec_orch/dashboard/surfaces.py`
- Test: `tests/unit/test_context_assembler.py`
- Test: `tests/unit/test_evidence_analyzer.py`
- Test: `tests/unit/test_eval_runner.py`
- Test: `tests/unit/test_dashboard.py`
- Test: `tests/unit/test_dashboard_api.py`

**Verification commands:**

```bash
pytest tests/unit/test_execution_semantics_reader.py \
  tests/unit/test_evidence_analyzer.py \
  tests/unit/test_eval_runner.py \
  tests/unit/test_context_assembler.py \
  tests/unit/test_dashboard.py \
  tests/unit/test_dashboard_api.py -v
```

**Key checks:**

- consumers prefer normalized reads
- legacy fallback still works
- no writer/cutover logic sneaks into this issue

## 5. Stop Conditions

Stop Tranche A and review before moving to Tranche B if:

- the semantic model starts absorbing round decision or acceptance-specific fields
- the reader layer starts inventing canonical writer paths
- consumer migration requires changing runtime ownership

## 6. Definition of Done For Tranche A

Tranche A is complete only when:

- `E1-I1`, `E1-I2`, and `E1-I3` all pass their focused verification
- the normalized read path exists for issue, mission leaf, and mission round artifacts
- at least one real consumer path prefers normalized reads
- Tranche B can begin without reopening semantic debates
