# 需求规格：Conductor 全生命周期拦截

> **Change**: 04-conductor-lifecycle | **依赖**: 01-scaffold-flow-engine, 02-conductor-fork

## 1. Conductor 拦截接口

| 需求 | 描述 |
|------|------|
| **R1.1** 接口签名 | `intercept(stage: DMAStage, user_input: str, context: dict[str, Any]) -> InterceptResult`。 |
| **R1.2** DMAStage | 枚举值：`conversation`、`build`、`verify`、`review`、`gate`、`retro`。 |
| **R1.3** InterceptResult | 含 `intent_signal: IntentSignal`、`action: Literal["continue", "pause", "redirect", "fork"]`、`metadata: dict`。 |
| **R1.4** 复用 classify_intent | `intercept()` 内部调用 `classify_intent(user_input, conversation_history=context.get("history", []), planner=...)`。 |

## 2. RunController 集成点

| 需求 | 描述 |
|------|------|
| **R2.1** 注入点 | RunController 接收可选 `user_input_provider: Callable[[], str | None]`，在关键节点调用获取待处理输入。 |
| **R2.2** Build 节点 | `_run_builder` 前、后各一次拦截检查；若 `action in ("pause", "redirect", "fork")`，中断或重定向。 |
| **R2.3** Verify 节点 | `verification_service.run` 前、后各一次；逻辑同 R2.2。 |
| **R2.4** Review 节点 | `review_adapter` 调用前、后各一次；逻辑同 R2.2。 |
| **R2.5** Gate 节点 | `gate_service.evaluate` 前一次；若 `action != "continue"`，可跳过 gate 或先执行路由动作。 |
| **R2.6** 无输入时零开销 | `user_input_provider` 返回 `None` 或空串时，不调用 `intercept()`，直接继续原流程。 |

## 3. 用户输入抽象

| 需求 | 描述 |
|------|------|
| **R3.1** UserInputSource | 类型定义：`source: str`（如 `linear_comment`、`slack`、`cli`）、`content: str`、`timestamp: str`。 |
| **R3.2** 输入聚合 | RunController 不实现聚合；调用方（Daemon、CLI 包装）负责将多源输入合并为单一 `user_input` 字符串传入。 |
| **R3.3** 去重 | 同一 `source` + `content` 哈希在 60 秒内不重复触发 `intercept()`。 |

## 4. 动作语义

| 需求 | 描述 |
|------|------|
| **R4.1** continue | 无变更，继续当前阶段。 |
| **R4.2** pause | 暂停当前 run，将控制权交回调用方；RunController 返回 `RunState.PAUSED` 或等价状态。 |
| **R4.3** redirect | 重定向到指定阶段或 Issue；`metadata` 含 `target_stage` 或 `target_issue_id`。 |
| **R4.4** fork | 复用 Change 02 的 fork 逻辑，创建新 Issue；`metadata` 含 `fork_result`。 |

## 5. 与 ConversationService 的兼容

| 需求 | 描述 |
|------|------|
| **R5.1** 无冲突 | `ConversationService` 继续使用 `process_message()`；`intercept()` 仅在非 conversation 阶段使用。 |
| **R5.2** 共享状态 | `intercept()` 可读取 `ConductorState`（若 thread_id 在 context 中），但不修改 `pending_proposal` 等对话状态。 |

## 6. 配置与开关

| 需求 | 描述 |
|------|------|
| **R6.1** 开关 | `SPEC_ORCH_INTERCEPT_ENABLED`（默认 true）控制是否启用拦截。 |
| **R6.2** 阶段过滤 | `SPEC_ORCH_INTERCEPT_STAGES` 逗号分隔，如 `build,gate`，仅这些阶段启用拦截；空则全部启用。 |

## 7. 边界场景

| 场景 | 处理策略 |
|------|----------|
| **S7.1** 拦截时 LLM 不可用 | 降级为 `action=continue`，记录 warning，不阻塞。 |
| **S7.2** 同一阶段多次拦截 | 每次有输入即调用，去重由 R3.3 保证。 |
| **S7.3** fork 时 Linear 不可用 | 与 Change 02 一致：降级为本地占位，待同步。 |
