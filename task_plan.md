# Task Plan: Self-Hosting Linear Sync Wave

## Goal
Make Linear the structured source of truth for the next self-hosting wave by mirroring spec-orch status and plan state into Linear, then extending the existing conversational intake flow toward chat-to-issue end-to-end.

## Current Phase
Phase 3

## Phases

### Phase 1: Requirements & Discovery
- [x] Read the latest hardening and harness review handoff documents
- [x] Inspect current Linear intake, canonical issue, handoff, and conversation assets
- [x] Identify the first tranche with the highest leverage
- **Status:** complete

### Phase 2: Planning & Structure
- [x] Write the self-hosting execution plan
- [x] Define the structured Linear mirror contract
- [x] Lock the first tranche write scope and tests
- **Status:** complete

### Phase 3: Implementation
- [x] Implement structured Linear mirror rendering and write-back
- [x] Extend tests for the Linear mirror contract
- [x] Keep the existing intake parser backward compatible
- [x] Start plan mirroring into Linear
- [x] Sync bound Linear issue descriptions after plan generation
- [x] Start chat-to-issue end-to-end
- [x] Add a backfill path for previously bound Linear issues
- **Status:** in_progress

### Phase 4: Verification
- [x] Run focused pytest coverage for Linear mirror/intake/write-back
- [x] Run ruff and mypy on touched files
- [x] Run focused pytest coverage for plan mirroring into Linear
- [x] Decide whether tranche closeout needs full acceptance/archive
- **Status:** pending

### Phase 5: Delivery
- [x] Summarize the first tranche outcome
- [x] Define the next tranche for chat-to-issue end-to-end
- [ ] Prepare the branch for commit/PR if ready
- **Status:** pending

## Key Questions
1. What is the smallest structured mirror we can write into Linear without destabilizing the current intake format?
2. Which plan/status fields are worth mirroring first so Linear matches real spec-orch work?
3. How do we preserve compatibility with existing Linear-native intake parsing while adding mirror metadata?

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Start from a fresh worktree on `origin/main` commit `c5d6d07` | Keeps this self-hosting wave isolated from the already-merged hardening work |
| First tranche is a structured Linear mirror contract, not a larger chat orchestrator rewrite | This closes the biggest current gap between spec-orch runtime truth and Linear truth |
| Reuse existing intake/canonical issue/handoff seams instead of inventing a new architecture | The user explicitly wants alignment, not another architecture round |
| Mirror metadata should live in a distinct `SpecOrch Mirror` section rendered as JSON | This keeps the core intake text readable while remaining parse-safe and replaceable |
| Plan mirroring should be an additive `plan_sync` carrier inside the existing mirror block | This keeps Linear updates structured without creating a second competing status surface |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
|       | 1       |            |

## Notes
- Keep `Linear / plan mirroring / chat-to-issue` in one program, but implement it as small tranches.
- Treat the harness review checklist and context taxonomy as governance language, not as a request to redesign the runtime.
