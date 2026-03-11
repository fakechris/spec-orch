# Trust Boundaries

## Input Classification

### Trusted (local filesystem, user-authored)

- **Plan markdown** (`docs/plans/*.md`) — authored by the user or AI assistant
  in an interactive session. Content flows into `builder_prompt` via
  `plan-to-spec`, which is intentional: the prompt IS the instruction to the
  builder. No sanitisation is applied or needed.

- **Fixture JSON** (`fixtures/issues/*.json`) — either hand-written or generated
  by `plan-to-spec`. Loaded by `FixtureIssueSource`, which validates `issue_id`
  format (`^[A-Za-z0-9_-]+$`).

- **Gate policy** (`gate.policy.yaml`) — local config, not user-facing input.

### Semi-trusted (external API, structured)

- **Linear issues** — fetched via GraphQL. `issue_id` is validated before use.
  Issue description is parsed for `## Builder Prompt` / `## Acceptance Criteria`
  sections; the extracted prompt is sent to the builder by design.

### Untrusted

- **Builder output** — code produced by the builder (Codex, etc.) is untrusted
  and must pass verification (lint, typecheck, test) and gate before merge.

- **Review comments** — from GitHub Apps or human reviewers. Currently consumed
  as advisory text; future `Finding` schema will add structure.

## Path Traversal Defence

`issue_id` is validated at multiple layers:

1. **`WorkspaceService.issue_workspace_path()`** — regex `^[A-Za-z0-9_-]+$`
   (unified entry point for all workspace path construction)
2. **`FixtureIssueSource.load()`** — same regex
3. **CLI `rerun` command** — `Path(issue_id).name != issue_id` check

Layer 1 is the authoritative defence; layers 2-3 are defence-in-depth.
