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
| 5. Operator console implementation | in_progress | Mission detail shell, transcript timeline blocks, websocket hardening, inbox scaffolding, approval-aware inbox semantics, transcript filter-bar depth, transcript inspector scaffolding, approval workspace surfacing, approval action presets, transcript command-burst grouping, transcript details payloads, and dashboard package refactor are in place |
| 6. Deliver research memo and shipable plan | in_progress | Remaining work is stronger approval workflows beyond canned guidance, richer transcript rendering in the UI, and continuing to split the transitional dashboard app module |

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
- The dashboard now has `routes.py`, `transcript.py`, and a package shell, but `app.py` is still a transitional large module that should be split further.
- The inbox now distinguishes approval-needed items from generic paused missions, and approval actions can inject canned guidance directly, but the UI still lacks a fully explicit approve/reject/request-revision workflow with stateful confirmations.
