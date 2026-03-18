# spec-orch.toml Configuration Reference

Complete reference for the `spec-orch.toml` configuration file.

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
| `adapter` | string | `"codex_exec"` | Builder adapter: `codex_exec`, `opencode`, `droid`, `claude_code` |
| `executable` | string | `"codex"` | Path to the builder CLI executable |
| `model` | string | — | Model override for adapters that support it (e.g. `minimax/MiniMax-M2.5`) |
| `timeout_seconds` | int | `1800` | Builder execution timeout |

## [reviewer]

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `adapter` | string | `"local"` | Reviewer adapter: `local`, `llm`, `github` |
| `model` | string | — | LLM model for `llm` adapter (e.g. `openai/gpt-4o`, `minimax/MiniMax-M2.5`) |
| `api_key_env` | string | — | Environment variable for reviewer API key |
| `api_base_env` | string | — | Environment variable for reviewer API base URL |

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

## Example

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
