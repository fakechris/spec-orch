# Review Fixes Batch — PR #3 and PR #4 Combined

## Background

PR #3 (builder observability) and PR #4 (plan-to-spec) each received multiple review comments from Devin, Codex, and Gemini. Seven issues are confirmed as real bugs or necessary improvements. This plan batches them into a single fix round.

## File Changes

- **Modify** `src/spec_orch/services/run_controller.py` — In `run_issue()` (around line 65-134) and `rerun_issue()` (around line 297-355), replace direct `activity_logger = self._open_activity_logger(...)` / `activity_logger.close()` with a `with` statement using the existing `__enter__/__exit__` protocol. This prevents file handle leaks when exceptions occur between open and close.
- **Modify** `src/spec_orch/cli.py` — In the `watch_issue` function (around line 446-458), record the file size BEFORE reading the initial content with `read_text()`, and use that as the starting offset for the tail loop. This fixes the race condition where lines appended between the initial read and the offset assignment would be lost.
- **Modify** `src/spec_orch/cli.py` — In the `_edit_fixture_json` function (around line 628), replace `editor.split()` with `shlex.split(editor)` for robust parsing of `$EDITOR` values that contain arguments. Add `import shlex` to the top-level imports if not already present.
- **Modify** `src/spec_orch/services/spec_generator.py` — In `generate_builder_prompt()` (around line 37-38), number the suffix instructions as continuation of the numbered list. Replace the two `numbered.append(...)` calls so they use `f"{next_index}. Run ruff check..."` format where `next_index` continues from the last file change instruction.
- **Modify** `src/spec_orch/services/spec_generator.py` — In `_instruction_from_change()` (around line 51), remove `in` from the regex `\b(modify|update|in)\b`. The word "in" is too common and causes false matches like "Add unit tests in `tests/test_x.py`" to lose the action description before the path. Only `modify` and `update` should trigger the "In `path`, ..." rewrite.
- **Modify** `src/spec_orch/services/plan_parser.py` — In `_extract_first_paragraph_after()` (around line 119-122), when a heading is encountered and we have NOT yet started collecting a paragraph, break instead of continue. This prevents the function from crossing section boundaries when a section (like `## Background`) is empty.
- **Modify** `src/spec_orch/services/plan_parser.py` — In `_heading_matches()` (around line 105-106), replace the substring check `alias in candidate or candidate in alias` with a check that the alias equals the candidate OR the candidate starts with the alias followed by a space/word boundary. This prevents false positives like "design" matching "redesigned".
- **Modify** `tests/unit/test_spec_generator.py` — Add test `test_generate_builder_prompt_suffix_is_numbered` to verify suffix instructions are numbered.
- **Modify** `tests/unit/test_spec_generator.py` — Add test `test_instruction_from_change_does_not_rewrite_in_bullets` to verify "Add tests in `path`" is NOT rewritten.
- **Modify** `tests/unit/test_plan_parser.py` — Add test `test_parse_summary_stops_at_next_heading_for_empty_section` verifying that an empty `## Background` followed by `## File Changes` does not capture File Changes content as the summary.
- **Modify** `tests/unit/test_plan_parser.py` — Add test `test_heading_match_does_not_false_positive_on_substring` verifying "Redesigned" does not match alias "design".
- **Modify** `tests/unit/test_cli_smoke.py` — If there is a test for `watch`, update or add a test verifying the offset race condition is fixed (optional, depends on testability).

## Acceptance Criteria

- ActivityLogger is used via `with` statement in run_issue and rerun_issue, guaranteeing handle closure
- watch command records file offset before initial read, no data loss on append
- _edit_fixture_json uses shlex.split instead of str.split
- Builder prompt suffix instructions are numbered continuously
- "in" is removed from modify/update regex, natural "in" bullets preserved
- Empty section summary extraction stops at next heading boundary
- Heading matching uses word-boundary prefix check, not substring
- All existing tests pass
- New tests cover each fix
- ruff and mypy pass

## Not Doing

- Memory optimization for read_text().splitlines() in logs/watch — low priority, deferred
- Refactoring watch to use streaming file read — separate optimization task
