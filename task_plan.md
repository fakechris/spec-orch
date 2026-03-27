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
