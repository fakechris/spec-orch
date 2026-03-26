## Design Context

### Users
SpecOrch is used by technical operators supervising autonomous software delivery work. These users are not casual dashboard viewers and not chat-first AI users. They are engineers, founders, or technical managers running missions, rounds, approvals, verification, and intervention flows across multiple agent executions.

Their context is operational and decision-heavy:
- They need to detect what is happening now.
- They need to understand what is blocked and why.
- They need to decide whether to approve, intervene, resume, rerun, or stop.
- They need to reconstruct how the system arrived at its current state.

The interface should help them move fluidly between fleet-level awareness and deep inspection without losing mission context.

### Brand Personality
SpecOrch should feel:
- cold
- reliable
- controllable

This is an operator control plane, not a BI dashboard, not a chat tool, and not a flashy AI demo surface. The emotional goal is confidence through structure. The UI should feel like a serious cockpit for supervised execution: calm under load, explicit about state, and trustworthy when something goes wrong.

### Aesthetic Direction
Primary reference:
- `superset.sh` IDE-style layout, especially its workbench composition and persistent context framing

Secondary product reference:
- Paperclip-style operator control plane, especially first-class surfaces for approvals, transcripts, budgets, and auditability

Anti-references:
- BI dashboard aesthetics
- flashy AI control panels
- chat-centric product layouts
- generic SaaS card-grid dashboards

Visual direction:
- workbench-like rather than dashboard-like
- split-pane and operator-console oriented
- persistent mission context with detail drilling instead of page-to-page context resets
- disciplined density with clear hierarchy
- sober, technical, and intentional rather than decorative

### Design Principles
1. Preserve context across navigation.
   Mission identity, current status, and primary actions should remain visible while drilling into transcript, approvals, visual QA, or artifacts.

2. Design for operator questions, not generic content blocks.
   The interface must answer: what is happening now, what is blocked, what needs my action, what can I do next, and how did we get here.

3. Make intervention obvious but safe.
   Approve, reject, resume, rerun, stop, and inject-guidance actions must be consistently placed, clearly labeled, and guarded against ambiguity.

4. Treat runtime evidence as first-class UI objects.
   Rounds, packets, sessions, approvals, costs, transcripts, and visual findings should be navigable product surfaces, not merely files or raw logs.

5. Favor a workbench over a dashboard.
   Avoid card clutter, decorative metrics, and AI-demo flourishes. Use strong layout structure, stable panels, and clear visual hierarchy to support sustained operational work.
