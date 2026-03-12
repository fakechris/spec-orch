# Retrospective — Parallel Wave Execution (E2E Discussion Pipeline)

**Mission**: 2026-03-i-want-to-add-parallel-wave-execution-to-spec-orch-currently-spec-orch-run-only
**PR**: #15
**Linear Issues**: SON-13 ~ SON-22
**Date**: 2026-03-12

## What went well

- **Full discuss → freeze → plan pipeline validated end-to-end** with live MiniMax M2.5 LLM. Three rounds of brainstorming produced a high-quality spec with clear acceptance criteria and interface contracts.
- **LLM-generated ExecutionPlan** was structurally sound: 4 waves, 10 work packets, correct DAG dependencies.
- **`api_type` config** resolved the model prefix confusion permanently — no more manual `anthropic/` vs `openai/` prefix juggling.

## What went wrong

- **Pipeline stopped at plan-show** — the plan file only defined 4 steps (up to plan-show), omitting promote → PR → review → merge → retro. Root cause: no standard pipeline checklist existed.
- **API key typo** (`n` vs `z` in one character) cost significant debugging time across multiple auth header formats before being identified.
- **`promote` command was broken** — always fell back to local stub IDs because `LinearClient` was never injected. This bug existed since the promote command was written.
- **`_load_planner_config` didn't extract `api_type`** — the scoper in `plan` command always fell back to `"anthropic"` regardless of config. Found by CodeRabbit review.

## Fixes applied

| Issue | Fix | Prevention |
|-------|-----|-----------|
| Pipeline stops early | Created `pipeline_checker.py` with 11-stage checklist; `spec-orch pipeline <id>` command; auto `>> next:` hints after every key command | Systemic — code-level enforcement |
| promote uses local stubs | Inject real `LinearClient` when token available | Bug fix |
| api_type not propagated | Added to `_load_planner_config` return dict | Bug fix |
| LinearClient resource leak | Wrapped in try/finally with close() | Bug fix |
| Mission ID too long | Extract H1 from LLM spec output; cap at 60 chars | Design fix |

## Metrics

- **Pipeline stages**: 11/11 completed
- **Tests**: 266 passed (9 new for pipeline_checker)
- **Linear issues created**: 10 (SON-13 ~ SON-22)
- **Review bots**: 3 (Gemini, Devin, CodeRabbit) — 4 actionable findings, all fixed
- **Commits in PR**: 4

## Key takeaway

Without a codified pipeline checklist, "done" is subjective. The `spec-orch pipeline` command makes progress auditable and next-steps automatic — the system now tells you what's missing instead of relying on memory.
