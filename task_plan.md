# Task Plan

## Goal
- Research Paperclip and adjacent agent-company/operator-console projects in detail.
- Compare their observability, UI, and operator experience to SpecOrch's current supervised mission system.
- Produce concrete recommendations for how SpecOrch can reach a comparable level of usability and visibility.

## Phases
| Phase | Status | Notes |
|------|--------|-------|
| 1. Baseline and planning | complete | Created research plan, branched from latest main, defined comparison dimensions |
| 2. Source collection | complete | Gathered Paperclip, agentcompanies.io, AgentCompany, and agency-agents primary sources |
| 3. Comparative analysis | complete | Compared product model, observability surfaces, UX patterns, and architecture choices |
| 4. SpecOrch implications | complete | Converted research into operator-console design principles, workbench IA, and implementation slices |
| 5. Operator console foundation | complete | Mission detail shell, transcript timeline blocks, websocket hardening, inbox scaffolding, approval-aware inbox semantics, approval history-linked inbox items, transcript filter-bar depth, transcript inspector scaffolding, approval workspace surfacing, explicit approval state feedback, richer evidence rendering, static helper extraction, and dashboard package refactor foundation are all in place |
| 6. Operator console next-slice planning | complete | Rebased the Todo list around what is actually left, then shipped batchable Approval Queue with mission-focus navigation, screenshot/gallery-first Visual QA surfacing, threshold-aware Costs/Budgets incidents, transcript emphasis layering, continued shell cleanup, and a dedicated operator-console guide |
| 7. Operator console depth pass | complete | Added transcript jump targets and stronger evidence reading, promoted Visual QA to diff-first when comparison artifacts exist, added operator guidance to budget incidents and Inbox alerts, and extracted control/evolution helpers out of the transitional app shell |
| 8. Operator feedback loop refinement | complete | Added operator-readout transcript summaries, approval age buckets and result summaries, next-pending mission routing after batch actions, explicit mission/round review routes for Visual QA, suggested-action routes for budget incidents, and refreshed the operator-console roadmap/docs to match the current UX baseline |
| 9. Workbench route consumption pass | complete | Added exact approval round review routes, transcript/visual/cost packet review routes, surfaced them through the dashboard API, taught the workbench shell to consume mission/tab/packet routes directly, and verified the new internal navigation in-browser |
| 10. Operator summary metrics pass | complete | Added stale/aged/failed approval counts, summary-level visual focus transcript routing, remaining-budget and incident-count cost metrics, and refreshed the operator docs/Todo baseline so the next remaining work is only deeper ergonomics rather than missing control-plane data |
| 11. Dashboard Mission Launcher | complete | Dashboard-first mission setup now exists: readiness checks, draft creation, approve+plan, Linear create/bind, launch actions, clearer mode semantics, and mission-list relevance sorting are all in place |
| 12. Acceptance evaluator implementation | complete | Added acceptance domain models, browser evidence collection, LiteLLM evaluator, policy-gated Linear filing, dashboard acceptance surface, and daemon/config/docs/e2e wiring for independent acceptance review |
| 13. Acceptance prompt architecture | complete | Reframed acceptance as three evaluator modes (feature-scoped, impact-sweep, exploratory), defined prompt hierarchy, coverage semantics, filing policy by mode, and the next implementation slices for route planning and exploratory evaluation |
| 14. Acceptance mode wiring | complete | Added `AcceptanceMode`/`AcceptanceCampaign`, mode-aware prompt composition, orchestrator-side campaign generation, enriched acceptance review payloads, and dashboard acceptance coverage surfacing |
| 15. yoyo-evolve harness research | complete | Compared yoyo's identity/personality/memory/social/evolution architecture against SpecOrch, wrote a roadmap/design doc, normalized `SON-234` as an epic, and created aligned roadmap epics `SON-242..244` with child issues `SON-245..256` |
| 16. Acceptance route planning and interaction-aware flows | complete | Acceptance campaigns now carry route budgets plus per-route interaction plans; browser evidence reuses Playwright capture to execute `click_text` flows and persist interaction traces into acceptance artifacts |
| 17. Adversarial rubric and filing policy | complete | Added mode-aware adversarial rubric sections to acceptance prompts, made filing guidance explicit per policy, and hardened Linear auto-filing against missing coverage, exploratory UX holds, and out-of-scope routes |
| 18. Acceptance calibration fixtures and dogfood regression suite | complete | Added fixed acceptance fixtures for feature-scoped, exploratory, and real dogfood dashboard samples, plus regression tests that lock filing-policy decisions and dashboard acceptance summary semantics |
| 19. Harness constitutions | complete | Added explicit constitutions for supervisor, acceptance evaluator, and evolvers; system prompts now encode non-negotiable stance around evidence, uncertainty, and narrow evidence-backed change scope |
| 20. Active memory synthesis and evolution journal | complete | Added synthesized self/delivery/feedback active-memory slices, role-scoped memory injection, and a granular evolution journal mirrored into memory and prompts |
| 21. Acceptance taxonomy and epic alignment | complete | Split acceptance into verification/workflow/exploratory/human layers, defined unified product semantics, and realigned roadmap/Epic structure before further implementation |
| 22. Workflow automation semantics for dashboard operator targets | complete | Added stable automation targets for mission cards, mission tabs, approval actions, operator modes, launcher actions, and active-state semantics so workflow acceptance can select and assert key dashboard interactions without ambiguous text matching |
| 23. Workflow acceptance campaigns and dogfood regression | complete | Added dedicated workflow acceptance mode, selector-based interaction plans, workflow-specific coverage/filing contracts, and a workflow dashboard repair-loop calibration fixture so the full Workflow Acceptance epic is regression-locked |
| 24. Dashboard workflow quality replay and judgment | complete | Expanded real workflow dogfood replay into a consolidated same-version coverage sweep, fixed approval-state rerender drift, and proved `25/25` scoped dashboard workflow-replay capabilities before moving into fresh mission proof |
| 25. Workflow Replay E2E skill contract | complete | Captured the replay methodology as a reusable design contract and added a repo-local `.spec_orch/skills/workflow-replay-e2e.yaml` scaffold plus sample payload so future skill work does not depend on operator memory |
| 26. Fresh Acpx Mission E2E first-path plan | complete | Wrote the first implementation plan for a fresh mission path, separating freshness proof from workflow replay proof and defining the first smoke script, fixtures, artifacts, and verification boundaries |
| 27. Fresh Acpx Mission E2E hardening | complete | Added runtime-safe fresh templates, stronger verification contracts, packet scope proof, launch/pickup and dashboard readiness hardening, plus `default` / `multi_packet` / `linear_bound` fresh proof variants that all completed end-to-end |

## Comparison Dimensions
- User entry points and onboarding flow
- Execution visibility and live monitoring
- Artifact model and audit trail
- Control loop and operator interventions
- Multi-agent / multi-run visualization
- UI polish and information architecture
- Debuggability and acceptance workflow

## Risks / Open Questions
- Paperclip may expose stronger demos/docs than actual implementation details.
- Some referenced projects may be early-stage or lightly maintained, which affects how much to borrow directly.
- Need to separate "good demo UX" from "operationally durable observability."
- The dashboard now has `routes.py`, `transcript.py`, `approvals.py`, `missions.py`, and a package shell. `app.py` is no longer the owner of the heaviest approval/transcript rendering, but it is still a transitional shell that should keep shrinking.
- Approval workflow is now explicitly stateful, queue-backed, and batchable, but it still needs richer navigation and deeper action semantics than `/btw` injection alone.
- Transcript evidence is functional and inspectable, but it is still short of the Paperclip bar for reading speed and evidence navigation.
- Visual QA and Costs/Budgets now exist as first-class surfaces with diff/comparison and escalation guidance, but both can still go deeper on operator ergonomics.
- The current remaining work is now mostly high-order UX depth: faster transcript reconstruction, deeper approval queue workflow, stronger visual comparison UX, and more opinionated budget intervention guidance.
- The user correctly called out that the old mission startup flow was still too engineering-heavy; this is now being addressed as a first-class product gap rather than a documentation problem.
- The acceptance evaluator is now wired into the supervised round loop and dashboard surfaces, but the next depth pass should focus on richer issue-filing policy, stronger browser evidence capture, and fully automated dogfood runs.
- The user correctly pushed on the current evaluator’s epistemic limits: it still inherits too much implementation framing and too little true user-perspective exploration.
- The new prompt architecture is now partially live: mode-aware evaluation, explicit coverage reporting, campaign-specific route planning, and basic interaction-aware browser flows are wired, but exploratory autonomy and richer task execution are still the next depth step.
- The acceptance harness now encodes adversarial rubric and policy-aware auto-filing, but it still lacks richer finding taxonomy and truly exploratory multi-step browser task execution.
- The acceptance harness now has repeatable calibration fixtures and a dogfood regression suite, but the next gap is evaluator quality itself: richer finding content, less empty-summary output, and more trustworthy exploratory task execution.
- Acceptance work had started to mix “strict verification”, “workflow operability”, and “exploratory critique” under one umbrella. This is now treated as a product-language problem, not just an implementation problem.
- The immediate next acceptance work should not jump to operator/social feedback. Workflow Acceptance needs its own epic and should land before Human Acceptance & Feedback Loop starts in earnest.
- The Workflow Acceptance epic is now live end-to-end: dashboard automation hooks, workflow-mode campaigns, selector-based interaction plans, and regression fixtures all exist. The next gap is no longer semantics, but real dashboard repair-loop dogfooding against those contracts.
- `Fresh Acpx Mission E2E` is no longer just a single narrow proof path. The branch now proves three fresh variants end-to-end, but still needs future strengthening around richer verification commands, broader packet shapes, and provider portability before it should be treated as a universal guarantee.
- `yoyo-evolve` appears to encode identity, personality, journal history, self-learnings, and social-learnings as first-class prompt inputs, not just docs. This is likely the biggest philosophical gap versus SpecOrch, which is currently mission/control-plane oriented rather than agent-selfhood oriented.
- `yoyo-evolve`'s stability strategy is explicit: one change at a time, mandatory build/test gates, revert on failure, and a public journal. Its “wild growth” is bounded by a very small self-edit aperture.
- `yoyo-evolve`'s social layer is not ornamental. Discussions, family/fork identity, sponsor economics, and social learnings are integrated into the operational scripts, which is materially different from SpecOrch’s current PM/workflow-centric Linear model.
- Roadmap/Linear alignment is now explicit: `SON-74` remains the completed self-evolution baseline, `SON-234` is the normalized operator-console epic, and new epics `SON-242` / `SON-243` / `SON-244` cover adversarial acceptance, selfhood/memory synthesis, and operator-feedback/social learning.
- The current selfhood pass should stay narrow: synthesized learnings must remain machine-readable and role-scoped, rather than turning MemoryService into a second narrative document store.
