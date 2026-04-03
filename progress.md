# Progress Log

## Session: 2026-03-07

### Phase 1: Requirements & Discovery
- **Status:** complete
- **Started:** 2026-03-07
- Actions taken:
  - Bootstrapped superpowers instructions.
  - Loaded planning and brainstorming skills required by repo instructions.
  - Confirmed the workspace was empty and not initialized as git.
- Files created/modified:
  - `task_plan.md`
  - `findings.md`
  - `progress.md`

### Phase 2: Planning & Structure
- **Status:** complete
- Actions taken:
  - Selected a minimal repository structure centered on docs-first delivery.
  - Chose canonical output paths for architecture and plan documents.
- Files created/modified:
  - `README.md`
  - `.gitignore`

### Phase 3: Documentation Authoring
- **Status:** complete
- Actions taken:
  - Drafted the formal architecture document from the provided SpecOrch v0 concept.
  - Drafted a v1 implementation plan that converts the concept into phased execution tasks.
- Files created/modified:
  - `docs/architecture/spec-orch-system-design-v0.md`
  - `docs/plans/2026-03-07-spec-orch-v1-implementation.md`

### Phase 4: Repository Setup & Verification
- **Status:** complete
- Actions taken:
  - Initialized the repository with `git init -b main`.
  - Reviewed the generated docs and top-level repository files.
  - Confirmed the deliverables are documentation-only plus minimal repository metadata.
- Files created/modified:
  - `.git/`
  - `README.md`
  - `docs/architecture/spec-orch-system-design-v0.md`
  - `docs/plans/2026-03-07-spec-orch-v1-implementation.md`

### Phase 5: Delivery
- **Status:** complete
- Actions taken:
  - Prepared the repository for the initial documentation commit.
  - Evaluated orchestration-layer options for the next design slice.
  - Added an architecture note for orchestration choices and MVP dogfooding.
- Files created/modified:
  - `task_plan.md`
  - `findings.md`
  - `progress.md`
  - `README.md`
  - `docs/architecture/orchestration-plane-options-and-mvp.md`

## Test Results
| Test | Input | Expected | Actual | Status |
|------|-------|----------|--------|--------|
| Workspace inspection | `ls -la` | Confirm repository state | Empty directory confirmed | pass |
| Git state inspection | `git status --short` | Confirm whether git exists | Not a git repository | pass |
| Document review | `sed -n` on generated markdown files | Confirm docs were created and populated | README, system design, and v1 plan reviewed successfully | pass |
| Git initialization | `git init -b main` | Create repository on `main` | Repository initialized successfully | pass |

## Error Log
| Timestamp | Error | Attempt | Resolution |
|-----------|-------|---------|------------|
| 2026-03-07 | `rg --files` in empty directory produced exit code 1 | 1 | Used `ls -la` for workspace inspection |

## Session: 2026-04-01 Operator Workbench Program

### Phase 1: Fresh branch and latest-main baseline
- **Status:** complete
- Actions taken:
  - Verified the current `codexharness` worktree was not the right landing zone.
  - Inspected the repo-wide worktree list.
  - Fetched latest `origin/main`.
  - Confirmed local `main` worktree is dirty and should not be mutated.
  - Created a new clean worktree from latest `origin/main`:
    - `/Users/chris/workspace/spec-orch/.worktrees/operator-workbench-program`
    - branch: `issue/operator-workbench-program`

### Phase 2: Existing-plan reconciliation
- **Status:** complete
- Actions taken:
  - Reviewed current program docs already merged from `llm_planner_orch`.
  - Reviewed current Epic 4 docs, runtime package docs, and Linear-ready mapping.
  - Confirmed current planning baseline is architecture-rich but not yet framed
    around a three-workbench operator product model.

### Phase 3: Three-workbench program docs
- **Status:** complete
- Actions taken:
  - Wrote:
    - `docs/plans/2026-04-01-operator-workbench-program-plan.md`
    - `docs/plans/2026-04-01-operator-workbench-linear-plan.md`
  - Reframed the next wave into:
    - Execution Workbench
    - Judgment Workbench
    - Learning Workbench
  - Converted the plan into 7 epic cards and detailed child issue cards.

### Phase 4: Linear access verification
- **Status:** complete
- Actions taken:
  - Confirmed `LINEAR_TOKEN` exists.
  - Queried Linear successfully.
  - Confirmed team `SON` exists and can be targeted directly.

### Phase 5: Linear epic and issue creation
- **Status:** complete
- Actions taken:
  - Created 7 parent epic issues and 30 child issues in Linear.
  - Used the current `SON` team backlog state and standard parent/child issue
    relationships.
  - Recorded the resulting IDs into:
    - `docs/plans/2026-04-01-operator-workbench-linear-plan.md`

## Session: 2026-04-02 SON-408 Tranche Start

### Phase 0: Shared worktree environment correction
- **Status:** in_progress
- Actions taken:
  - Confirmed the repo requires Python `>=3.11`, while ad hoc shell defaults were
    drifting between system Python and worktree-local `.venv`.
  - Standardized on a shared `uv` environment for all SpecOrch worktrees:
    `/Users/chris/workspace/spec-orch/.venv-py313`
  - Recorded the preferred command prefix for future tranche work:
    `UV_PROJECT_ENVIRONMENT=/Users/chris/workspace/spec-orch/.venv-py313 uv run --python 3.13 ...`
  - Updated `docs/agent-guides/setup.md` so future worktrees do not recreate `.venv`
    per branch.

## Session: 2026-04-02 Conversational Intake Tranche SON-408..411

### Phase 1: SON-408 Linear-native conversational intake
- **Status:** complete
- Actions taken:
  - Added Linear-native intake parsing, readiness evaluation, and write-back wiring.
  - Bridged the new intake sections into the current issue source and Linear update flow.

### Phase 2: SON-409 dashboard intake workspace
- **Status:** complete
- Actions taken:
  - Added a dashboard intake workspace preview/read model to the launcher flow.
  - Persisted intake workspace state under mission operator paths and exposed new launcher APIs.

### Phase 3: SON-410 canonical issue / acceptance schema
- **Status:** complete
- Actions taken:
  - Added canonical intake models and canonical issue construction for Linear and dashboard entry paths.
  - Kept a legacy bridge so current runtime paths can still consume normalized issues.

### Phase 4: SON-411 intake-to-workspace handoff contract
- **Status:** complete
- Actions taken:
  - Added a workspace handoff builder with placeholder execution/judgment/learning seams.
  - Surfaced the handoff payload inside the dashboard intake workspace.

### Phase 5: Tranche closeout and formal acceptance
- **Status:** complete
- Actions taken:
  - Fixed a harness bug where canonical shell runners did not inherit the shared `.venv-py313`.
  - Fixed a status aggregation bug where stale direct fail reports could override newer operator reports.
  - Re-ran canonical acceptance:
    - `issue_start`: pass
    - `dashboard_ui`: pass
    - `mission_start`: pass
    - `exploratory`: fail
  - Archived the tranche as:
    - `docs/acceptance-history/releases/conversational-intake-tranche-son-408-411-2026-04-02/`

### Current program state
- `SON-408` through `SON-411` are complete at the current minimal tranche level.
- The next real blocker is no longer harness/env drift; it is the exploratory acceptance failure on fresh workflow replay evidence.

## 5-Question Reboot Check
| Question | Answer |
|----------|--------|
| Where am I? | Prototype increment planning before the next feature branch |
| Where am I going? | Add explicit human acceptance so the prototype can complete a full local issue lifecycle |
| What's the goal? | Reach a dogfoodable end-to-end local run that can become mergeable after acceptance |
| What have I learned? | The last missing control-plane step is human acceptance, not more builder depth |
| What have I done? | Confirmed the current `main` state, selected the acceptance-flow slice, and refreshed planning files |

## Session: 2026-03-08

### Phase 1: Repository Baseline & Scope
- **Status:** complete
- Actions taken:
  - Re-read the repository state on `main`.
  - Confirmed the builder adapter changes were already merged via cherry-picks.
  - Selected explicit human acceptance as the next minimal increment.
- Files created/modified:
  - `task_plan.md`
  - `findings.md`
  - `progress.md`

### Phase 2: Isolated Workspace & Baseline
- **Status:** complete
- Actions taken:
  - Confirmed `.worktrees/` is ignored by git.
  - Prepared to create a fresh feature worktree from `main`.

## Session: 2026-03-10

### Dogfood-First Development Plan Execution
- **Status:** complete
- **All tasks from the plan have been implemented and verified:**

| Task | Description | Status |
|------|-------------|--------|
| P0-READY | Dogfood 基础设施 (ruff/mypy, fixture JSONs, lint baseline) | complete |
| SPC-P0-1 | README 修复 (第一个 dogfood 循环) | complete |
| SPC-P0-2 | 提取 _finalize_run + compliance 共享模块 | complete |
| SPC-P0-3 | BuilderAdapter/IssueSource Protocol + DI 重构 | complete |
| SPC-P1-1 | codex exec --experimental-json 替换 941 行 app-server | complete |
| SPC-UX-1 | status/explain/diff/cherry-pick CLI 命令 | complete |
| SPC-UX-2 | 富 explain.md (Gate 明细表 + acceptance checklist) | complete |
| SPC-L1 | Linear 客户端 + LinearIssueSource | complete |
| SPC-D1 | daemon 主循环 + spec-orch.toml 配置 | complete |
| SPC-D2 | daemon 完成通知 (macOS + terminal bell) | complete |
| SPC-G1 | Gate 配置化 + gate.policy.yaml + CLI 命令 | complete |
| SPC-W1 | Linear write-back (explain 摘要 + 状态更新) | complete |
| SPC-W2 | GitHub PR 自动创建 + Gate as PR status check | complete |

### New Files Created
- `src/spec_orch/domain/protocols.py` — BuilderAdapter / IssueSource protocols
- `src/spec_orch/domain/compliance.py` — extracted compliance functions
- `src/spec_orch/services/codex_exec_builder_adapter.py` — new simpler builder
- `src/spec_orch/services/fixture_issue_source.py` — fixture-based issue source
- `src/spec_orch/services/linear_client.py` — Linear GraphQL API client
- `src/spec_orch/services/linear_issue_source.py` — Linear-backed issue source
- `src/spec_orch/services/linear_write_back.py` — write summaries back to Linear
- `src/spec_orch/services/daemon.py` — daemon main loop + config
- `src/spec_orch/services/github_pr_service.py` — GitHub PR creation + gate status
- `spec-orch.toml` — daemon configuration
- `gate.policy.yaml` — configurable gate policy
- `fixtures/issues/SPC-*.json` — dogfood issue fixtures
- `tests/unit/test_daemon.py` — daemon unit tests
- `tests/unit/test_gate_service.py` — gate service tests
- `tests/unit/test_linear_write_back.py` — write-back tests
- `tests/unit/test_github_pr_service.py` — github PR service tests

### Verification — Adversarial Rubric & Filing Policy
- **ruff**: All checks passed
- **mypy**: No issues found
- **pytest**: 42/42 tests passed

## Session: 2026-03-10 (PR #1 Review Fixes + EODF Bootstrap)

### PR #1 Code Review Fixes
- **Status:** complete
- Fixed 9 issues raised by chatgpt-codex-connector, gemini-code-assist, devin-ai-integration
- Key fixes: lockfile release on failure, AppleScript injection, GraphQL injection,
  state name→ID resolution, gate re-evaluation, path traversal, prompt injection,
  PR title lookup, _write_report import
- Commit: `c15f487`

### EODF Bootstrap
- **Status:** complete
- Successfully demonstrated semi-auto EODF self-development loop

| EODF Issue | Description | Result |
|------------|-------------|--------|
| SPC-BOOT-1 | Update README for post-PR#1 architecture | mergeable=True |
| SPC-BOOT-2 | Add rerun CLI command | mergeable=True |

#### EODF Loop Verified
1. `run-issue SPC-BOOT-1` → builder skipped, verification passed
2. `review-issue` → verdict=pass
3. `accept-issue` → human_acceptance=True
4. `gate` → mergeable=True, all conditions passed
5. `rerun SPC-BOOT-2` → re-verification passed

#### New Capabilities
- `rerun` CLI command: re-runs verification + gate on existing workspace
- README updated to reflect EODF status and current architecture
- EODF bootstrap fixtures: SPC-BOOT-1, SPC-BOOT-2

### Full-Auto EODF Milestone
- **SPC-BOOT-3**: Codex (`codex exec --json`) 自动实现了 `--version` CLI flag
- Codex 生成了正确的实现代码（importlib.metadata + Typer callback）
- Codex 生成的测试有 mock 路径错误（monkeypatch 模块属性 vs 局部别名），手动修复
- 修复 `--experimental-json` → `--json` flag（codex 0.114.0 稳定 API）

| EODF Issue | 模式 | Builder | Verification | Gate |
|------------|------|---------|--------------|------|
| SPC-BOOT-1 | 半自动 | skipped | all pass | mergeable=True |
| SPC-BOOT-2 | 半自动 | skipped | all pass | mergeable=True |
| SPC-BOOT-3 | **全自动** | **codex exec** | test fix needed | mergeable after fix |

### Verification — Calibration Fixtures & Dogfood Regression
- **ruff**: All checks passed
- **mypy**: No issues found
- **pytest**: 47/47 tests passed

## Session: 2026-03-14

### Self-Evolution Epic (SON-74) — Complete

- **Status:** complete
- **Scope:** AutoHarness-inspired closed-loop improvement — 3 phases, 8 issues

| Phase | Issues | Description | Status |
|-------|--------|-------------|--------|
| 1: Evidence Consumption | SON-75, SON-76, SON-77 | Dynamic gate enforcement, evidence analysis, context injection | ✅ complete |
| 2: Auto-Harness Synthesis | SON-78, SON-79 | LLM-driven compliance rule generation + back-test validation | ✅ complete |
| 3: Recursive Self-Improvement | SON-80, SON-81, SON-82 | Prompt evolution, plan strategy hints, policy distillation | ✅ complete |

### New Capabilities (v0.3.0)
- **EvidenceAnalyzer**: Aggregates run data into pattern summaries
- **HarnessSynthesizer + RuleValidator**: Compliance rules auto-generated from failures
- **PromptEvolver**: Versioned builder prompts with A/B testing
- **PlanStrategyEvolver**: Scoper hints from historical plan outcomes
- **PolicyDistiller**: Recurring tasks as deterministic Python scripts
- **16 new CLI commands** across `evidence`, `harness`, `prompt`, `strategy`, `policy`

### Verification
- **ruff**: All checks passed
- **mypy**: No issues found
- **pytest**: 470+ tests passed (72 new tests for self-evolution)

## Session: 2026-03-25

### Harness Selfhood — Constitutions
- **Status:** complete
- Actions taken:
  - Added a shared `services/constitutions.py` module for supervisor, acceptance evaluator, and evolver constitutions.
  - Rebuilt the supervisor, acceptance evaluator, prompt evolver, and intent evolver system prompts to include explicit constitution sections rather than ad hoc role text only.
  - Added regression tests that lock the constitution text into each role prompt.
- Files created/modified:
  - `src/spec_orch/services/constitutions.py`
  - `src/spec_orch/services/litellm_supervisor_adapter.py`
  - `src/spec_orch/services/acceptance/litellm_acceptance_evaluator.py`
  - `src/spec_orch/services/evolution/prompt_evolver.py`
  - `src/spec_orch/services/evolution/intent_evolver.py`
  - `tests/unit/test_litellm_supervisor_adapter.py`
  - `tests/unit/test_litellm_acceptance_evaluator.py`
  - `tests/unit/test_prompt_evolver.py`
  - `tests/unit/test_muscle_evolvers.py`

### Verification — Harness Constitutions
- targeted prompt tests: `67 passed`

## Session: 2026-03-28

### Dashboard Workflow Replay Quality Pass
- **Status:** in_progress
- Actions taken:
  - Fixed approval-action UI staleness where the page stayed on transient `applied` state after `request_revision` / `ask_followup` because `approvalActionStates` was cleared without rerendering the current mission detail.
  - Re-ran real browser workflow replay for `revision_requested` and `followup_requested`, confirming both approval variants now settle on the final rendered approval state with zero page errors.
  - Ran a consolidated same-version dashboard coverage sweep covering launcher Linear create/bind, root mission selection, mission tab transitions, transcript filtering, acceptance/cost jumps, budget inbox drill-down, visual QA transcript jump, and both approval variants.
  - Updated the dashboard workflow judgment doc to distinguish fully proven `Workflow Replay E2E` dashboard coverage from still-unproven `Fresh Acpx Mission E2E` pipeline freshness.
- Files created/modified:
  - `src/spec_orch/dashboard/app.py`
  - `tests/unit/test_dashboard_package.py`
  - `docs/plans/2026-03-28-dashboard-workflow-acceptance-judgment.md`
  - `task_plan.md`
  - `progress.md`

### Verification — Dashboard Workflow Replay Quality Pass
- `uv run pytest tests/unit/test_dashboard_package.py -q` → `22 passed`
- `uv run mypy src/spec_orch/dashboard/app.py` → pass

## Session: 2026-03-29

### Fresh Acpx Mission E2E Hardening
- **Status:** complete
- Actions taken:
  - Moved fresh mission and campaign templates into runtime-safe packaged resources and added a shared resource loader so fresh smoke no longer depends on `tests/fixtures` at runtime.
  - Strengthened fresh verification from file-exists checks to explicit TypeScript contract/schema command generation, and wired those commands into launcher-generated fresh plans.
  - Added packet scope proof to fresh gate artifacts so mergeability now depends on declared `files_in_scope`, not just whether the worker produced files.
  - Hardened launch/pickup by forcing the smoke path through one foreground lifecycle, replaced dashboard fixed sleeps with readiness polling, and expanded the smoke harness to support named variants and lock-protected runs.
  - Added fresh variants for `default`, `multi_packet`, and `linear_bound`, including real Linear-bound launch proof and post-run workflow replay reports.
  - Fixed a real dashboard regression surfaced by the new Linear-bound replay: acceptance review payloads with string confidences like `"low"` no longer 500 mission detail or acceptance-review routes.
- Files created/modified:
  - `src/spec_orch/resources/__init__.py`
  - `src/spec_orch/resources/fresh_acpx_mission_request.json`
  - `src/spec_orch/resources/fresh_acpx_campaign.json`
  - `src/spec_orch/resources/fresh_acpx_mission_request_multi_packet.json`
  - `src/spec_orch/resources/fresh_acpx_mission_request_linear_bound.json`
  - `src/spec_orch/services/resource_loader.py`
  - `src/spec_orch/services/fresh_verification.py`
  - `src/spec_orch/dashboard/launcher.py`
  - `src/spec_orch/services/fresh_acpx_e2e.py`
  - `src/spec_orch/services/round_orchestrator.py`
  - `src/spec_orch/domain/models.py`
  - `src/spec_orch/services/acceptance/litellm_acceptance_evaluator.py`
  - `tests/e2e/fresh_acpx_mission_smoke.sh`
  - `tests/unit/test_dashboard_api.py`
  - `tests/unit/test_dashboard_launcher.py`
  - `tests/unit/test_fresh_acpx_e2e.py`
  - `tests/unit/test_fresh_verification.py`
  - `tests/unit/test_round_orchestrator.py`
  - `tests/unit/test_litellm_acceptance_evaluator.py`
  - `docs/plans/2026-03-28-fresh-acpx-mission-e2e-design.md`
  - `docs/plans/2026-03-29-fresh-acpx-hardening-implementation.md`
  - `docs/guides/supervised-mission-e2e-playbook.md`

### Verification — Fresh Acpx Mission E2E Hardening
- `uv run pytest tests/unit/test_dashboard_api.py tests/unit/test_round_orchestrator.py tests/unit/test_fresh_acpx_e2e.py tests/unit/test_dashboard_launcher.py tests/unit/test_fresh_verification.py tests/unit/test_litellm_acceptance_evaluator.py -q` → `136 passed`
- `bash tests/e2e/fresh_acpx_mission_smoke.sh --full --variant linear_bound` → pass
- `bash tests/e2e/fresh_acpx_mission_smoke.sh --full --variant multi_packet` → pass
- `bash tests/e2e/fresh_acpx_mission_smoke.sh --full --variant default` → pass
- `uv run ruff check src/spec_orch/dashboard/app.py tests/unit/test_dashboard_package.py` → pass

### Workflow Replay E2E Skill Contract
- **Status:** complete
- Actions taken:
  - Wrote a dedicated design document that freezes the `Workflow Replay E2E` method as a reusable harness contract rather than a one-off dashboard runbook.
  - Documented the six-layer architecture: mission boundary, surface contract, campaign, browser runner, evaluator, and repair loop.
  - Captured the step-by-step runbook, provider portability boundaries, skill-level input/output contract, and the concrete failure modes already seen during dashboard replay.
  - Added a repo-local `.spec_orch/skills/workflow-replay-e2e.yaml` scaffold so the current Skill Runtime/ContextAssembler path can discover a first-class Workflow Replay capability.
  - Added a small sample campaign JSON fixture to make the expected replay payload concrete for future skill implementation.
- Files created/modified:
  - `.spec_orch/skills/workflow-replay-e2e.yaml`
  - `docs/plans/2026-03-28-workflow-replay-e2e-skill-contract.md`
  - `tests/fixtures/workflow_replay_skill_contract_sample.json`
  - `task_plan.md`
  - `progress.md`

### Verification — Workflow Replay E2E Skill Contract
- `uv run pytest tests/unit/test_skill_format.py -q` → `14 passed`
- YAML scaffold parse check → pass

### Fresh Acpx Mission E2E First-Path Plan
- **Status:** complete
- Actions taken:
  - Wrote the first implementation plan for `Fresh Acpx Mission E2E`, explicitly separating fresh execution proof from replay-only dashboard proof.
  - Defined the first artifact contract, proof checkpoints, fixture needs, bootstrap helper requirements, and the first local smoke-script path.
  - Kept the scope narrow: one mission, one wave, one first ACPX execution path, followed by post-run workflow replay.
- Files created/modified:
  - `docs/plans/2026-03-28-fresh-acpx-mission-e2e-implementation.md`
  - `task_plan.md`
  - `progress.md`

### Acceptance Harness Phase 2 — Adversarial Rubric & Filing Policy
- **Status:** complete
- Actions taken:
  - Added mode-aware adversarial rubric text to the acceptance prompt so feature-scoped, impact-sweep, and exploratory runs now have explicit evaluator stance rather than only route budgets.
  - Added filing-policy guidance to the prompt so the evaluator is told when to auto-file, when to defer, and how to downgrade confidence when coverage is incomplete.
  - Hardened `LinearAcceptanceFiler` so auto-filing now respects `coverage_status`, campaign filing policy, and route scope.
  - Added skip reasons for held or out-of-scope proposals so the dashboard and artifacts can explain why an issue was not auto-filed.
- Files created/modified:
  - `src/spec_orch/services/acceptance/prompt_composer.py`
  - `src/spec_orch/services/acceptance/linear_filing.py`
  - `tests/unit/test_acceptance_prompt_composer.py`
  - `tests/unit/test_acceptance_linear_filing.py`
  - `task_plan.md`
  - `progress.md`

### Verification
- **pytest**: targeted acceptance/prompt/filing/orchestrator suite passed (`35 passed`)

## Session: 2026-03-29

### Dashboard Workflow Acceptance Quality Pass
- **Status:** in_progress
- Actions taken:
  - Reproduced the approval replay failure and traced it to malformed helper-generated `onclick` attributes that embedded `safeJsArg(...)` inside double-quoted HTML attributes.
  - Added a static regression test that forces helper buttons using `safeJsArg(...)` to use single-quoted handlers.
  - Repaired the helper buttons and reran real browser replay until `approve` reached the dashboard approval endpoint and the approval state changed to `applied`.
  - Re-ran launcher workflow replay to verify real browser mutations for `Create Draft`, `Approve & Plan`, and `Launch Mission`.
  - Updated the workflow-acceptance judgment document to distinguish proven `Workflow Replay E2E` coverage from still-unproven `Fresh Acpx Mission E2E` coverage.
- Files created/modified:
  - `src/spec_orch/dashboard_assets/static/operator-console.js`
  - `tests/unit/test_dashboard_package.py`
  - `docs/plans/2026-03-28-dashboard-workflow-acceptance-judgment.md`
  - `task_plan.md`
  - `progress.md`

### Verification — Dashboard Workflow Quality Pass
- **pytest**: dashboard package suite passed (`16 passed`)
- **real workflow replay**:
  - launcher create draft / approve plan replay passed
  - launcher launch replay passed
  - approval action replay passed
- **coverage judgment**:
  - core non-destructive workflow navigation: `13/13`
  - broader dashboard capability coverage: `17/22` (intermediate checkpoint) -> final workflow replay sweep: `25/25`
- **ruff**: targeted acceptance/orchestrator checks passed
- **mypy**: no issues found in touched acceptance/orchestrator files

### Acceptance Harness Phase 2 — Route Planning & Interaction Flows
- **Status:** complete
- Actions taken:
  - Added mode-aware acceptance coverage budgets to `AcceptanceCampaign`, including required interactions and route-budget semantics.
  - Reordered acceptance orchestration so campaigns are built before browser evidence collection and now drive which routes are sampled.
  - Added per-route interaction plans and wired Playwright evidence capture to execute simple `click_text` sweeps before screenshotting.
  - Persisted interaction traces into `browser_evidence.json` and surfaced the richer campaign payload through the acceptance prompt stack.
- Files created/modified:
  - `src/spec_orch/domain/models.py`
  - `src/spec_orch/services/acceptance/browser_evidence.py`
  - `src/spec_orch/services/acceptance/prompt_composer.py`
  - `src/spec_orch/services/visual/playwright_visual_eval.py`
  - `src/spec_orch/services/round_orchestrator.py`
  - `tests/unit/test_acceptance_models.py`
  - `tests/unit/test_acceptance_prompt_composer.py`
  - `tests/unit/test_browser_evidence.py`
  - `tests/unit/test_playwright_visual_eval.py`
  - `tests/unit/test_round_orchestrator.py`

### Verification
- **ruff**: targeted checks passed
- **mypy**: no issues found in touched acceptance/orchestrator files
- **pytest**: 1505/1505 tests passed

### Acceptance Harness Phase 2 — Calibration Fixtures & Dogfood Regression
- **Status:** complete
- Actions taken:
  - Added fixed acceptance fixtures for a feature-scoped launcher regression, an exploratory UX hold case, and a sanitized operator-console dogfood run spanning three rounds.
  - Added regression tests that round-trip acceptance review payloads through the domain model and assert policy-aware Linear filing decisions stay stable.
  - Added a dashboard-surface regression that materializes the dogfood fixture into `acceptance_review.json` artifacts and verifies mission-level review summaries remain numerically correct.
- Files created/modified:
  - `tests/fixtures/acceptance/feature_scoped_launcher_regression.json`
  - `tests/fixtures/acceptance/exploratory_dashboard_ux_hold.json`
  - `tests/fixtures/acceptance/dogfood_dashboard_regression.json`
  - `tests/unit/test_acceptance_calibration_suite.py`
  - `task_plan.md`
  - `progress.md`

### Verification
- **pytest**: acceptance calibration + filing + dashboard suite passed (`77 passed`)
- **ruff**: calibration suite checks passed

## Session: 2026-03-27

### Phase: yoyo-evolve harness analysis
- **Status:** complete
- Actions taken:
  - Collected primary source material from `yologdev/yoyo-evolve`:
    - `README.md`
    - `IDENTITY.md`
    - `PERSONALITY.md`
    - `JOURNAL.md`
    - `CLAUDE.md`
    - `CLAUDE_CODE_GAP.md`
    - `memory/*`
    - `scripts/evolve.sh`, `social.sh`, `yoyo_context.sh`
    - `docs/src/*`
  - Logged comparison findings into planning files.
  - Wrote a dedicated roadmap/design document mapping the comparison into concrete SpecOrch phases and explicit Linear epics.
  - Normalized `SON-234` into a real operator-console epic and attached `SON-235..241` as child issues.
  - Created new roadmap epics and child issues:
    - `SON-242` + `SON-245..248` for adversarial/exploratory acceptance
    - `SON-243` + `SON-249..252` for selfhood, constitutions, and memory synthesis
    - `SON-244` + `SON-253..256` for operator feedback and bounded social learning
- Files created/modified:
  - `task_plan.md`
  - `findings.md`
  - `progress.md`
  - `docs/plans/2026-03-28-spec-orch-vs-yoyo-evolve-roadmap.md`
  - `docs/plans/roadmap.md`

## Session: 2026-03-28

### Acceptance Prompt Architecture
- **Status:** complete
- Actions taken:
  - Ran a real dogfood acceptance pass against the operator console dashboard.
  - Confirmed that the current evaluator can produce browser evidence and independent findings, but still over-inherits implementation framing and route constraints.
  - Designed a new mode-based prompt architecture for acceptance evaluation with three explicit modes:
    - feature-scoped verification
    - impact-sweep verification
    - exploratory user-perspective acceptance
  - Defined the prompt stack, coverage semantics, filing policy by mode, and the next implementation order.
- Files created/modified:
  - `docs/plans/2026-03-28-acceptance-prompt-architecture.md`
  - `task_plan.md`
  - `progress.md`

### Acceptance Prompt Architecture Implementation
- **Status:** complete
- Actions taken:
  - Added `AcceptanceMode` and `AcceptanceCampaign` to the acceptance domain model.
  - Extended `AcceptanceReviewResult` with explicit coverage fields, campaign metadata, and recommended next-step semantics.
  - Added `prompt_composer.py` so acceptance prompts are mode-aware instead of one generic JSON dump.
  - Wired `RoundOrchestrator` to build a per-round acceptance campaign from mission criteria, browser evidence, review routes, and `SPEC_ORCH_ACCEPTANCE_MODE`.
  - Updated the LiteLLM acceptance evaluator to consume campaigns and backfill mode/coverage defaults into structured review results.
  - Surfaced mode/coverage/untested-routes/next-step data through the dashboard acceptance API and Acceptance panel.
- Files created/modified:
  - `src/spec_orch/domain/models.py`
  - `src/spec_orch/domain/protocols.py`
  - `src/spec_orch/services/acceptance/prompt_composer.py`
  - `src/spec_orch/services/acceptance/litellm_acceptance_evaluator.py`
  - `src/spec_orch/services/round_orchestrator.py`
  - `src/spec_orch/dashboard_assets/static/operator-console.js`
  - `tests/unit/test_acceptance_models.py`
  - `tests/unit/test_acceptance_protocols.py`
  - `tests/unit/test_acceptance_prompt_composer.py`
  - `tests/unit/test_litellm_acceptance_evaluator.py`
  - `tests/unit/test_round_orchestrator.py`
  - `tests/unit/test_dashboard_api.py`
  - `tests/unit/test_dashboard_package.py`

### Acceptance Taxonomy and Epic Alignment
- **Status:** complete
- Actions taken:
  - Formalized acceptance as a four-layer stack:
    - Verification Acceptance
    - Workflow Acceptance
    - Exploratory Acceptance
    - Human Acceptance
  - Wrote a dedicated taxonomy document so “acceptance” no longer ambiguously mixes strict verification, workflow dogfooding, and user-perspective critique.
  - Realigned the roadmap so:
    - `SON-242` is explicitly the Verification Acceptance epic
    - Workflow Acceptance becomes its own required future epic
    - Exploratory Acceptance becomes its own required future epic
    - `SON-244` is narrowed to Human Acceptance and Feedback Loop rather than treated as the immediate next implementation target
  - Updated the yoyo-roadmap document to reflect the new acceptance-layer interpretation and execution order.
- Files created/modified:
  - `docs/plans/2026-03-28-acceptance-taxonomy-and-epics.md`
  - `docs/plans/roadmap.md`
  - `docs/plans/2026-03-28-spec-orch-vs-yoyo-evolve-roadmap.md`
  - `task_plan.md`
  - `progress.md`

### Workflow Automation Semantics for Dashboard Operator Targets
- **Status:** complete
- Actions taken:
  - Added stable automation-target semantics for dashboard mission cards so workflow acceptance can select missions without ambiguous text matching.
  - Added stable automation-target semantics for mission tabs so workflow acceptance can switch surfaces without colliding with repeated visible headings like `Transcript`.
  - Added stable automation-target semantics for approval actions so workflow acceptance can invoke approval decisions without Playwright strict-mode collisions on duplicate `Approve` labels.
  - Locked these semantics with new static package tests before implementation, then re-ran the full dashboard unit suite.
- Files created/modified:
  - `src/spec_orch/dashboard/app.py`
  - `src/spec_orch/dashboard_assets/static/operator-console.js`
  - `tests/unit/test_dashboard_package.py`
  - `task_plan.md`
  - `progress.md`

### Operator Console and Mission Launcher Consolidation
- **Status:** complete
- Actions taken:
  - Promoted the dashboard into a real operator console with mission detail, transcript, approval queue, visual QA, and costs surfaces.
  - Added a dashboard-first mission launcher so operators can create, approve, plan, bind, and launch a mission without editing files or manually touching Linear descriptions.
  - Tightened left-rail work-mode semantics, mission ordering, and launcher feedback so newly launched missions are discoverable and startup UX is less confusing.
- Files created/modified:
  - `src/spec_orch/dashboard/launcher.py`
  - `src/spec_orch/dashboard/app.py`
  - `src/spec_orch/dashboard/missions.py`
  - `src/spec_orch/dashboard/routes.py`
  - `src/spec_orch/dashboard_assets/static/operator-console.css`
  - `docs/guides/operator-console.md`
  - `docs/guides/supervised-mission-e2e-playbook.md`
  - `spec-orch.toml`

### Acceptance Evaluator Implementation
- **Status:** complete
- Actions taken:
  - Added acceptance domain models and adapter protocol seams.
  - Added browser evidence collection for acceptance review.
  - Added LiteLLM-backed independent acceptance evaluator with safe parse fallback.
  - Persisted `acceptance_review.json` after supervised rounds and added policy-gated Linear filing.
  - Added dashboard Acceptance surface and acceptance summary surfacing in mission detail/context rail.
  - Wired acceptance evaluator config through daemon startup, config docs, and supervised mission dogfood samples.
- Files created/modified:
  - `src/spec_orch/services/acceptance/browser_evidence.py`
  - `src/spec_orch/services/acceptance/litellm_acceptance_evaluator.py`
  - `src/spec_orch/services/acceptance/linear_filing.py`
  - `src/spec_orch/services/round_orchestrator.py`
  - `src/spec_orch/services/daemon.py`
  - `src/spec_orch/domain/models.py`
  - `src/spec_orch/domain/protocols.py`
  - `src/spec_orch/dashboard/surfaces.py`
  - `src/spec_orch/dashboard/routes.py`
  - `src/spec_orch/dashboard/app.py`
  - `src/spec_orch/dashboard_assets/static/operator-console.js`
  - `docs/reference/spec-orch-toml.md`
  - `docs/guides/operator-console.md`
  - `docs/guides/supervised-mission-e2e-playbook.md`
  - `tests/e2e/supervised_mission_minimax.sh`
  - Wrote a concrete implementation plan for Playwright evidence capture, separate evaluator LLM review, structured acceptance artifacts, and policy-gated Linear issue filing.
- Files created/modified:
  - `docs/plans/2026-03-27-acceptance-evaluator-playwright-linear.md`
  - `task_plan.md`
  - `progress.md`

## Session: 2026-03-27

### Dashboard Mission Launcher
- **Status:** in progress
- **Goal:** Replace the current file-edit + CLI + manual-Linear mission startup path with a dashboard-first launcher flow.
- Actions taken:
  - Created a new implementation plan for `Dashboard Mission Launcher`.
  - Added a new launcher service module with readiness, draft, approve+plan, Linear create/bind, and launch helpers.
  - Added launcher API routes under `/api/launcher/...`.
  - Added a minimal launcher sidebar to the dashboard so users can create, plan, bind, and launch missions from the UI.
  - Updated the operator-console guide and supervised-mission E2E playbook to make the dashboard-first flow the recommended path.
  - Created a real dogfood mission skeleton at `docs/specs/operator-console-dogfood-smoke/spec.md`.
  - Created the next-phase Linear epic/issues for operator-console depth and dogfood validation (`SON-234` through `SON-241`).
- Files created/modified:
  - `docs/plans/2026-03-27-dashboard-mission-launcher.md`
  - `docs/guides/operator-console.md`
  - `docs/guides/supervised-mission-e2e-playbook.md`
  - `docs/specs/operator-console-dogfood-smoke/spec.md`
  - `src/spec_orch/dashboard/launcher.py`
  - `src/spec_orch/dashboard/app.py`
  - `src/spec_orch/dashboard/api.py`
  - `src/spec_orch/dashboard/routes.py`
  - `src/spec_orch/dashboard/__init__.py`
  - `tests/unit/test_dashboard_launcher.py`
  - `tests/unit/test_dashboard_api.py`
  - `tests/unit/test_dashboard_package.py`
  - `task_plan.md`
  - `progress.md`
- Verification:
  - `pytest tests/unit/test_dashboard_launcher.py -q` passed
  - `pytest tests/unit/test_dashboard_api.py -q -k launcher` passed
  - `pytest tests/unit/test_dashboard_launcher.py tests/unit/test_dashboard_api.py tests/unit/test_dashboard_package.py tests/unit/test_dashboard.py -q` passed
  - `ruff check` for dashboard files/tests passed

### Operator Console Refactor Continuation
- **Status:** in_progress
- Actions taken:
  - Extracted mission, inbox, mission-detail, and lifecycle-state aggregation into `src/spec_orch/dashboard/missions.py`.
  - Kept dashboard route and package exports stable while shrinking the transitional `dashboard/app.py` surface.
  - Preserved approval workspace, transcript inspector, and operator shell behavior while moving aggregation ownership out of the UI shell.
  - Continued operator-console UX work with richer transcript evidence rendering and approval action state feedback.
  - Linked approval action history back into inbox items so triage surfaces the latest operator decision without opening mission detail first.
  - Added explicit `applied` vs `not_applied` approval-action persistence so operator decisions are no longer flattened into a generic `sent` status.
  - Promoted transcript evidence-rendering helpers into `static/operator-console.js`, reducing inline dashboard script weight and creating a stable helper namespace for future UI extraction.
  - Extended approval-action auditability to exception paths with persisted `failed` state.
  - Moved `buildMissionSubtitle`, `renderArtifactLinks`, and `renderRoundContext` into the shared operator-console helper namespace to keep shrinking inline dashboard script ownership.
  - Added backend-derived `approval_state` to mission detail and inbox so operator workflow is no longer inferred purely from raw history rows.
  - Added explicit pending UI state for approval actions and migrated the heavy approval/transcript render functions into `static/operator-console.js`, leaving `app.py` with thin orchestration wrappers.
  - Landed the first complete operator-console foundation pass: approval state semantics are explicit, transcript evidence is inspectable, Inbox promotes approval-needed missions, and dashboard rendering ownership is split across package modules plus shared static helpers.
  - Reframed the remaining work around new first-class surfaces instead of old foundation Todos: Approval Queue productization, Paperclip-grade transcript readability, Visual QA, Costs/Budgets, and continued shell/package cleanup.
  - Added `src/spec_orch/dashboard/surfaces.py` to own Approval Queue, Visual QA, and Costs/Budgets aggregation.
  - Added dedicated dashboard surfaces for Approval Queue, Visual QA, and Costs/Budgets, and wired them into mission tabs plus operator mode switching.
  - Removed duplicated transcript implementation from `app.py`, leaving the package-backed transcript module as the single owner.
  - Deepened the operator feedback loop again: transcript summaries now emit operator-readout copy, Approval Queue exposes age buckets/result summaries/next-pending routing, Visual QA exposes explicit review routes, Costs incidents expose suggested-action routes, and the operator docs/Todo baseline were refreshed to match the current product surface.
  - Added route-aware workbench navigation: approval requests now expose exact round review routes, transcript round-evidence blocks expose review routes, Visual QA and Costs expose transcript-aware follow-through routes, and the dashboard shell now consumes those routes directly instead of treating them as inert links.
  - Added another layer of operator summary metrics: Approval Queue now reports stale/aged/failed-action counts, Visual QA now emits a focus transcript route when blocking rounds map back to packets, and Costs summary now exposes incident counts and remaining budget against the critical threshold.

### Verification
- `uv run --python 3.13 python -m pytest tests/unit/test_dashboard_api.py -q` → `41 passed`
- `uv run --python 3.13 python -m pytest tests/unit/test_dashboard.py tests/unit/test_dashboard_api.py tests/unit/test_dashboard_package.py -q` → `53 passed`
- `uv run --python 3.13 python -m ruff check src/spec_orch/dashboard.py src/spec_orch/dashboard tests/unit/test_dashboard_api.py tests/unit/test_dashboard_package.py pyproject.toml` → passed
- Browser smoke on `http://127.0.0.1:8472` loaded cleanly, websocket status was `live`, and console errors were `0`
- Browser smoke on `http://127.0.0.1:8473` confirmed route-aware buttons switch the shell into the expected mission/tab state and still keep websocket status `live` with console errors `0`
- Browser smoke on `http://127.0.0.1:8474` still loaded cleanly after the summary-metrics pass; websocket status stayed `live` and console errors remained `0`
  - Added a dedicated `docs/guides/operator-console.md` guide and updated service/run docs to point to the operator-console workflow first.
  - Deepened Approval Queue with urgency, wait-time surfacing, batch actions, and persisted batch feedback.
  - Added post-batch mission focus/navigation so approval processing can jump directly into the affected mission.
  - Deepened Visual QA with gallery extraction, blocking-round summaries, and artifact-backed screenshot surfacing.
  - Deepened Costs/Budgets with thresholds from `spec-orch.toml`, incident detection, and Inbox budget alerts.
  - Removed the obsolete inline operator-console helper fallback from `app.py`, leaving the static helper bundle as the single owner for heavy rendering logic.
  - Added transcript emphasis semantics so milestones, decisions, alerts, and bursts surface with clearer reading hierarchy.
- Files created/modified:
  - `src/spec_orch/dashboard/missions.py`
  - `src/spec_orch/dashboard/api.py`
  - `src/spec_orch/dashboard/__init__.py`
  - `src/spec_orch/dashboard/app.py`
  - `src/spec_orch/dashboard/shell.py`
  - `src/spec_orch/dashboard/surfaces.py`
  - `src/spec_orch/dashboard/routes.py`
  - `src/spec_orch/dashboard_assets/static/operator-console.js`
  - `src/spec_orch/dashboard_assets/static/operator-console.css`
  - `tests/unit/test_dashboard_package.py`
  - `tests/unit/test_dashboard_api.py`
  - `task_plan.md`

### Operator Console Depth Pass
- **Status:** complete
- Actions taken:
  - Added transcript jump-target metadata so timeline blocks now expose direct evidence navigation for source logs, round artifacts, and visual assets.
  - Promoted Visual QA into a diff-first surface whenever before/after/diff assets exist, while preserving gallery fallback for simpler runs.
  - Added explicit budget incident guidance and escalation copy, and surfaced that guidance back into Inbox budget alerts.
  - Extracted dashboard control/evolution/run-history helpers into `src/spec_orch/dashboard/control.py`, reducing the amount of non-UI logic still owned by the transitional `app.py`.
  - Tightened the operator-console JS/CSS so transcript evidence links, diff-first visual comparison, and cost incidents read more like operator surfaces and less like payload dumps.
- Files created/modified:
  - `src/spec_orch/dashboard/control.py`
  - `src/spec_orch/dashboard/app.py`
  - `src/spec_orch/dashboard/missions.py`
  - `src/spec_orch/dashboard/surfaces.py`
  - `src/spec_orch/dashboard/transcript.py`
  - `src/spec_orch/dashboard_assets/static/operator-console.js`
  - `src/spec_orch/dashboard_assets/static/operator-console.css`
  - `tests/unit/test_dashboard_api.py`
  - `tests/unit/test_dashboard_package.py`
  - `task_plan.md`
  - `progress.md`
  - `docs/guides/operator-console.md`
  - `docs/plans/2026-03-26-operator-console-next-todos.md`
  - `progress.md`
  - `docs/plans/2026-03-26-operator-console-next-todos.md`
  - `docs/guides/operator-console.md`
  - `docs/agent-guides/services.md`
  - `docs/agent-guides/run-pipeline.md`

### Verification
- **dashboard pytest**: 51/51 passed
- **dashboard ruff**: All checks passed
- **browser smoke**: local dashboard verified for live websocket, Approval Queue, Visual QA, Costs/Budgets, and zero browser-console errors
- `uv run --python 3.13 python -m pytest tests/unit/test_dashboard.py tests/unit/test_dashboard_api.py tests/unit/test_dashboard_package.py -q`
- `uv run --python 3.13 python -m ruff check src/spec_orch/dashboard.py src/spec_orch/dashboard tests/unit/test_dashboard_api.py tests/unit/test_dashboard_package.py pyproject.toml`

### Phase 1: Research Setup
- **Status:** in_progress
- Actions taken:
  - Fetched `origin/main` and created a fresh branch `paperclip-observability-research`.
  - Initialized a new research-oriented `task_plan.md`.
  - Updated `findings.md` with the scope and hypotheses for the Paperclip / agent observability comparison.
- Files created/modified:
  - `task_plan.md`
  - `findings.md`
  - `progress.md`

### Phase 2: Source Collection
- **Status:** in_progress
- Actions taken:
  - Collected current repo metadata for `paperclipai/paperclip`, `ZacharyZhang-NY/AgentCompany`, and `msitarzewski/agency-agents`.
  - Read the current READMEs and extracted architecture / UX claims.
  - Queried repository trees to identify whether observability concepts are first-class objects in code.
  - Read `agentcompanies.io` documentation to position it as a vendor-neutral packaging/spec layer rather than an operator UI reference.
- Files created/modified:

## Session: 2026-03-26

### Operator Console Delivery
- **Status:** in_progress
- Actions taken:
  - Added approval-aware inbox semantics so `ask_human` round decisions surface as first-class approval items.
  - Added transcript timeline block filtering, transcript inspector, and linked evidence paths for round artifacts.
  - Grouped consecutive tool events into `command_burst` timeline blocks to make packet execution easier to read.
  - Surfaced `approval_request` in mission detail and added approval action presets that inject canned guidance back into paused missions.
  - Persisted approval action history so operator interventions are visible in mission detail instead of disappearing into the `/btw` file alone.
  - Exposed structured `details` payloads on transcript blocks so the inspector can show richer evidence than title/body alone.
  - Refactored the dashboard into a package shape with `spec_orch/dashboard/`, a compatibility wrapper, extracted `routes.py`, plus dedicated `transcript.py` and `approvals.py` modules.
  - Synced agent docs to describe the operator-console surfaces and supervised mission observability workflow.
- Files created/modified:
  - `src/spec_orch/dashboard.py`
  - `src/spec_orch/dashboard/__init__.py`
  - `src/spec_orch/dashboard/api.py`
  - `src/spec_orch/dashboard/app.py`
  - `src/spec_orch/dashboard/routes.py`
  - `src/spec_orch/dashboard/transcript.py`
  - `src/spec_orch/dashboard/approvals.py`
  - `src/spec_orch/dashboard_assets/static/operator-console.css`
  - `docs/agent-guides/services.md`
  - `docs/agent-guides/run-pipeline.md`
  - `docs/guides/supervised-mission-e2e-playbook.md`
  - `tests/unit/test_dashboard.py`
  - `tests/unit/test_dashboard_api.py`
  - `tests/unit/test_dashboard_package.py`

### Verification
- Dashboard API/unit verification: `uv run --python 3.13 python -m pytest tests/unit/test_dashboard.py tests/unit/test_dashboard_api.py tests/unit/test_dashboard_package.py -q`
- Dashboard lint verification: `uv run --python 3.13 python -m ruff check src/spec_orch/dashboard.py src/spec_orch/dashboard tests/unit/test_dashboard_api.py tests/unit/test_dashboard_package.py docs/agent-guides/services.md docs/agent-guides/run-pipeline.md docs/guides/supervised-mission-e2e-playbook.md pyproject.toml`
  - `findings.md`
  - `progress.md`

### Phase 3: Design Context and Console Draft
- **Status:** in_progress
- Actions taken:
  - Wrote `.impeccable.md` with persistent design context for the operator console.
  - Synced the same Design Context into `.github/copilot-instructions.md`.
  - Drafted the first dedicated operator console design document focused on Mission Detail and Run Transcript.
- Files created/modified:
  - `.impeccable.md`
  - `.github/copilot-instructions.md`
  - `docs/plans/2026-03-25-operator-console-design.md`
  - `task_plan.md`
  - `progress.md`

### Phase 4: Implementation Planning
- **Status:** in_progress
- Actions taken:
  - Mapped current dashboard endpoints and mission/transcript data sources.
  - Drafted the operator console implementation plan with Mission Detail and Run Transcript as the first two product surfaces.
  - Chose an incremental FastAPI-backed migration instead of a React rewrite.
- Files created/modified:
  - `docs/plans/2026-03-25-operator-console-implementation-plan.md`
  - `task_plan.md`
  - `progress.md`

### Phase 5: Operator Console Foundations
- **Status:** in_progress
- Actions taken:
  - Added the operator workbench shell to the dashboard homepage with persistent mission, transcript, and context panes.
  - Added mission-detail, packet-transcript, and inbox APIs to back the new console.
  - Root-caused and fixed the dashboard WebSocket `403` issue caused by a deferred `WebSocket` annotation being misread as a query parameter.
  - Added `/favicon.ico` handling so browser dogfooding no longer produces avoidable console noise.
  - Hardened transcript handling so missing telemetry returns an empty payload instead of a `404`.
  - Added transcript timeline blocks and round evidence blocks for supervisor decisions and visual findings.
  - Added inbox scaffolding and then promoted `ask_human` rounds into first-class `approval` items instead of treating them as generic pauses.
  - Added transcript block-count summaries and a filter bar so operators can narrow the timeline by evidence type.
  - Re-ran local browser dogfood and confirmed the dashboard loads cleanly with a live WebSocket connection and zero console errors.
  - Added transcript block source/artifact paths and a transcript inspector section in the context rail for selected evidence.
  - Added `approval_request` to mission detail and surfaced an approval workspace in the context rail with the current blocking question and intervention entry points.
  - Created a `spec_orch.dashboard` package with `app.py`, `api.py`, and package exports so the dashboard now has a modular import surface instead of only a top-level module.
- Files created/modified:
  - `src/spec_orch/dashboard.py`
  - `src/spec_orch/dashboard_assets/static/operator-console.css`
  - `src/spec_orch/dashboard_assets/static/operator-console.js`
  - `tests/unit/test_dashboard.py`
  - `tests/unit/test_dashboard_api.py`
  - `task_plan.md`
  - `progress.md`

## Test Results
| Test | Input | Expected | Actual | Status |
|------|-------|----------|--------|--------|
| Dashboard API slice | `uv run --python 3.13 python -m pytest tests/unit/test_dashboard_api.py -q` | Inbox, transcript, and mission-detail API tests pass | `27 passed` | pass |
| Dashboard shell slice | `uv run --python 3.13 python -m pytest tests/unit/test_dashboard.py tests/unit/test_dashboard_api.py -q` | Dashboard UI/API regression suite stays green | `29 passed` | pass |
| Dashboard lint | `uv run --python 3.13 python -m ruff check src/spec_orch/dashboard.py tests/unit/test_dashboard_api.py pyproject.toml` | Dashboard files lint cleanly | `All checks passed` | pass |

## Session: 2026-03-28

### Phase 24: Dashboard Workflow Quality Replay
- **Status:** in_progress
- Actions taken:
  - Fixed a real workflow dogfood defect where the dashboard root route emitted `Unexpected end of input` because inline `selectMission(...)` handlers were rendered with broken quote nesting.
  - Hardened acceptance finding normalization so replay output no longer preserves empty-shell findings or issue proposals without supporting evidence.
  - Added a stable `mission-detail-ready` automation target and switched workflow replay to wait on that readiness signal instead of brittle tab-state inference.
  - Expanded workflow replay coverage to include launcher readiness refresh, all four top-level operator modes, and the core mission-detail tab sweep (`Overview`, `Transcript`, `Approvals`, `Visual QA`, `Acceptance`, `Costs`).
  - Re-ran real browser-based workflow acceptance replay against a live dashboard and produced a clean pass with complete coverage and zero findings:
    - `docs/specs/operator-console-dogfood-smoke/operator/workflow-acceptance-quality/20260328T233446Z/acceptance_review.json`
    - `docs/specs/operator-console-dogfood-smoke/operator/workflow-acceptance-quality/20260328T233446Z/browser_evidence.json`
  - Wrote a judgment document that separates proven capabilities, unproven capabilities, and next validation targets before opening a PR.
- Files created/modified:
  - `src/spec_orch/dashboard/app.py`
  - `src/spec_orch/services/acceptance/litellm_acceptance_evaluator.py`
  - `src/spec_orch/services/round_orchestrator.py`
  - `tests/unit/test_dashboard_package.py`
  - `tests/unit/test_litellm_acceptance_evaluator.py`
  - `tests/unit/test_round_orchestrator.py`
  - `docs/plans/2026-03-28-dashboard-workflow-acceptance-judgment.md`
  - `task_plan.md`
  - `progress.md`

### Phase 23: Workflow Acceptance Epic
- **Status:** complete
- Actions taken:
  - Added stable dashboard automation semantics for workflow-critical controls: launcher entry, operator modes, mission cards, mission tabs, launcher actions, approval actions, and explicit active-state markers.
  - Added `AcceptanceMode.WORKFLOW` plus workflow-specific prompt guidance so acceptance reviews can judge blocked operator flows as first-class failures rather than generic exploratory critique.
  - Extended Playwright interaction execution with selector-based actions and used those selectors to build workflow campaign steps in `RoundOrchestrator`.
  - Added workflow assertions and coverage contracts for launcher-to-mission-control handoffs, including transcript/approvals tab transitions and actionable operator-surface reachability.
  - Added `workflow_dashboard_repair_loop` calibration fixture and regression coverage so broken workflow findings can be replayed and auto-file behavior stays stable.
- Files created/modified:
  - `src/spec_orch/dashboard/app.py`
  - `src/spec_orch/dashboard_assets/static/operator-console.js`
  - `src/spec_orch/domain/models.py`
  - `src/spec_orch/services/acceptance/prompt_composer.py`
  - `src/spec_orch/services/round_orchestrator.py`
  - `src/spec_orch/services/visual/playwright_visual_eval.py`
  - `tests/fixtures/acceptance/workflow_dashboard_repair_loop.json`
  - `tests/unit/test_acceptance_calibration_suite.py`
  - `tests/unit/test_acceptance_models.py`
  - `tests/unit/test_acceptance_prompt_composer.py`
  - `tests/unit/test_dashboard_package.py`
  - `tests/unit/test_playwright_visual_eval.py`
  - `tests/unit/test_round_orchestrator.py`
  - `task_plan.md`
  - `progress.md`

### Phase 24: Dashboard Workflow Quality Replay and Judgment
- **Status:** in_progress
- Actions taken:
  - Fixed a real helper-bundle bug where `renderInternalRouteButton()` existed but was not exported, which had broken cold-load context-rail rendering during replay.
  - Proved a deeper root-based workflow replay against live dashboard `:8485` covering packet selection, transcript filter switching, transcript-block activation, and an internal acceptance-review jump from the context rail.
  - Added stable automation semantics for secondary mission actions (`Discuss` / `Refresh`) and replayed both successfully through the live dashboard.
  - Added Linear token fallback support (`LINEAR_TOKEN` / `LINEAR_API_TOKEN`) so launcher readiness and real Linear browser mutations no longer depend on a single env name.
  - Proved launcher `Create Linear Issue` and `Bind Existing Issue` through real browser replay, with `workflow-launcher-mutation-smoke/operator/launch.json` recording the created/bound issue.
  - Proved a second context-rail route variant (`Open cost review`) through real browser replay.
  - Updated the workflow judgment doc to distinguish proven `Workflow Replay E2E` coverage from still-unproven `Fresh Acpx Mission E2E`, raising conservative broader dashboard capability coverage to `20/22`.
- Files created/modified:
  - `src/spec_orch/dashboard/app.py`
  - `src/spec_orch/dashboard/launcher.py`
  - `src/spec_orch/dashboard_assets/static/operator-console.js`
  - `src/spec_orch/services/linear_client.py`
  - `tests/unit/test_dashboard_package.py`
  - `tests/unit/test_dashboard_launcher.py`
  - `tests/unit/test_linear_client.py`
  - `docs/plans/2026-03-28-dashboard-workflow-acceptance-judgment.md`
  - `task_plan.md`
  - `progress.md`

### Phase 20: Active Memory Synthesis and Evolution Journal
- **Status:** in_progress
- Actions taken:
  - Added red tests for three selfhood seams: active learning synthesis in MemoryService, role-scoped learning injection in ContextAssembler, and granular evolution journal writes in EvolutionTrigger.
  - Added new learning fields to `LearningContext` for `active_self_learnings`, `active_delivery_learnings`, `active_feedback_learnings`, and `recent_evolution_journal`.
  - Extended node context specs so supervisor/reviewer consume delivery-feedback slices while evolvers consume self learnings and recent journal entries.
  - Added `record_evolution_journal()` to MemoryRecorder/MemoryService and started mirroring evolution lifecycle stages into episodic memory.
  - Added active-memory synthesis in `MemoryDistiller` and `MemoryService`, plus post-run derivation hooks for `self`, `delivery`, and `feedback` slices.
  - Added granular `evolution_journal.jsonl` emission from `EvolutionTrigger` for observe/propose/validate/promote/error stages.
- Files created/modified:
  - `src/spec_orch/domain/context.py`
  - `src/spec_orch/services/context/context_assembler.py`
  - `src/spec_orch/services/context/node_context_registry.py`
  - `src/spec_orch/services/memory/distiller.py`
  - `src/spec_orch/services/memory/recorder.py`
  - `src/spec_orch/services/memory/service.py`
  - `src/spec_orch/services/evolution/evolution_trigger.py`
  - `tests/unit/test_context_assembler.py`
  - `tests/unit/test_evolution_journal.py`
  - `tests/unit/test_memory_service.py`
  - `task_plan.md`
  - `progress.md`

## 5-Question Reboot Check
| Question | Answer |
|----------|--------|
| Where am I? | Midway through the operator-console implementation slice on `paperclip-observability-research` |
| Where am I going? | From basic shell + APIs toward richer inbox actions, deeper transcript UX, and eventual dashboard modularization |
| What's the goal? | Turn the current dashboard into a Paperclip-like operator console without rewriting the whole frontend stack |
| What have I learned? | The system already has enough artifacts for a strong control plane; the missing layer is productized object surfaces and intervention UX |
| What have I done? | Landed the workbench shell, mission/transcript APIs, transcript evidence blocks, WebSocket hardening, and approval-aware inbox triage |
  - Chose an incremental implementation strategy: keep FastAPI, split the dashboard into a package, and build a workbench-style operator console on top.
  - Wrote a task-by-task implementation plan for Mission Detail and Run Transcript.
- Files created/modified:
  - `docs/plans/2026-03-25-operator-console-implementation-plan.md`
  - `findings.md`
  - `progress.md`

### Phase 5: Dashboard Foundations
- **Status:** in_progress
- Actions taken:
  - Added stable static asset entrypoints for the operator console shell and mounted them at `/static`.
  - Added a new mission detail API projection at `/api/missions/{mission_id}/detail`.
  - Added a new packet transcript API projection at `/api/missions/{mission_id}/packets/{packet_id}/transcript`.
  - Verified dashboard-related tests and lint after the changes.
- Files created/modified:
  - `src/spec_orch/dashboard.py`
  - `src/spec_orch/dashboard_assets/static/operator-console.css`
  - `src/spec_orch/dashboard_assets/static/operator-console.js`
  - `tests/unit/test_dashboard_api.py`
  - `pyproject.toml`
