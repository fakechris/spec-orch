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
| 5. Operator console implementation | in_progress | Mission detail shell, transcript timeline blocks, websocket hardening, inbox scaffolding, approval-aware inbox semantics, transcript filter-bar depth, and transcript inspector scaffolding are in place |
| 6. Deliver research memo and shipable plan | in_progress | Remaining work is approvals action surfacing, transcript grouping/payload depth, docs sync, and package refactor follow-through |

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
- The current dashboard still lives in a single Python module; planned package extraction is not done yet.
- The inbox now distinguishes approval-needed items from generic paused missions, but intervention actions are not yet first-class in the UI.
