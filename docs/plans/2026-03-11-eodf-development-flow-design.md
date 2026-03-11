# EODF Development Flow Design

## Problem

SpecOrch's pipeline covers `run-issue → verify → gate → PR`, but there is no structured path from brainstorming/planning into that pipeline. In practice, features get developed directly in Cursor, bypassing the spec-orch pipeline entirely. This means we never eat our own dog food.

The gap: **plan documents cannot be fed into `run-issue`**. The pipeline expects a JSON fixture with `builder_prompt`, `verification_commands`, and `acceptance_criteria`, but brainstorming produces a markdown design doc.

## Competitive Analysis

| System | Input | Planning Phase | Execution Phase |
|--------|-------|---------------|-----------------|
| Cyrus | Linear issue (human-written) | None — users write issues directly | codex exec, subroutines |
| cc-connect | Chat message | None — one-shot messages | codex exec |
| Remodex | Phone command | None — one-shot commands | codex app-server |
| **SpecOrch** | Issue fixture JSON | **Gap — no structured plan-to-fixture conversion** | codex exec, verify, gate |

No competitor has a structured planning-to-execution bridge. This is a differentiator opportunity.

## Three-Phase Development Model

```
Phase 1: Brainstorming          Phase 2: Spec              Phase 3: Development
(interactive, human-in-loop)    (semi-auto, one-shot)      (autonomous, codex exec)
                                                           
User <-> AI (Cursor/CLI)        plan-to-spec               run-issue --live
  |                               |                          |
  v                               v                          v
docs/plans/topic-design.md  ->  fixtures/issues/SPC-X.json  ->  workspace/ -> PR
```

### Phase 1: Brainstorming (already works)

Happens in Cursor Plan mode (or any conversation). Interactive dialogue produces a design document at `docs/plans/YYYY-MM-DD-<topic>-design.md`.

Outputs:
- Design markdown with architecture, file change list, acceptance criteria
- Committed to git

No code changes needed — this phase already works via Cursor.

### Phase 2: Spec Generation (new)

New CLI command: `spec-orch plan-to-spec`

```
spec-orch plan-to-spec docs/plans/2026-03-11-observability-design.md \
  --issue-id SPC-OBS-1 \
  --output fixtures/issues/SPC-OBS-1.json
```

This command converts a plan markdown into an issue fixture JSON. It works by:

1. Reading the plan markdown
2. Extracting structured data:
   - `title` — from the first H1 heading
   - `summary` — from the "Background" or "Overview" section (first paragraph)
   - `builder_prompt` — from the "File Changes" / "Implementation" sections, converted into step-by-step instructions for Codex
   - `verification_commands` — defaults to standard ruff/mypy/pytest, overridable
   - `acceptance_criteria` — extracted from plan if present, or derived from file changes
   - `context.files_to_read` — extracted from file paths mentioned in the plan
   - `context.architecture_notes` — from the "Architecture" section if present
   - `context.constraints` — from "Not doing" / "Constraints" sections
3. Writing the JSON fixture
4. Printing the generated fixture for review

Flags:
- `--issue-id` (required): Issue ID for the fixture
- `--output` / `-o`: Output path (default: `fixtures/issues/{issue-id}.json`)
- `--edit`: Open the generated fixture in `$EDITOR` for manual review before saving
- `--builder-prompt-from` / `-p`: Override builder_prompt with content from a separate file (for cases where the plan is complex and needs a custom prompt)
- `--no-builder`: Set `builder_prompt` to null (for manual/semi-auto EODF)

The extraction is template-based, not LLM-based, to avoid circular dependency (needing an LLM to generate specs for the LLM). For complex plans, users can `--edit` the result or provide a custom prompt via `--builder-prompt-from`.

### Phase 3: Development (already works)

```
spec-orch run-issue SPC-OBS-1 --live    # codex builds + real-time stream
spec-orch watch SPC-OBS-1               # monitor from another terminal
spec-orch review-issue SPC-OBS-1 ...    # review
spec-orch accept-issue SPC-OBS-1 ...    # accept
spec-orch gate SPC-OBS-1                # gate check
spec-orch create-pr SPC-OBS-1           # create PR
```

## Plan Markdown Conventions

For `plan-to-spec` to reliably extract data, plan documents should follow these conventions:

```markdown
# <Title>                              → fixture.title

## Background / Overview               → fixture.summary (first paragraph)

## Architecture / Design               → fixture.context.architecture_notes

## File Changes / Implementation        → fixture.builder_prompt
                                         (each bullet becomes a step)

## Acceptance Criteria                  → fixture.acceptance_criteria
                                         (each bullet becomes a criterion)

## Not Doing / Constraints              → fixture.context.constraints
```

File paths mentioned anywhere (backtick-quoted paths ending in `.py`, `.json`, etc.) are auto-extracted into `context.files_to_read`.

## Builder Prompt Generation Strategy

The `builder_prompt` is the most critical field — it's what Codex actually executes. Generation strategy:

For each file in the "File Changes" section:
1. If **new file**: "Create `<path>` with <description from plan>"
2. If **modified file**: "In `<path>`, <description of changes from plan>"

Then append standard suffixes:
- "Run ruff check src/ and fix any lint errors."
- "Run pytest tests/ -q to make sure nothing is broken."

Example output for the observability feature:

```json
{
  "issue_id": "SPC-OBS-1",
  "title": "Builder observability — live event stream, watch, and logs",
  "summary": "Add real-time observability for Codex builder execution...",
  "builder_prompt": "Implement builder observability for spec-orch.\n\n1. Create src/spec_orch/services/event_formatter.py with an EventFormatter class...\n2. Create src/spec_orch/services/activity_logger.py...\n3. In src/spec_orch/services/codex_exec_builder_adapter.py, expand read_stdout()...\n...",
  "verification_commands": {
    "lint": ["{python}", "-m", "ruff", "check", "src/"],
    "typecheck": ["{python}", "-m", "mypy", "src/"],
    "test": ["{python}", "-m", "pytest", "tests/", "-q"],
    "build": ["{python}", "-c", "print('build ok')"]
  },
  "acceptance_criteria": [
    "run-issue --live streams events to stderr",
    "spec-orch watch tails activity.log",
    "spec-orch logs shows complete history",
    "All existing tests pass",
    "ruff and mypy pass"
  ],
  "context": {
    "files_to_read": [
      "src/spec_orch/services/codex_exec_builder_adapter.py",
      "src/spec_orch/services/run_controller.py",
      "src/spec_orch/cli.py"
    ],
    "architecture_notes": "codex exec --json emits JSONL events. The adapter reads them in a thread...",
    "constraints": [
      "Do not break existing tests",
      "Do not change codex exec invocation method"
    ]
  }
}
```

## Implementation Plan

### Files to Create/Modify

- **New**: `src/spec_orch/services/plan_parser.py` — Markdown plan parser
  - `parse_plan(path: Path) -> PlanData` — extracts structured data from markdown
  - `PlanData` dataclass with title, summary, file_changes, acceptance_criteria, constraints, architecture_notes
- **New**: `src/spec_orch/services/spec_generator.py` — Converts PlanData to Issue fixture JSON
  - `generate_fixture(plan: PlanData, issue_id: str) -> dict` — produces the fixture dict
  - `generate_builder_prompt(plan: PlanData) -> str` — constructs step-by-step prompt
- **Modify**: `src/spec_orch/cli.py` — Add `plan-to-spec` command
- **New**: `tests/unit/test_plan_parser.py` — Parser tests
- **New**: `tests/unit/test_spec_generator.py` — Generator tests
- **Modify**: `tests/unit/test_cli_smoke.py` — plan-to-spec smoke test

### Verification

- ruff check: 0 errors
- mypy: 0 issues
- pytest: all pass
- End-to-end: generate a fixture from an existing plan doc, then `run-issue` with it

## Not Doing

- LLM-based plan parsing — template extraction is sufficient and avoids circular dependency
- Interactive plan editing UI — `$EDITOR` integration covers this
- Plan versioning — git handles this
- Multi-issue plan splitting — one plan = one issue for now
