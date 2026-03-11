---
name: spec-orch-spec-stage
description: >-
  Drive the SpecOrch Spec stage from a coding environment (Cursor/Claude Code).
  Use when the user wants to plan a feature, draft a spec, manage questions,
  approve a spec, or advance an issue through the SpecOrch lifecycle.
  Triggers on "spec-orch", "plan feature", "draft spec", "questions",
  "approve spec", "advance issue", or "EODF workflow".
---

# SpecOrch Spec Stage — Coding Environment Driver

This skill replaces the autonomous LLM Planner when working inside a coding
environment. You (the AI assistant) act as the planner — analysing the issue,
generating questions, drafting the spec, and driving the state machine via CLI.

## Lifecycle States

```
DRAFT → SPEC_DRAFTING → SPEC_APPROVED → BUILDING → VERIFYING → REVIEW → GATE → ACCEPTED
```

## Workflow

### 1. Create or load the issue fixture

```bash
# From an existing plan document:
spec-orch plan-to-spec docs/plans/my-feature.md --issue-id SPC-FEAT-1

# Or use an existing fixture in fixtures/issues/
```

### 2. Draft the spec

```bash
spec-orch spec draft SPC-FEAT-1
```

This creates an initial `spec_snapshot.json` in the workspace.

### 3. Add questions (your analysis)

Analyse the issue and add clarifying questions:

```bash
spec-orch questions add SPC-FEAT-1 \
  --text "Should the API support pagination?" \
  --category requirement \
  --blocking

spec-orch questions add SPC-FEAT-1 \
  --text "Which database backend?" \
  --category architecture \
  --blocking
```

Categories: `requirement`, `environment`, `architecture`, `risk`.

### 4. List and answer questions

```bash
spec-orch questions list SPC-FEAT-1
```

When the user provides answers:

```bash
spec-orch questions answer SPC-FEAT-1 q-abc12345 \
  --answer "Yes, cursor-based pagination" \
  --decided-by chris
```

### 5. Approve the spec

Once all blocking questions are answered:

```bash
spec-orch spec approve SPC-FEAT-1 --approved-by chris
```

Check the spec status anytime:

```bash
spec-orch spec show SPC-FEAT-1
```

### 6. Advance to build

```bash
spec-orch advance SPC-FEAT-1 --live
```

Or run directly:

```bash
spec-orch run-issue SPC-FEAT-1 --live
```

### 7. Post-build workflow

```bash
# Review
spec-orch review-issue SPC-FEAT-1 --verdict pass --reviewed-by chris

# Accept
spec-orch accept-issue SPC-FEAT-1 --accepted-by chris

# Check findings
spec-orch findings list SPC-FEAT-1
```

## Decision Guide

| Situation | Action |
|-----------|--------|
| New feature request | `plan-to-spec` → `spec draft` → add questions |
| User answers a question | `questions answer` |
| All questions answered | `spec approve` |
| Spec approved | `advance` or `run-issue` |
| Build complete | `review-issue` → `accept-issue` |
| Need to re-verify | `rerun` |

## Key Principle

The coding environment AI is the planner. There is no need for LiteLLM or any
external LLM call. You analyse the issue using your own intelligence, generate
questions via CLI, and drive the state machine step by step. The same CLI
commands also work in Daemon mode with an autonomous LLM planner — the
artifacts and state transitions are identical.
