# 需求规格：Conductor Fork

> **Change**: 02-conductor-fork | **依赖**: 01-scaffold-flow-engine（FlowType 定义）

## 1. Fork 触发条件

| 条件 | 描述 | 优先级 |
|------|------|--------|
| **R1.1** 漂移检测 | `_detect_drift(state, signal)` 返回 true，且 `signal.summary` 非空。 | P0 |
| **R1.2** 新可执行意图 | 当前 `state.mode` 为 CRYSTALLIZE 或 EXECUTE，且新 message 的 `IntentSignal` 满足 `is_actionable()`。 | P0 |

满足任一条件即触发 fork，不重复 fork 同一 signal（通过 `state.forked_intent_ids` 或等价机制去重）。

## 2. 自动创建 Issue 内容

| 需求 | 描述 |
|------|------|
| **R2.1** 来源 thread | Description 中必须包含 `source_thread_id`，格式如 `Source: thread:{thread_id}`。 |
| **R2.2** 原始意图 | 包含 `original_intent`：`category` + `summary`，便于后续 flow 选择。 |
| **R2.3** 对话摘要 | 包含 `conversation_excerpt`：最近 3–5 条消息的截断摘要（每条约 100 字符），便于人工理解上下文。 |
| **R2.4** Title | 优先使用 `IntentSignal.suggested_title`，否则 `summary[:60]`，空则 `"Forked from conversation"`。 |

## 3. 审计链

| 需求 | 描述 |
|------|------|
| **R3.1** EventBus | 发布 `Event(topic=CONDUCTOR, payload={action: "fork", thread_id, linear_issue_id, intent_signal, ...})`。 |
| **R3.2** Episodic Memory | `MemoryService.store()` 写入 `MemoryLayer.EPISODIC`，tags 含 `conductor-fork`、`thread:{id}`、`linear:{identifier}`。 |
| **R3.3** Linear 关联 | Issue description 或首条 comment 记录来源 thread，支持从 Linear 反查对话。 |

## 4. 当前流不中断

| 需求 | 描述 |
|------|------|
| **R4.1** 无状态篡改 | Fork 不修改 `state.mode`、`state.pending_proposal`、`state.intent_history`。 |
| **R4.2** 返回值不变 | `process_message()` 的 `ConductorResponse` 与无 fork 时一致，调用方无需特殊分支。 |
| **R4.3** 异步友好 | Fork 为同步副作用，若未来改为异步，需保证不阻塞主流程。 |

## 5. 新 Issue 进入独立 flow

| 需求 | 描述 |
|------|------|
| **R5.1** 创建即完成 | 本 change 仅负责创建 Linear Issue，不实现 flow 路由。 |
| **R5.2** 与 Change 01 衔接 | 新 Issue 的 metadata（intent_category 等）可供 FlowType 映射使用，由 Change 01/04 消费。 |

## 6. 错误处理

| 需求 | 描述 |
|------|------|
| **R6.1** Linear API 失败 | 捕获异常，记录日志，可选：EventBus 发布 `conductor.fork.failed`。不抛出，不影响主流程。 |
| **R6.2** 限流 | 若 Linear 返回 429，实现指数退避重试（最多 2 次），仍失败则降级为本地占位（写入 `.spec_orch_conductor/forks.jsonl`），待后续同步。 |
| **R6.3** 无 token | `LinearClient` 未配置时，跳过 fork，记录 debug 日志，不报错。 |

## 7. 边界场景

| 场景 | 处理策略 |
|------|----------|
| **S7.1** 短时间内多次 fork | 同一 thread 内，相同 `intent_signal`（基于 summary 哈希）60 秒内不重复 fork。 |
| **S7.2** Fork 期间再 fork | 串行处理：先完成当前 fork（含 Linear + EventBus + Memory），再评估下一轮。不嵌套。 |
| **S7.3** 漂移 + 新意图同时满足 | 仅触发一次 fork，以漂移为优先（因漂移通常意味着更明确的话题切换）。 |
| **S7.4** Fork 时无 `suggested_title` 且 `summary` 为空 | 使用 `"Forked from conversation"` 作为 title，description 仍包含 thread_id 与 excerpt。 |

## 8. 场景验收

- **场景 A（漂移）**：用户从「登录页」切到「支付退款」，系统创建新 Issue，原对话继续。
- **场景 B（新意图）**：用户在执行中补充「顺便修 CSV 编码」，系统 fork 新 Issue，当前 flow 不变。
- **场景 C（探索结晶）**：用户连续提暗色主题、多语言、移动端，系统可为每个 fork，或按现有 crystallize 逻辑合并，由实现选择（本 change 不强制多 fork，仅支持能力）。
