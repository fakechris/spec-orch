# Findings & Decisions

## Requirements
- Start from the latest `main` in a fresh worktree.
- Align spec-orch reality with Linear epic/issue status.
- Reflect the plan structure in Linear rather than only in local docs.
- Make the previously discussed chat-to-issue workflow actually run end-to-end.
- Reuse the latest handoff in `llm_planner_orch`, especially the 5-subsystem review checklist, bottleneck-first ritual, and context taxonomy.

## Research Findings
- `origin/main` is currently at `c5d6d07`, which already includes the phase-2 hardening merge.
- Existing Linear-native intake already covers:
  - structured intake parsing/rendering in `src/spec_orch/services/linear_intake.py`
  - canonical issue normalization in `src/spec_orch/services/canonical_issue.py`
  - intake-to-workspace handoff in `src/spec_orch/services/intake_handoff.py`
  - Linear comments/description updates in `src/spec_orch/services/linear_write_back.py`
- What is still missing is a distinct contract that mirrors spec-orch runtime state and plan state back into Linear in a structured way.
- A `SpecOrch Mirror` markdown section with fenced JSON works cleanly with the existing intake parser because unknown `##` sections are ignored by the current extraction logic.
- `ConversationService` and `LinearConversationAdapter` already exist, so the future chat-to-issue flow can build on existing conversation plumbing instead of creating a second chat stack.
- The best shape for plan mirroring is not a second Linear section, but an additive `plan_sync` carrier inside the existing `SpecOrch Mirror`.
- The cleanest chat-to-issue path is to reuse the existing dashboard intake workspace seam during `freeze`, instead of building a conversation-only canonicalization stack.
- Historical Linear drift needs an explicit sweep path; auto-sync on new launcher/daemon events is not enough by itself.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Add a structured Linear mirror contract on top of the current intake description | Lets Linear reflect spec-orch truth without breaking existing intake parsing |
| Keep mirror metadata separate from canonical issue semantics | The context taxonomy argues for explicit boundaries between active context, review evidence, archive, and promoted learning |
| Use the 5-subsystem review frame as tranche governance, not as runtime data model | It is a review language, not a replacement architecture |
| Derive an explicit `next_action` for the mirror instead of only echoing handoff state | Linear needs operator-facing action language such as `create_workspace`, not just substrate state |
| Keep plan status inside a structured `plan_sync` object and let `plan_summary` stay compact/human-readable | This makes Linear readable for humans while preserving parse-safe state for later automation |
| Reuse one mission-level mirror sync seam across launcher, daemon, conversation freeze, and CLI backfill | Any second write path would immediately recreate the status drift problem we are trying to remove |
| Add `spec-orch linear-sync` as the historical correction path | Updating old bound issues should be an explicit operation, not an accidental side effect of future launches |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| `sed` path for `linear_conversation.py` was wrong | Inspected `conversation_service.py` and `linear_conversation_adapter.py` usage via `rg` instead |
| Launcher tests expected `create_workspace` from drafts that were not verification-ready | Added `evidence_expectations` so the tests cover the real ready-for-workspace path |
| `daemon.py` mirror helper was initially inserted inside a `try` block and broke syntax | Moved the helper below the mission execution exception handlers |
| `ruff check` rejected long lines that formatter would not split in `linear_plan_sync.py` | Broke the lines manually and then reran lint/format |

## Resources
- `docs/plans/2026-04-04-harness-review-checklist-and-context-taxonomy.md`
- `docs/plans/2026-04-03-phase-2-hardening-execution-plan.md`
- `docs/plans/2026-04-01-conversational-intake-and-workflow-overview.md`
- `src/spec_orch/services/linear_intake.py`
- `src/spec_orch/services/linear_write_back.py`
- `src/spec_orch/services/conversation_service.py`
- `src/spec_orch/services/linear_plan_sync.py`
- `src/spec_orch/services/linear_conversation_adapter.py`
- `src/spec_orch/dashboard/launcher.py`
- `src/spec_orch/cli/mission_commands.py`

## Visual/Browser Findings
- None yet.

## Current Outcome
- Structured Linear mirror contract: implemented
- Additive plan mirroring into Linear: implemented
- Chat-to-issue end-to-end through `freeze`: implemented
- Historical bound-issue backfill via CLI: implemented
- Focused verification across these seams: `118 passed`
