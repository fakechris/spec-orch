# 变更提案：Conductor 全生命周期拦截

> **Change**: 04-conductor-lifecycle | **源 Issue**: SON-98, SON-102

## 为何要做

Conductor 已具备意图分类（`classify_intent`）、漂移检测、crystallize 等能力，但仅在 `ConversationService` 内工作。DMA 的 build、verify、review、gate 阶段若出现用户意图，系统无法感知。将 Conductor 扩展为全生命周期拦截器可：

- 满足「DMA 在任意阶段识别用户意图」的产品目标
- 与 sdd-landscape-and-positioning 中「流程约束需机器强制」的结论一致
- 复用现有 `IntentClassifier`、`IntentSignal`，无需重写意图模型

## 变更内容

1. **Conductor 拦截接口**  
   - 新增 `intercept(stage: DMAStage, user_input: str, context: dict) -> InterceptResult`。  
   - `DMAStage` 枚举：`conversation`、`build`、`verify`、`review`、`gate`、`retro`。  
   - `InterceptResult` 含 `intent_signal`、`action`（`continue` | `pause` | `redirect` | `fork`）、`metadata`。

2. **RunController 集成点**  
   - 在 `_run_builder` 前后、`verification_service.run` 前后、`review_adapter` 调用前后、`gate_service.evaluate` 前，检查是否有「待处理的用户输入」。  
   - 若有，调用 `Conductor.intercept()`，根据 `action` 决定是否暂停、重定向或 fork。

3. **用户输入抽象**  
   - 定义 `UserInputSource`：可来自 Linear 评论、Slack 消息、CLI 输入、Webhook。  
   - RunController 不直接拉取外部输入，而是接收「注入的输入」；Daemon 或上层服务负责将 Linear/Slack 等聚合后传入。

4. **与 ConversationService 的关系**  
   - `ConversationService` 继续使用 `Conductor.process_message()` 处理对话。  
   - `intercept()` 为新增能力，供 RunController 等调用；两者共享 `classify_intent`。

5. **Fork 复用**  
   - 当 `intercept()` 返回 `action=fork` 时，复用 Change 02 的 `_maybe_fork()` 逻辑（若已实现），或在本 change 中实现最小 fork 路径。

## 不做（Out of Scope）

- 实现 Linear/Slack 等输入源的拉取逻辑（由 Daemon 或独立服务负责）。
- 跨 Issue 依赖编排。
- 修改 Gate 的评估逻辑本身，仅增加「gate 前可被 Conductor 拦截」的钩子。

## 影响范围

| 模块 | 影响 |
|------|------|
| `conductor/conductor.py` | 新增 `intercept()`，可选 `_intercept_to_action()` 辅助 |
| `conductor/types.py` | 新增 `DMAStage`、`InterceptResult`、`UserInputSource` |
| `run_controller.py` | 在 build/verify/review/gate 节点插入拦截调用 |
| `conversation_service.py` | 无变更，继续用 `process_message` |
| 配置 | 可选：`SPEC_ORCH_INTERCEPT_ENABLED`、`SPEC_ORCH_INTERCEPT_STAGES` |
