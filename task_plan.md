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
| 4. SpecOrch implications | in_progress | Translating findings into concrete UI/observability roadmap for SpecOrch |
| 5. Deliver research memo | in_progress | Writing operator-console design and next implementation slices |

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
