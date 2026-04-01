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

## Recommended LLM Configuration Shape

Use three layers for LiteLLM-powered roles:

1. `[models.<id>]` defines provider/model/env once
2. `[model_chains.<id>]` defines primary + fallback order
3. `[llm].default_model_chain` lets empty role sections inherit a working chain

```toml
[llm]
default_model_chain = "default_reasoning"

[models.minimax_reasoning]
model = "MiniMax-M2.7-highspeed"
api_type = "anthropic"
api_key_env = "MINIMAX_API_KEY"
api_base_env = "MINIMAX_ANTHROPIC_BASE_URL"

[models.fireworks_kimi]
model = "accounts/fireworks/routers/kimi-k2p5-turbo"
api_type = "anthropic"
api_key_env = "ANTHROPIC_AUTH_TOKEN"
api_base_env = "ANTHROPIC_BASE_URL"

[model_chains.default_reasoning]
primary = "minimax_reasoning"
fallbacks = ["fireworks_kimi"]

[planner]

[supervisor]
adapter = "litellm"

[acceptance_evaluator]
adapter = "litellm"
```

Resolution order:

1. role `model_chain`
2. role `model_ref`
3. role inline `model/api_* / fallbacks`
4. `[llm].default_model_chain`
5. `[llm].default_model_ref`
6. provider env fallback chain

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

Mission round-loop note:
- when `[supervisor]` is enabled, mission workers use ACPX session ids like `mission-<mission_id>-<packet_id>`
- this is separate from `[builder].session_name`, which still controls the single-issue builder path

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

## `[supervisor]` — Mission Round Review

Enables the mission execute-review-decide loop. This is used by mission execution in the daemon path, not by the single-issue `spec-orch run` path.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `adapter` | string | — | `litellm` |
| `model_chain` | string | inherits `[llm].default_model_chain` | Named chain |
| `model_ref` | string | inherits `[llm].default_model_ref` | Named single model |
| `model` | string | — | Model used for round review |
| `api_key_env` | string | — | Environment variable for supervisor API key |
| `api_base_env` | string | — | Environment variable for supervisor API base |
| `max_rounds` | int | `20` | Maximum mission rounds before fail-fast |

### Multi-Model Pattern

Fail over only on transient provider failures such as `429`, `529`, overload,
timeout, or temporary unavailability. Do not fail over on invalid credentials
or missing base URL.

---

## `[reviewer]` — Review Adapter

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `adapter` | string | `"local"` | `local` or `llm` |
| `model_chain` | string | inherits `[llm].default_model_chain` | Named chain for `llm` adapter |
| `model_ref` | string | inherits `[llm].default_model_ref` | Named single model |
| `model` | string | — | LLM model (for `llm` adapter) |
| `api_key_env` | string | — | Env var for API key |
| `api_base_env` | string | — | Env var for API base URL |

---

## `[planner]` — LLM Planner

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `model_chain` | string | inherits `[llm].default_model_chain` | Named chain |
| `model_ref` | string | inherits `[llm].default_model_ref` | Named single model |
| `model` | string | — | Full `provider/model` string |
| `api_type` | string | `"anthropic"` | `anthropic` or `openai` |
| `api_key_env` | string | — | Env var for API key |
| `api_base_env` | string | — | Env var for API base URL |
| `token_command` | string | — | Shell command to fetch token dynamically |

If `[planner]` is empty, it still works when `[llm].default_model_chain` or
`[llm].default_model_ref` is configured.

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

---

## Multi-Model Checklist

When an AI assistant configures spec-orch, prefer this checklist:

1. Verify the primary model works on its own.
2. Add one shared chain instead of repeating per-role fallback blocks.
3. Ensure each model definition has both:
   - `api_key_env`
   - `api_base_env`
4. Prefer Anthropic-compatible chains for Anthropic-compatible primaries.
5. Treat auth/config failures as setup bugs, not retry/fallback events.

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
3. When `[reviewer] adapter = "llm"`, the reviewer needs a resolvable model via
   `model_chain`, `model_ref`, inline `model`, or `[llm]` defaults
4. When `[issue] source = "linear"`, `[linear]` section must be configured with valid `token_env`
5. `[verification]` steps are optional — omitted steps auto-pass the gate
6. The `{python}` token only works in `[verification]` commands, not in `[builder]`
7. `[planner]` needs a resolvable model via section override or `[llm]` defaults
8. `[supervisor]` needs a resolvable model via section override or `[llm]` defaults if you want daemon mission execution to use the supervised round loop

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
adapter = "acpx_codex"
model = "gpt-5-codex"
timeout_seconds = 900

[reviewer]
adapter = "llm"
model = "openai/gpt-4o"
api_key_env = "OPENAI_API_KEY"

[planner]
model = "anthropic/claude-sonnet-4-20250514"
api_key_env = "ANTHROPIC_API_KEY"

[supervisor]
adapter = "litellm"
model = "openai/gpt-4o"
api_key_env = "OPENAI_API_KEY"
max_rounds = 12

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
