# Fresh Acpx Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Harden the fresh ACPX mission path so it proves scoped edits, stronger verification, stable launch/pickup execution, reliable dashboard startup, runtime-safe templates, and more than one fresh mission variant.

**Architecture:** Keep the existing fresh harness shape, but strengthen the proof contract at each layer. Runtime templates move out of `tests/fixtures`, fresh verification becomes explicit and reusable, packet gate evidence grows a real scope signal, and the smoke runner becomes a long-lived deterministic harness instead of a set of loosely coupled short-lived steps.

**Tech Stack:** Python 3.13, pytest, ruff, mypy, bash smoke harness, existing SpecOrch launcher/round-orchestrator/acceptance services.

### Task 1: Move fresh templates to runtime-safe resources

**Files:**
- Create: `src/spec_orch/resources/fresh_acpx_campaign.json`
- Create: `src/spec_orch/resources/fresh_acpx_mission_request.json`
- Create: `src/spec_orch/services/resource_loader.py`
- Modify: `src/spec_orch/dashboard/launcher.py`
- Modify: `src/spec_orch/services/round_orchestrator.py`
- Modify: `tests/unit/test_dashboard_launcher.py`
- Modify: `tests/unit/test_round_orchestrator.py`
- Modify: `tests/unit/test_acceptance_models.py`

**Step 1: Write failing tests**

- Add launcher tests that do not seed `tests/fixtures`, and expect `_build_fresh_acpx_mission_request()` to succeed from packaged resources.
- Add round orchestrator tests that do not seed `tests/fixtures`, and expect `build_fresh_acpx_post_run_campaign()` to load the runtime resource.

**Step 2: Run focused tests to verify they fail**

Run:
```bash
uv run pytest tests/unit/test_dashboard_launcher.py tests/unit/test_round_orchestrator.py tests/unit/test_acceptance_models.py -q
```

**Step 3: Implement minimal runtime resource loader**

- Add a helper that reads JSON resources from `spec_orch.resources`.
- Update launcher and round orchestrator to use runtime resources by default, while still allowing explicit test override when needed.

**Step 4: Re-run focused tests**

Run:
```bash
uv run pytest tests/unit/test_dashboard_launcher.py tests/unit/test_round_orchestrator.py tests/unit/test_acceptance_models.py -q
```

### Task 2: Strengthen fresh packet verification commands

**Files:**
- Modify: `src/spec_orch/dashboard/launcher.py`
- Create: `src/spec_orch/services/fresh_verification.py`
- Modify: `tests/unit/test_dashboard_launcher.py`
- Create: `tests/unit/test_fresh_verification.py`

**Step 1: Write failing tests**

- Lock that fresh packet verification commands include more than `scaffold_exists`.
- Add tests for stronger checks:
  - file exists
  - TypeScript contract tokens present
  - optional importability/schema-friendly checks exposed in command structure

**Step 2: Run focused tests to verify they fail**

Run:
```bash
uv run pytest tests/unit/test_dashboard_launcher.py tests/unit/test_fresh_verification.py -q
```

**Step 3: Implement reusable fresh verification command builder**

- Extract verification generation into a dedicated service module.
- Emit a richer command map for TS contract scaffolds instead of only one inline `-c` snippet.

**Step 4: Re-run focused tests**

Run:
```bash
uv run pytest tests/unit/test_dashboard_launcher.py tests/unit/test_fresh_verification.py -q
```

### Task 3: Add fresh packet scope proof to gate evidence

**Files:**
- Modify: `src/spec_orch/services/round_orchestrator.py`
- Modify: `src/spec_orch/domain/models.py` (only if needed for a structured scope field)
- Modify: `tests/unit/test_round_orchestrator.py`

**Step 1: Write failing tests**

- Add a test where a packet writes one in-scope file and one out-of-scope file in its workspace.
- Expect `gate_verdicts` to record `mergeable=False`, include a `scope` failure, and expose the out-of-scope file list.

**Step 2: Run focused tests to verify they fail**

Run:
```bash
uv run pytest tests/unit/test_round_orchestrator.py -q
```

**Step 3: Implement scope proof**

- Compute actual realized files under the packet workspace.
- Compare them with `packet.files_in_scope`.
- When out-of-scope files exist:
  - persist them in the gate verdict
  - force `mergeable=False`
  - append `scope` to failed conditions

**Step 4: Re-run focused tests**

Run:
```bash
uv run pytest tests/unit/test_round_orchestrator.py -q
```

### Task 4: Harden launch/pickup into one long-lived fresh harness path

**Files:**
- Modify: `tests/e2e/fresh_acpx_mission_smoke.sh`
- Modify: `src/spec_orch/services/fresh_acpx_e2e.py`
- Modify: `tests/unit/test_fresh_acpx_e2e.py`

**Step 1: Write failing tests**

- Add unit-level helpers around fresh execution orchestration so launch/pickup can be driven in one logical call.
- Add smoke-harness-facing tests that assert the orchestration helper records consistent launch/pickup proof.

**Step 2: Run focused tests to verify they fail**

Run:
```bash
uv run pytest tests/unit/test_fresh_acpx_e2e.py -q
```

**Step 3: Implement unified orchestration helper**

- Collapse launch and pickup into one long-lived Python path inside the smoke harness.
- Ensure `launch_result.json` and `daemon_run.json` reflect the same execution lifecycle.

**Step 4: Re-run focused tests**

Run:
```bash
uv run pytest tests/unit/test_fresh_acpx_e2e.py -q
```

### Task 5: Replace fixed dashboard sleep with readiness polling

**Files:**
- Modify: `tests/e2e/fresh_acpx_mission_smoke.sh`
- Optionally Create: `src/spec_orch/services/dashboard_readiness.py`
- Create/Modify: tests that cover the readiness helper if one is added

**Step 1: Write failing tests or harness assertions**

- Add a helper test if readiness polling is factored into Python.
- Otherwise add shell-side timeout/error-path handling and verify the smoke harness still passes.

**Step 2: Implement readiness polling**

- Wait for the dashboard port or HTTP response.
- On timeout:
  - print `/tmp/spec_orch_fresh_dashboard.log`
  - stop the process
  - fail deterministically

**Step 3: Verify**

Run:
```bash
bash tests/e2e/fresh_acpx_mission_smoke.sh --full
```

### Task 6: Add fresh path variants

**Files:**
- Create: `tests/fixtures/fresh_acpx_mission_request_<variant>.json` (or resource equivalents)
- Modify: `tests/e2e/fresh_acpx_mission_smoke.sh`
- Modify/Create: `tests/unit/test_fresh_acpx_e2e.py`
- Modify docs:
  - `docs/plans/2026-03-28-fresh-acpx-mission-e2e-design.md`
  - `docs/guides/supervised-mission-e2e-playbook.md`

**Step 1: Define at least two additional fresh variants**

- Different packet combination
- Different launcher/approval outcome

**Step 2: Write failing coverage tests**

- Ensure the smoke helper can select a variant
- Ensure reports identify which variant was run

**Step 3: Implement variant support**

- Add variant selector input to the smoke harness
- Thread variant metadata into mission bootstrap and final report

**Step 4: Re-run variant-focused verification**

Run:
```bash
uv run pytest tests/unit/test_fresh_acpx_e2e.py tests/unit/test_dashboard_launcher.py -q
bash tests/e2e/fresh_acpx_mission_smoke.sh --full
```

### Task 7: Full verification and landing prep

**Files:**
- Modify: `task_plan.md`
- Modify: `progress.md`

**Step 1: Run targeted verification**

Run:
```bash
uv run pytest tests/unit/test_dashboard_launcher.py tests/unit/test_fresh_verification.py tests/unit/test_fresh_acpx_e2e.py tests/unit/test_round_orchestrator.py tests/unit/test_playwright_visual_eval.py tests/unit/test_litellm_acceptance_evaluator.py -q
```

**Step 2: Run static verification**

Run:
```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy src/
```

**Step 3: Run full suite**

Run:
```bash
uv run pytest -q
```

**Step 4: Run full fresh smoke**

Run:
```bash
bash tests/e2e/fresh_acpx_mission_smoke.sh --full
```

**Step 5: Commit and open PR**

```bash
git add src/ tests/ docs/ task_plan.md progress.md
git commit -m "feat: harden fresh acpx mission proof"
git push -u origin fresh-acpx-hardening
gh pr create --fill
```
