# acpx 项目分析报告

## 1. acpx 支持的 Agent 列表及 ACP 适配方式

### Native (内置命令，直接调用 ACP 模式)

| Agent | 命令 | 包装 |
|-------|------|------|
| openclaw | `openclaw acp` | OpenClaw ACP bridge |
| gemini | `gemini --acp` | Gemini CLI |
| cursor | `cursor-agent acp` | Cursor CLI |
| copilot | `copilot --acp --stdio` | GitHub Copilot CLI |
| droid | `droid exec --output-format acp` | Factory Droid |
| iflow | `iflow --experimental-acp` | iFlow CLI |
| kimi | `kimi acp` | Kimi CLI |
| kiro | `kiro-cli acp` | Kiro CLI |
| qwen | `qwen --acp` | Qwen Code |

### npm Adapter (通过 npx 拉取适配器)

| Agent | Adapter | 底层 Agent |
|-------|---------|------------|
| pi | `pi-acp` | Pi Coding Agent |
| codex | `@zed-industries/codex-acp` | Codex CLI |
| claude | `@zed-industries/claude-agent-acp` | Claude Code |
| kilocode | `@kilocode/cli acp` | Kilocode |
| opencode | `opencode-ai acp` | OpenCode |

**适配方式总结**：
- **native**: Agent 原生支持 `--acp` 参数，acpx 直接调用
- **npm adapter**: 通过社区适配器包桥接不支持 ACP 的 Agent

---

## 2. ACP 协议核心事件格式

### JSON Envelope 结构

```json
{
  "eventVersion": 1,
  "sessionId": "abc123",
  "requestId": "req-42",
  "seq": 7,
  "stream": "prompt",
  "type": "tool_call"
}
```

### 核心消息类型 (JSON-RPC 2.0)

| Method | 用途 |
|--------|------|
| `session/new` | 创建新会话 |
| `session/load` | 恢复已有会话 |
| `session/prompt` | 发送 prompt |
| `session/cancel` | 取消执行 |
| `session/set_mode` | 设置模式 |
| `session/set_config_option` | 设置配置 |

### 输出格式选项

- `text`: 人类可读流（含 tool status blocks）
- `json`: 原始 ACP NDJSON 流（每行一个 JSON-RPC 消息）
- `quiet`: 仅 assistant 文本

---

## 3. 与现有 BuilderAdapter 对比

### 现有 OpenCodeBuilderAdapter 模式

```
┌─────────────────────────────────────────────────────────┐
│                  OpenCodeBuilderAdapter                  │
├─────────────────────────────────────────────────────────┤
│ • 直接调用 `opencode run --format json`                 │
│ • JSONL 事件解析 (step_start, tool_use, text, step_finish) │
│ • map_events() → BuilderEvent 转换                      │
│ • session 管理: 无（每次 run 新进程）                    │
│ • 错误处理: returncode + state 追踪                     │
└─────────────────────────────────────────────────────────┘
```

### acpx 提供的增强

| 特性 | OpenCodeBuilderAdapter | acpx |
|------|------------------------|------|
| Session 持久化 | ❌ | ✅ `~/.acpx/sessions/` |
| 多会话并行 | ❌ | ✅ `-s <name>` |
| Prompt 队列 | ❌ | ✅ 自动排队 |
| 软关闭 | ❌ | ✅ `sessions close` |
| Crash 重连 | ❌ | ✅ 自动 respawn |
| Cancel 协调 | ❌ | ✅ `session/cancel` |
| 任意 Agent | 仅 OpenCode | 15+ Agents |

### 事件映射对比

```python
# OpenCodeBuilderAdapter.map_events()
if etype == "tool_use":
    tool = part.get("tool", "")
    if tool == "bash":
        BuilderEvent(kind="command_end", ...)
    elif tool in ("write", "edit"):
        BuilderEvent(kind="file_change", ...)

# acpx 输出 (raw ACP)
{"jsonrpc":"2.0","method":"tools/list",...}
{"jsonrpc":"2.0","method":"tools/call",...}
```

---

## 4. 集成方案建议：AcpxBuilderAdapter 接口设计

```python
class AcpxBuilderAdapter:
    """通过 acpx CLI 调用任意 ACP 兼容 Agent"""
    
    ADAPTER_NAME = "acpx"
    AGENT_NAME: str  # 可配置: codex, claude, pi, etc.
    
    def __init__(
        self,
        agent: str = "codex",
        session_name: str | None = None,
        timeout: int = 1800,
        permissions: str = "approve-reads",  # approve-all, deny-all
        format: str = "json",
    ):
        self.agent = agent
        self.session_name = session_name
        self.timeout = timeout
        self.permissions = permissions
        self.format = format
    
    def run(
        self,
        *,
        issue: Issue,
        workspace: Path,
        run_id: str | None = None,
        event_logger: Callable[[dict], None] | None = None,
    ) -> BuilderResult:
        # 1. 确保 session 存在: acpx {agent} sessions ensure -s {name}
        # 2. 发送 prompt: acpx {agent} {prompt} 或 acpx {agent} -s {name} {prompt}
        # 3. 解析 JSONL 输出 → BuilderEvent
        # 4. 处理 cancel/timeout
        ...
    
    def map_events(self, raw_events: list[dict]) -> list[BuilderEvent]:
        """将 ACP JSON-RPC 消息映射为 BuilderEvent"""
        # type: method → tools/call, tools/list, etc.
        # params: { tool, input, output, status }
        ...
```

### 关键设计决策

1. **Session 管理**: 使用 `sessions ensure` + `-s <name>` 实现多租户隔离
2. **权限控制**: 透传 `--approve-all` / `--deny-all` 参数
3. **事件解析**: 订阅 `tools/call` 方法，提取 tool name/input/output/status
4. **Cancel**: 调用 `acpx {agent} cancel` 发送 `session/cancel`
5. **Timeout**: 透传 `--timeout` 到 acpx 全局选项

---

## 5. 风险评估

### Alpha 状态风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| CLI 接口变更 | 破坏集成 | 锁定版本 `acpx@~0.3.0` |
| Agent 适配器 API 变化 | 事件格式失效 | 事件解析容错 + 版本检测 |
| Session 格式变更 | 状态恢复失败 | 定期清理 ~/.acpx/sessions |

### 依赖链风险

```
acpx → npx (npm) → @zed-industries/codex-acp → Codex CLI
                 → @zed-industries/claude-agent-acp → Claude Code
                 → pi-acp → Pi Coding Agent
```

- **问题**: 多层依赖，任意一层变更可能导致适配失败
- **建议**: 
  - 使用 `npx -y` 自动安装
  - 监控适配器版本变更
  - 优先使用 native agents (gemini, qwen, cursor 等)

### 协议变更影响

- ACP 仍处于发展中，核心方法 (`session/*`) 相对稳定
- 工具调用格式 (`tools/call`) 可能有变化
- **建议**: 事件解析层实现容错，忽略未知字段

---

## 6. 下一步

1. 试点: 先为 `codex` 创建 `AcpxBuilderAdapter`
2. 验证: 运行现有 test suite，确认事件映射正确
3. 扩展: 添加 `claude`, `gemini` 等 Agent 支持
4. 监控: 添加 acpx 版本检测和告警
