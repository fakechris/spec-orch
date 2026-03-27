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
| 6. Operator console next-slice planning | complete | Rebased the Todo list around what is actually left, then shipped the first pass of Approval Queue, Visual QA, Costs/Budgets, continued shell cleanup, and a dedicated operator-console guide. Remaining work is now depth and polish, not missing surfaces |

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
- Approval workflow is now explicitly stateful and has a dedicated queue surface, but the queue still needs stronger urgency, bulk handling, and richer post-action feedback.
- Transcript evidence is functional and inspectable, but it is still short of the Paperclip bar for reading speed and evidence navigation.
- Visual QA and Costs/Budgets now exist as first-class surfaces, but both still need depth beyond their current first pass.
