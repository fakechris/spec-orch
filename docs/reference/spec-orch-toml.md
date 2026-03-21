# spec-orch.toml Configuration Reference

Complete reference for the `spec-orch.toml` configuration file.

## [issue]

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `source` | string | `"fixture"` | Issue source: `fixture`, `linear` (extensible via `register_issue_source()`) |

When `source = "fixture"`, issues are loaded from `fixtures/issues/<id>.json`.
When `source = "linear"`, the `[linear]` section must be configured.

## [verification]

Defines the shell commands for each verification step.  **Any key** in this
section is treated as a verification step — you are not limited to the four
standard names.  Omitted steps are treated as "not applicable" and
automatically pass the gate.

### Standard steps

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `lint` | list[string] | — | Lint command (e.g., `["{python}", "-m", "ruff", "check", "src/"]`) |
| `typecheck` | list[string] | — | Type check command |
| `test` | list[string] | — | Test command |
| `build` | list[string] | — | Build command |

### Custom steps (examples)

```toml
[verification]
lint = ["make", "lint"]
test = ["make", "test"]
security_scan = ["npm", "audit", "--production"]
e2e = ["make", "e2e-test"]
docker_test = ["docker", "compose", "run", "--rm", "test"]
format_check = ["cargo", "fmt", "--check"]
```

If the entire `[verification]` section is absent, no verification steps are
run (all steps pass by default).  Use `spec-orch init` to auto-detect the
appropriate commands for your project.

The token `{python}` is replaced with the current Python interpreter at runtime.

### Monorepo / multi-language projects

For monorepo setups, use composite commands that test all sub-projects:

```toml
[verification]
lint = ["make", "lint-all"]
test = ["make", "test-all"]
build = ["make", "build-all"]
```

Or use `spec-orch init` with LLM analysis (default mode) to auto-detect
the project structure and generate appropriate commands.

See `docs/guides/ai-config-guide.md` for per-language templates.

## [linear]

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `token_env` | string | `"SPEC_ORCH_LINEAR_TOKEN"` | Environment variable name containing the Linear API token |
| `team_key` | string | `"SPC"` | Linear team key for issue queries |
| `poll_interval_seconds` | int | `60` | Daemon polling interval |
| `issue_filter` | string | `"assigned_to_me"` | Issue filter strategy |

## [builder]

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `adapter` | string | `"codex_exec"` | Builder adapter: `codex_exec`, `opencode`, `droid`, `claude_code`, `acpx`, `acpx_<agent>` |
| `executable` | string | varies | Path to the builder CLI executable (`codex`, `opencode`, `npx` for acpx) |
| `model` | string | — | Model override for adapters that support it (e.g. `minimax/MiniMax-M2.5`) |
| `timeout_seconds` | int | `1800` | Builder execution timeout |
| `agent` | string | `"opencode"` | (ACPX only) Target agent: `opencode`, `codex`, `claude`, `gemini`, `droid`, etc. |
| `session_name` | string | — | (ACPX only) Named session for persistence and resume |
| `permissions` | string | `"full-auto"` | (ACPX only) Permission mode: `full-auto`, `approve-reads`, etc. |
| `acpx_package` | string | `"acpx"` | (ACPX only) npm package name |

## [reviewer]

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `adapter` | string | `"local"` | Reviewer adapter: `local`, `llm`, `github` |
| `model` | string | — | LLM model for `llm` adapter (e.g. `openai/gpt-4o`, `minimax/MiniMax-M2.5`) |
| `api_key_env` | string | — | Environment variable for reviewer API key |
| `api_base_env` | string | — | Environment variable for reviewer API base URL |
| `temperature` | float | `0.2` | LLM temperature for review calls |
| `max_diff_chars` | int | `60000` | Maximum diff characters sent to LLM |
| `max_spec_chars` | int | `10000` | Maximum spec characters sent to LLM |

## [planner]

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `model` | string | — | LLM model for planning. Full provider/model string (e.g. `anthropic/claude-sonnet-4-20250514`) or bare name auto-prefixed with `api_type` |
| `api_type` | string | `"anthropic"` | API type: `anthropic`, `openai` |
| `api_key_env` | string | — | Environment variable for planner API key |
| `api_base_env` | string | — | Environment variable for planner API base URL |
| `token_command` | string | — | Shell command to fetch API token dynamically |

## [github]

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `base_branch` | string | `"main"` | Target branch for PRs |

## [daemon]

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `max_concurrent` | int | `1` | Maximum concurrent issue executions |
| `lockfile_dir` | string | `".spec_orch_locks/"` | Directory for lock files and daemon state |
| `consume_state` | string | `"Ready"` | Linear state to poll for new issues |
| `require_labels` | list[str] | `[]` | Only process issues with these labels |
| `exclude_labels` | list[str] | `["blocked", "needs-clarification"]` | Skip issues with these labels |
| `skip_parents` | bool | `true` | Skip parent/epic issues |
| `max_retries` | int | `3` | Maximum retry attempts before dead letter |
| `retry_base_delay_seconds` | int | `60` | Base delay for exponential backoff (seconds) |
| `hotfix_labels` | list[str] | `["hotfix", "urgent", "P0"]` | Labels that trigger hotfix mode (skip triage) |

## [memory]

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `provider` | string | `"filesystem"` | Memory provider: `"filesystem"` (file-only) or `"filesystem_qdrant"` (file + Qdrant semantic index) |

When `provider = "filesystem_qdrant"`, the `[memory.qdrant]` section must be configured.
When `provider = "filesystem"` (or section omitted), only filesystem-based recall is used.

### [memory.qdrant]

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `mode` | string | `"local"` | Qdrant mode: `"local"` (on-disk), `"memory"` (in-memory, dev/test), `"server"` (remote Qdrant server) |
| `path` | string | `".spec_orch_qdrant"` | Local storage path for `mode = "local"` |
| `url` | string | — | Qdrant server URL for `mode = "server"` (e.g. `"http://localhost:6333"`) |
| `collection` | string | `"spec_orch_memory"` | Qdrant collection name |
| `embedding_model` | string | `"BAAI/bge-small-zh-v1.5"` | FastEmbed model for local embedding generation |

Requires the `memory` optional extra: `pip install "spec-orch[memory]"`.
The local embedding model (~90 MB) is auto-downloaded on first use.
If Qdrant initialization fails, the system silently degrades to filesystem-only mode.

See [ADR-0001](../adr/0001-memory-architecture.md) for architecture details.

## [evolution]

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | `true` | Enable/disable the evolution system |
| `trigger_after_n_runs` | int | `5` | Trigger evolution cycle after N runs |
| `auto_promote` | bool | `false` | Auto-promote evolved prompts without review |

### [evolution.prompt_evolver]

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | `true` | Enable prompt evolution |

### [evolution.plan_strategy_evolver]

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | `true` | Enable plan strategy hints generation |

### [evolution.harness_synthesizer]

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | `true` | Enable compliance rule synthesis |
| `dry_run` | bool | `true` | Only propose rules, don't apply |

### [evolution.policy_distiller]

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | `false` | Enable policy distillation |

## Example (Direct Adapter)

```toml
[linear]
token_env = "SPEC_ORCH_LINEAR_TOKEN"
team_key = "SON"
poll_interval_seconds = 30

[builder]
adapter = "opencode"
executable = "opencode"
model = "minimax/MiniMax-M2.5"
timeout_seconds = 900

[reviewer]
adapter = "llm"
model = "openai/MiniMax-M2.5"
api_key_env = "MINIMAX_API_KEY"
api_base_env = "SPEC_ORCH_LLM_API_BASE_OPENAI"

[planner]
model = "anthropic/claude-sonnet-4-20250514"
api_type = "anthropic"
api_key_env = "ANTHROPIC_API_KEY"

[github]
base_branch = "main"

[daemon]
max_concurrent = 2
max_retries = 5
retry_base_delay_seconds = 120
hotfix_labels = ["hotfix", "P0"]

[evolution]
enabled = true
trigger_after_n_runs = 10
auto_promote = false

[evolution.prompt_evolver]
enabled = true

[evolution.plan_strategy_evolver]
enabled = true

[evolution.harness_synthesizer]
dry_run = false

[evolution.policy_distiller]
enabled = false
```

## Example (Memory with Qdrant)

```toml
[memory]
provider = "filesystem_qdrant"

[memory.qdrant]
mode = "local"
path = ".spec_orch_qdrant"
collection = "spec_orch_memory"
embedding_model = "BAAI/bge-small-zh-v1.5"
```

For dev/test, use `mode = "memory"` (no disk persistence).
For a remote Qdrant server, use `mode = "server"` with `url = "http://localhost:6333"`.

## Example (ACPX Unified Adapter)

```toml
[linear]
token_env = "SPEC_ORCH_LINEAR_TOKEN"
team_key = "SON"

[builder]
adapter = "acpx"
agent = "opencode"
model = "minimax/MiniMax-M2.5"
timeout_seconds = 900

# Shortcut: adapter = "acpx_codex" is equivalent to adapter = "acpx" + agent = "codex"

[reviewer]
adapter = "llm"
model = "openai/gpt-4o"

[daemon]
max_concurrent = 1
```
