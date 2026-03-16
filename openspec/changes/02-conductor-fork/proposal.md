# 变更提案：Conductor Fork

> **Change**: 02-conductor-fork | **源 Issue**: SON-110

## 为何要做

Conductor 已具备 `_detect_drift()`（Jaccard 相似度）和 `IntentCategory.DRIFT`，但漂移和新意图仅影响当前 proposal 的累积逻辑，无法分流。用户在一次对话中混入多个话题或意图时，要么被迫手动切分，要么接受粒度粗糙的单一 proposal。自动 fork 可：

- 保持对话连贯性，不打断用户
- 为每个独立意图建立可追溯的 Issue，便于后续 flow 选择
- 与 Change 01 的 FlowType 体系衔接，新 Issue 自然进入 flow 路由

## 变更内容

1. **Fork 触发条件**  
   - 漂移检测：`_detect_drift()` 返回 true 且当前 signal 有可提取的 summary。  
   - 新可执行意图：当前处于 CRYSTALLIZE 或 EXECUTE 模式，且新 message 被分类为 actionable（confidence ≥ 0.6）。

2. **自动创建 Issue**  
   - 调用 `LinearClient.create_issue()`，title 来自 `IntentSignal.suggested_title` 或 `summary[:60]`。  
   - Description 包含：`source_thread_id`、`original_intent`（category + summary）、`conversation_excerpt`（最近 N 条消息摘要）。

3. **审计链**  
   - EventBus 发布 `EventTopic.CONDUCTOR`，payload 含 `action: "fork"`、`thread_id`、`linear_issue_id`、`intent_signal`。  
   - MemoryService 存储 Episodic Memory，tag 含 `conductor-fork`、`thread:{id}`、`linear:{identifier}`。  
   - Linear Issue 的 description 或 comment 中记录来源 thread，便于双向追溯。

4. **当前流不中断**  
   - Fork 为副作用，不修改 `ConductorState.mode`、`pending_proposal`。  
   - `process_message()` 的返回值不变，调用方无感知。

5. **新 Issue 进入独立 flow**  
   - 依赖 Change 01 的 FlowType 与 flow 选择逻辑；本 change 仅负责创建 Issue，不实现 flow 路由。

## 不做（Out of Scope）

- 跨 Issue 依赖编排、父子关系（Change 04）。
- Fork 前的用户确认弹窗（本阶段全自动，后续可加开关）。
- 去重/合并已 fork 的相似 Issue。
- 非 Linear 的 Issue 后端（如 GitHub Issues）。

## 影响范围

| 模块 | 影响 |
|------|------|
| `conductor/conductor.py` | 新增 `_maybe_fork()`，在 `process_message()` 中于 drift/新 intent 分支调用 |
| `conductor/types.py` | 可选：`ForkResult` 等轻量类型 |
| `linear_client.py` | 复用 `create_issue()`，可能扩展 description 模板 |
| `event_bus.py` | 复用 `EventTopic.CONDUCTOR`，定义 `fork` payload 结构 |
| `memory/service.py` | 复用 `store()`，新增 fork 专用 tag |
| 配置 | 可选：`SPEC_ORCH_FORK_ENABLED`、`SPEC_ORCH_FORK_TEAM`、`SPEC_ORCH_DRIFT_THRESHOLD` |

## 与 Change 01 的衔接

Change 01 定义 FlowType 及 flow 选择规则。本 change 创建的新 Issue 将具备：

- `intent_category`（来自 IntentSignal）
- `source_thread_id`（便于追溯）
- `conversation_excerpt`（上下文摘要）

这些字段可供 flow 选择器在后续调度时使用，实现「新 Issue 进入独立 flow」的语义。本 change 不实现 flow 路由逻辑，仅确保 Issue 创建时携带足够元数据。
