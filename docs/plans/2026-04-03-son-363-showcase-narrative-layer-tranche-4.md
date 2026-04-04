# SON-363 Showcase Narrative Layer Tranche 4

**Goal:** Extend showcase from point-in-time summaries into explicit release-to-workspace timeline narrative so operators can see how a workspace's archived journey evolved across release bundles.

**Architecture:** Keep showcase strictly downstream and read-only. This tranche may derive new carriers from existing `docs/acceptance-history` bundles plus the current workbench read models, but it must not add a new persistence layer or mutate archive content.

### Task 1: Lock the release/workspace journey contract in tests

**Files:**
- Modify: `tests/unit/test_showcase_workbench.py`
- Modify: `tests/unit/test_dashboard_package.py`

Add tests that require:

- `release_timeline[]` rows to expose a concise `storyline_headline`
- `workspace_storylines[]` rows to expose `journey_summary`
- `workspace_storylines[]` rows to expose a chronological `release_journey`
- dashboard showcase rendering to consume and display those carriers

Run:

```bash
uv run --python 3.13 pytest tests/unit/test_showcase_workbench.py tests/unit/test_dashboard_package.py -q
```

Expected: `FAIL` because the showcase read model and dashboard surface do not yet expose timeline narrative carriers.

### Task 2: Implement minimal release/workspace timeline narrative

**Files:**
- Modify: `src/spec_orch/services/showcase_workbench.py`
- Modify: `src/spec_orch/dashboard/app.py`

Implement:

- a per-release `storyline_headline` derived from linked workspaces plus source-run compare focus
- a per-workspace `release_journey` derived from linked releases in chronological order
- a per-workspace `journey_summary` that surfaces release-count and latest-release identity
- dashboard showcase cards that render the new storyline and journey carriers

Keep the tranche narrow:

- no new routes
- no new write actions
- no archive schema changes

### Task 3: Run focused verification

Run:

```bash
uv run --python 3.13 pytest tests/unit/test_showcase_workbench.py tests/unit/test_dashboard_package.py -q
uv run --python 3.13 pytest tests/unit/test_dashboard_api.py -q -k showcase
uv run --python 3.13 ruff check src/spec_orch/services/showcase_workbench.py src/spec_orch/dashboard/app.py tests/unit/test_showcase_workbench.py tests/unit/test_dashboard_package.py tests/unit/test_dashboard_api.py
uv run --python 3.13 mypy src/spec_orch/services/showcase_workbench.py
```

Expected: `PASS`

### Task 4: Decide closeout

If the tranche remains showcase-only and no canonical workflow behavior changed, focused verification is sufficient before commit.

If later showcase work in this wave starts touching archive writers, dashboard routing, or mission execution seams, run the full acceptance closeout sequence before landing.
