# spec-orch Configuration Guide (AI-Readable)

> This document is designed for AI assistants to help users configure spec-orch.
> It contains the complete schema, per-language templates, and constraint rules.

---

## Quick Start

```bash
# Auto-detect project type and generate config
spec-orch init

# Or with flags
spec-orch init --force      # overwrite existing
spec-orch init --yes        # accept defaults without prompting

# Verify configuration
spec-orch config check
```

---

## Configuration File: `spec-orch.toml`

All configuration lives in a single TOML file at the project root.

---

## `[issue]` — Issue Source

Defines where spec-orch loads issues from.

| Key | Type | Default | Values |
|-----|------|---------|--------|
| `source` | string | `"fixture"` | `fixture`, `linear`, (extensible via registry) |

```toml
[issue]
source = "linear"
```

When `source = "fixture"`, issues are loaded from `fixtures/issues/<issue_id>.json`.
When `source = "linear"`, requires `[linear]` section to be configured.

---

## `[linear]` — Linear Integration

Required when `[issue] source = "linear"`.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `token_env` | string | `"SPEC_ORCH_LINEAR_TOKEN"` | Env var containing API token |
| `team_key` | string | `"SPC"` | Linear team key |
| `poll_interval_seconds` | int | `60` | Daemon polling interval |
| `issue_filter` | string | `"assigned_to_me"` | Filter strategy |

---

## `[builder]` — Builder Adapter

Controls which AI agent performs code generation.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `adapter` | string | `"codex_exec"` | See adapter table below |
| `executable` | string | varies | CLI executable path |
| `model` | string | — | Model override |
| `timeout_seconds` | int | `1800` | Execution timeout |

### Adapter Options

| `adapter` value | Agent | Executable | Description |
|----------------|-------|------------|-------------|
| `codex_exec` | OpenAI Codex | `codex` | Default, calls `codex exec --json` |
| `opencode` | OpenCode | `opencode` | Calls `opencode run --format json` |
| `droid` | Droid | `droid` | Calls `droid exec` |
| `claude_code` | Claude Code | `claude` | Calls Claude Code CLI |
| `acpx` | Any (via ACPX) | `npx` | Unified agent protocol |
| `acpx_<agent>` | Shortcut | `npx` | e.g., `acpx_opencode` = `acpx` + `agent = "opencode"` |

### ACPX-Specific Keys

Only applicable when `adapter = "acpx"` or `adapter = "acpx_<agent>"`:

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `agent` | string | `"opencode"` | Target agent |
| `session_name` | string | — | Named session for persistence |
| `permissions` | string | `"full-auto"` | `full-auto`, `approve-reads` |
| `acpx_package` | string | `"acpx"` | npm package name |

---

## `[verification]` — Verification Commands

Defines the commands for each verification step. If this section is absent,
spec-orch falls back to Python defaults (ruff/mypy/pytest).

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `lint` | list[string] | — | Lint command |
| `typecheck` | list[string] | — | Type checking command |
| `test` | list[string] | — | Test command |
| `build` | list[string] | — | Build command |

Steps that are **omitted** are treated as "not applicable" and automatically
pass the gate check. This means a JavaScript project without TypeScript can
simply omit `typecheck`.

### Token Substitution

The special token `{python}` is replaced with the current Python interpreter
path at runtime. Useful for Python projects:

```toml
[verification]
lint = ["{python}", "-m", "ruff", "check", "src/"]
```

For non-Python projects, use direct commands:

```toml
[verification]
lint = ["npm", "run", "lint"]
```

---

## `[reviewer]` — Review Adapter

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `adapter` | string | `"local"` | `local` or `llm` |
| `model` | string | — | LLM model (for `llm` adapter) |
| `api_key_env` | string | — | Env var for API key |
| `api_base_env` | string | — | Env var for API base URL |

---

## `[planner]` — LLM Planner

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `model` | string | — | Full `provider/model` string |
| `api_type` | string | `"anthropic"` | `anthropic` or `openai` |
| `api_key_env` | string | — | Env var for API key |
| `api_base_env` | string | — | Env var for API base URL |
| `token_command` | string | — | Shell command to fetch token dynamically |

---

## `[github]`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `base_branch` | string | `"main"` | Target branch for PRs |

---

## `[daemon]`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `max_concurrent` | int | `1` | Max parallel issue executions |
| `lockfile_dir` | string | `".spec_orch_locks/"` | Lock file directory |
| `consume_state` | string | `"Ready"` | Linear state to poll |
| `require_labels` | list[str] | `[]` | Only process these labels |
| `exclude_labels` | list[str] | `["blocked", "needs-clarification"]` | Skip these labels |
| `skip_parents` | bool | `true` | Skip parent/epic issues |
| `max_retries` | int | `3` | Max retries before dead letter |
| `retry_base_delay_seconds` | int | `60` | Base delay for backoff |
| `hotfix_labels` | list[str] | `["hotfix", "urgent", "P0"]` | Hotfix mode labels |

---

## `[evolution]`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | `true` | Enable evolution system |
| `trigger_after_n_runs` | int | `5` | Runs before evolution triggers |
| `auto_promote` | bool | `false` | Auto-promote without review |

### Sub-sections

| Section | `enabled` default | Description |
|---------|-------------------|-------------|
| `[evolution.prompt_evolver]` | `true` | Evolve builder prompts |
| `[evolution.plan_strategy_evolver]` | `true` | Evolve planning strategies |
| `[evolution.harness_synthesizer]` | `true` (`dry_run: true`) | Synthesize compliance rules |
| `[evolution.policy_distiller]` | `false` | Distill gate policies |

---

## `[conversation]`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `default_channel` | string | — | Default discussion channel |

### `[conversation.slack]`

| Key | Type | Default |
|-----|------|---------|
| `bot_token_env` | string | — |
| `app_token_env` | string | — |

### `[conversation.linear]`

| Key | Type | Default |
|-----|------|---------|
| `watch_label` | string | — |
| `poll_interval_seconds` | int | `30` |

---

## Per-Language Templates

### Python

```toml
[verification]
lint = ["{python}", "-m", "ruff", "check", "src/"]
typecheck = ["{python}", "-m", "mypy", "src/"]
test = ["{python}", "-m", "pytest", "-q"]
build = ["{python}", "-c", "print('build ok')"]
```

### Node.js / TypeScript

```toml
[verification]
lint = ["npm", "run", "lint"]
typecheck = ["npx", "tsc", "--noEmit"]
test = ["npm", "test"]
build = ["npm", "run", "build"]
```

### Node.js (JavaScript only, no TypeScript)

```toml
[verification]
lint = ["npx", "eslint", "."]
test = ["npm", "test"]
build = ["npm", "run", "build"]
# typecheck omitted — treated as N/A, auto-passes gate
```

### Rust

```toml
[verification]
lint = ["cargo", "clippy", "--", "-D", "warnings"]
typecheck = ["cargo", "check"]
test = ["cargo", "test"]
build = ["cargo", "build"]
```

### Go

```toml
[verification]
lint = ["golangci-lint", "run"]
typecheck = ["go", "vet", "./..."]
test = ["go", "test", "./..."]
build = ["go", "build", "./..."]
```

### Java (Gradle)

```toml
[verification]
lint = ["./gradlew", "checkstyleMain"]
test = ["./gradlew", "test"]
build = ["./gradlew", "build"]
```

### Swift / iOS

```toml
[verification]
lint = ["swiftlint"]
test = ["swift", "test"]
build = ["swift", "build"]
```

### .NET (C# / F#)

```toml
[verification]
lint = ["dotnet", "format", "--verify-no-changes"]
test = ["dotnet", "test"]
build = ["dotnet", "build"]
```

### Docker-Based Verification

For projects that run everything inside Docker:

```toml
[verification]
lint = ["docker", "compose", "run", "--rm", "app", "npm", "run", "lint"]
test = ["docker", "compose", "run", "--rm", "app", "npm", "test"]
build = ["docker", "compose", "build"]
```

### Monorepo (Turborepo)

```toml
[verification]
lint = ["npx", "turbo", "run", "lint"]
typecheck = ["npx", "turbo", "run", "typecheck"]
test = ["npx", "turbo", "run", "test"]
build = ["npx", "turbo", "run", "build"]
```

### Monorepo (Nx)

```toml
[verification]
lint = ["npx", "nx", "run-many", "--target=lint"]
test = ["npx", "nx", "run-many", "--target=test"]
build = ["npx", "nx", "run-many", "--target=build"]
```

---

## Constraint Rules

1. When `adapter = "acpx"`, you should also set `agent` (defaults to `"opencode"`)
2. When `adapter = "acpx_<name>"`, do NOT set `agent` separately (it's implied)
3. When `[reviewer] adapter = "llm"`, `model` is required
4. When `[issue] source = "linear"`, `[linear]` section must be configured with valid `token_env`
5. `[verification]` steps are optional — omitted steps auto-pass the gate
6. The `{python}` token only works in `[verification]` commands, not in `[builder]`
7. `[planner] model` is required for AI-assisted planning (question answering, spec generation)

---

## Full Example: Python Project with ACPX + Linear

```toml
[issue]
source = "linear"

[linear]
token_env = "SPEC_ORCH_LINEAR_TOKEN"
team_key = "SON"
poll_interval_seconds = 30

[builder]
adapter = "acpx"
agent = "opencode"
model = "minimax/MiniMax-M2.5"
timeout_seconds = 900

[reviewer]
adapter = "llm"
model = "openai/gpt-4o"
api_key_env = "OPENAI_API_KEY"

[planner]
model = "anthropic/claude-sonnet-4-20250514"
api_key_env = "ANTHROPIC_API_KEY"

[verification]
lint = ["{python}", "-m", "ruff", "check", "src/"]
typecheck = ["{python}", "-m", "mypy", "src/"]
test = ["{python}", "-m", "pytest", "-q"]
build = ["{python}", "-c", "print('build ok')"]

[github]
base_branch = "main"

[daemon]
max_concurrent = 2
hotfix_labels = ["hotfix", "P0"]

[evolution]
enabled = true
trigger_after_n_runs = 10
```

## Full Example: Node.js Project with Codex + Fixture

```toml
[issue]
source = "fixture"

[builder]
adapter = "codex_exec"
timeout_seconds = 900

[reviewer]
adapter = "local"

[verification]
lint = ["npm", "run", "lint"]
typecheck = ["npx", "tsc", "--noEmit"]
test = ["npm", "test"]
build = ["npm", "run", "build"]

[github]
base_branch = "main"

[evolution]
enabled = false
```
