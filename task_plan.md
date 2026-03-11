# Task Plan: Prototype-first SpecOrch buildout

## Goal
Iteratively turn the docs-first SpecOrch repo into a runnable prototype that can dogfood its own issue workflow end-to-end.

## Current Phase
Phase 2

## Phases

### Phase 1: Repository Baseline & Scope
- [x] Understand user intent
- [x] Confirm current `main` state and merged prototype capabilities
- [x] Choose the next smallest end-to-end slice
- [x] Document the slice boundary in planning files
- **Status:** complete

### Phase 2: Isolated Workspace & Baseline
- [ ] Create isolated git worktree from `main`
- [ ] Set up a project-local `.venv`
- [ ] Run clean baseline tests before changes
- **Status:** in_progress

### Phase 3: TDD for Acceptance Flow
- [ ] Add failing tests for human acceptance artifacts and gate recomputation
- [ ] Verify the new tests fail for the expected reason
- **Status:** pending

### Phase 4: Implementation
- [ ] Implement minimal acceptance recording flow
- [ ] Recompute gate after acceptance
- [ ] Update `report.json` and `explain.md`
- **Status:** pending

### Phase 5: Verification & Integration
- [ ] Run targeted and full test suite
- [ ] Commit feature branch changes
- [ ] Cherry-pick cleanly back to `main`
- **Status:** pending

## Key Questions
1. What is the smallest human-acceptance mechanism that closes the prototype loop without adding workflow bloat?
2. How should acceptance be persisted so it can be re-read by gate computation and later synced to Linear/PR states?

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Keep the next slice focused on explicit human acceptance | The current prototype already handles builder and verification; acceptance is the missing piece for a true mergeable path |
| Continue using project-local `.worktrees/` and `.venv` | Matches the repo policy and keeps the prototype hermetic from system Python |
| Use TDD for the new acceptance flow | The behavior is small, testable, and should become the contract for later Linear/PR integration |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| None yet for this increment | - | - |

## Notes
- Keep the scope to local artifacts and CLI behavior only.
- Defer real reviewer adapter and external state sync until acceptance flow is stable.
