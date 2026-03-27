# Operator Console Next Todos

## Goal

Refresh the operator-console roadmap so it reflects the current codebase, not the older foundation-phase Todo list.

This document replaces the stale framing of "approval is not stateful yet" and "approval/transcript rendering still lives in `app.py`" with the next real slice:

- keep driving the dashboard through the impeccable workflow
- close the biggest UX gap versus Paperclip
- finish the remaining first-class operator surfaces

## Current Baseline

The following are already in place and should no longer be treated as open foundation Todos:

- operator shell / workbench layout
- Mission Detail base page
- approval-aware Inbox
- Approval workspace inside Mission Detail
- approval action presets wired into the `/btw` path
- persisted approval action history
- explicit approval state semantics in Mission Detail and Inbox
- transcript linked evidence
- command-burst grouping
- transcript structured details
- transcript inspector
- `routes.py`, `transcript.py`, `approvals.py`, and `missions.py` extraction
- shared operator-console helper namespace in `static/operator-console.js`

## Design Stance

Continue to follow `.impeccable.md`:

- calm
- reliable
- controllable

Do not regress toward:

- BI dashboard aesthetics
- flashy AI-control-panel visuals
- chat-window interaction patterns

Keep using the impeccable workflow as a continuous loop, not a final polish pass:

1. `audit`
2. `arrange`
3. `clarify`
4. `typeset`
5. `normalize`
6. `harden`
7. `polish`

## Completed In This Slice

The following items from the refreshed foundation backlog are now complete:

- Transcript UX moved forward with clearer block types, command-burst grouping, emphasis states, linked evidence markers, and a stronger inspector
- Approval Queue is now a dedicated dashboard surface with batch actions, urgency, wait-time surfacing, audit-backed feedback, and mission-focus navigation
- Visual QA is now a dedicated mission surface with screenshot/gallery surfacing, blocking summaries, and artifact links
- Costs & Budgets is now a dedicated mission surface with thresholds, incidents, and Inbox alerts
- Transcript now exposes operator readout summaries and stronger evidence/review routes
- Approval Queue now surfaces age buckets, result summaries, and next-pending mission routing after batch actions
- Visual QA now exposes explicit mission/round review routes
- Costs incidents now expose explicit suggested-action routes for operator follow-through
- `app.py` has been reduced further by moving the heavy approval/transcript/surface rendering into shared helpers, removing duplicated transcript implementations, and dropping the obsolete inline helper fallback
- operator-console documentation now has a dedicated guide

## Remaining Todo Buckets

### 1. Transcript UX Push

The transcript now has block filtering, emphasis, jump targets, and structured inspection, but it is still short of the Paperclip bar.

What remains:

- improve evidence reading beyond structured key-value details and link lists
- make command bursts easier to scan and expand at a glance
- add richer round / packet / artifact navigation beyond the current review routes
- further reduce the remaining "payload browser" feel inside the inspector

Success criteria:

- operators can reconstruct "what happened and why" without reading raw JSON first
- the right rail becomes an evidence reader, not just a payload viewer

### 2. Approval Workflow Depth

Approval Queue now exists as a first-class, stateful surface with batch handling, but the workflow can still go deeper.

What remains:

- richer post-action confirmation inside the destination mission/round
- queue-state transitions that do more than guidance injection + audit logging

Success criteria:

- an operator can process many approval items with minimal ambiguity

### 3. Visual QA Depth

Visual QA now exists as a comparison-aware surface, but it can still go deeper.

What remains:

- richer screenshot/gallery presentation
- sharper linkage back to transcript and round context
- stronger changed-area and regression emphasis
- true side-by-side or swipe-style workflows once the UI shell is ready

Success criteria:

- visual issues are readable without opening raw artifact files

### 4. Costs and Budgets Depth

Costs surface now exists with thresholds, incidents, and operator guidance, but budget policy and escalation are still minimal.

What remains:

- stronger threshold markers across mission detail and rails
- richer incident presentation and escalation copy
- clearer operator guidance when a mission enters warning/critical spend
- budget-aware intervention suggestions that tie back to mission scope or retry policy

Success criteria:

- spend risk is visible before the operator has to inspect raw cost numbers

### 5. Dashboard Package Cleanup

The heaviest duplicate rendering has been removed from `app.py`, but the shell is still transitional.

What remains:

- continue shrinking `src/spec_orch/dashboard/app.py`
- separate shell rendering from page-specific orchestration
- isolate Mission Detail page composition further
- isolate Inbox rendering further
- decide whether `DASHBOARD_HTML` should move fully out of `app.py`
- keep moving non-UI helpers out of the app entrypoint

Success criteria:

- `app.py` becomes a thin app-shell coordinator rather than a mixed shell plus page-render module

### 6. Operator Documentation Refresh

The docs now have a dedicated operator-console guide, but the doc set still needs one more consolidation pass.

What remains:

- one observability guide explaining Inbox, Mission Detail, transcript inspector, approval history, and linked evidence
- update service/run guides to point to the operator-console workflow first
- add screenshots or operator walkthroughs once the surfaces stabilize

Success criteria:

- a new operator can understand where to look, how to intervene, and how to debug a supervised mission from docs alone

## Recommended Execution Order

### Slice A: Transcript + Approval Depth

- push transcript readability toward Paperclip
- deepen Approval Queue workflow
- keep running the impeccable loop against these two surfaces

### Slice B: Visual QA + Costs Depth

- deepen comparison workflows and budget escalation

### Slice C: Package Cleanup + Docs

- keep shrinking `app.py`
- publish a systematic operator-console doc set

## Immediate Next Actions

1. Run the impeccable loop against Mission Detail and Transcript again.
2. Deepen Approval Queue workflow and feedback.
3. Make Visual QA more screenshot-first.
4. Add budget thresholds and incidents to Costs.
5. Keep paying down `app.py` shell debt while those surfaces evolve.

## Verification Baseline

For dashboard work, keep using:

```bash
uv run --python 3.13 python -m pytest tests/unit/test_dashboard.py tests/unit/test_dashboard_api.py tests/unit/test_dashboard_package.py -q
uv run --python 3.13 python -m ruff check src/spec_orch/dashboard.py src/spec_orch/dashboard tests/unit/test_dashboard_api.py tests/unit/test_dashboard_package.py pyproject.toml
```
