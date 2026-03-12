# Remote Discussion Adapters

## Goal

Enable spec-orch users to brainstorm and discuss requirements with the LLM planner
from outside the coding environment — via Slack threads, Linear issue comments, or
a local TUI — with all conclusions converging to the canonical `docs/specs/` spec.

The Discussion Layer is currently only available inside IDE sessions (Cursor / Claude Code).
This feature makes it accessible from mobile, Slack on the go, or Linear directly,
preserving the core principle: **discussion can happen anywhere, but the authoritative
spec lives only in `docs/specs/` inside the GitHub repo**.

## Scope

### In scope

- `ConversationAdapter` protocol — transport-agnostic interface for receiving and
  sending messages in a conversation thread
- `ConversationService` — core multi-turn brainstorming engine that routes messages
  to the LLM planner and manages thread state
- `ConversationMessage` / `ConversationThread` domain models
- `LiteLLMPlannerAdapter.brainstorm()` — multi-turn conversation mode (vs single-shot `plan()`)
- `LinearConversationAdapter` — polls Linear issue comments, replies via `add_comment()`
- `SlackConversationAdapter` — Slack Bolt + Socket Mode, thread-based interaction
- CLI `discuss` subcommand group for local TUI brainstorming
- `freeze` command — LLM summarises discussion → writes `docs/specs/<id>/spec.md` + `mission.json`
- Thread persistence in `.spec_orch_threads/` (JSON)
- Configuration in `spec-orch.toml` under `[conversation]`
- `slack-bolt` as optional dependency (`pip install spec-orch[slack]`)

### Out of scope

- Telegram, Discord, Lark adapters (future; protocol is designed for them)
- Web frontend / Canvas UI
- Webhook-based listeners (polling first; webhook is a deployment concern)
- Voice interactions
- Real-time streaming responses (batch reply only for v1)

## Acceptance Criteria

- ConversationAdapter protocol is defined and runtime-checkable
- ConversationService correctly routes messages to LLM and returns replies
- Thread state persists across process restarts (JSON files)
- `freeze` command generates a valid spec.md from conversation history
- LinearConversationAdapter polls for new comments and replies via API
- SlackConversationAdapter listens via Socket Mode and replies in threads
- `spec-orch discuss` provides interactive TUI brainstorming
- `spec-orch discuss --channel slack` starts Slack bot mode
- `spec-orch discuss --channel linear` starts Linear comment bot mode
- All new code has unit tests; existing tests continue to pass
- Slack dependency is optional (import guarded, extra in pyproject.toml)

## Constraints

- No new required dependencies — Slack/LiteLLM remain optional extras
- Linear integration reuses existing `LinearClient`; no separate HTTP client
- Thread persistence uses simple JSON files, not a database
- `ConversationAdapter.listen()` is blocking; adapters run in their own thread/process
- Bot must not respond to its own messages (loop prevention)
- All LLM calls go through the existing `LiteLLMPlannerAdapter` configuration

## Interface Contracts

### ConversationAdapter Protocol

```python
@runtime_checkable
class ConversationAdapter(Protocol):
    ADAPTER_NAME: str
    def listen(self, callback: Callable[[ConversationMessage], None]) -> None: ...
    def reply(self, thread_id: str, content: str) -> None: ...
    def stop(self) -> None: ...
```

### ConversationMessage

```python
@dataclass
class ConversationMessage:
    message_id: str
    thread_id: str
    sender: str         # "user" | "bot" | "planner"
    content: str
    timestamp: str
    channel: str        # "slack" | "linear" | "cli"
    metadata: dict[str, Any]
```

### ConversationThread

```python
@dataclass
class ConversationThread:
    thread_id: str
    channel: str
    mission_id: str | None
    messages: list[ConversationMessage]
    status: str         # "active" | "frozen" | "archived"
    spec_snapshot: str | None
    created_at: str
```

### LiteLLMPlannerAdapter.brainstorm()

```python
def brainstorm(
    self,
    *,
    conversation_history: list[dict[str, str]],
    codebase_context: str = "",
) -> str:
```

### spec-orch.toml schema

```toml
[conversation]
default_channel = "slack"

[conversation.slack]
bot_token_env = "SLACK_BOT_TOKEN"
app_token_env = "SLACK_APP_TOKEN"

[conversation.linear]
watch_label = "spec-orch"
poll_interval_seconds = 30
```
