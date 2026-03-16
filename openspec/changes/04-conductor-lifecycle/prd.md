# PRD: Conductor 全生命周期拦截

> **Linear**: SON-98, SON-102 | **Change**: 04-conductor-lifecycle | **依赖**: 01-scaffold-flow-engine, 02-conductor-fork

## 背景

Conductor 是 spec-orch 的渐进式形式化层，负责在自由对话与结构化执行之间架桥。当前实现中，Conductor **仅**在 `ConversationService.handle_message()` 内工作——即用户通过对话与系统交互时才会触发意图识别与路由。DMA（开发管理代理）的完整生命周期包含 build、verify、review、gate 等阶段，这些阶段若出现用户意图（如「先别 merge，我改下 spec」），系统无法识别并路由。

sdd-landscape-and-positioning.md 指出：流程约束不能只靠上下文，需要机器强制；同时 DMA 跳过流程的实战发现表明，Conductor 必须在**任意阶段**都能识别用户意图并做出响应。

## 问题

1. **意图识别范围窄**：Conductor 仅在 conversation 阶段介入，build/verify/review/gate 阶段无意图感知。
2. **DMA 生命周期割裂**：用户在执行中（如 gate 前）提出新需求或变更指令，系统无法分流，只能继续原流程或失败。
3. **单模块耦合**：Conductor 与 ConversationService 强绑定，RunController、GateService 等无法复用其意图分类能力。

## 目标

- DMA 在**任意阶段**（build、verify、review、gate、retro）都能识别用户意图并路由。
- Conductor 从「仅对话服务内」扩展为「全 DMA 生命周期拦截器」。
- 保持 Conductor 单模块职责：意图分类 + 路由建议，不承担执行逻辑。

## 非目标

- 不改变 Conductor 的 explore → crystallize → execute 主流程。
- 不实现跨 Issue 依赖编排（由其他 change 负责）。
- 不替换 RunController 的编排逻辑，仅在其关键节点插入 Conductor 拦截点。

## 用户场景

### 场景 1：Build 阶段用户说「先停，改下 scope」

用户通过 DMA 启动 build，执行中在 Slack/Linear 评论中写「先停，scope 要缩小」。系统在下一轮轮询或事件触发时，Conductor 识别为「暂停/变更意图」，路由到 pause 或 redirect，而非继续 build。

### 场景 2：Gate 前用户补充验收标准

Gate 即将评估时，用户在 spec 评论中补充「还要检查导出 CSV 的编码」。Conductor 在 gate 前拦截，识别为「spec 变更意图」，触发 spec 更新流程或新建子 Issue，而非直接 gate。

### 场景 3：Review 阶段用户说「这个可以 merge」

Review 进行中，用户回复「这个可以 merge」。Conductor 识别为「加速/批准意图」，可路由到跳过部分 review 或提前触发 gate（若 policy 允许）。

## 成功指标

- RunController 在 build/verify/review/gate 的关键节点调用 Conductor 拦截接口。
- Conductor 能接收「当前阶段 + 用户输入」并返回 `IntentSignal` 与路由建议。
- 当意图为「继续」或「无明确变更」时，不改变原有流程，零侵入。
- 当意图为「暂停/变更/分流」时，有明确的路由动作（pause、redirect、fork 等）供 RunController 消费。

## 风险

- **性能**：每个阶段都调 Conductor 可能增加 LLM 调用。缓解：仅在「有用户输入」时调用，或支持批量/异步。
- **上下文边界**：build 阶段的「用户输入」可能来自 Linear 评论、Slack、CLI，需统一输入抽象。
- **与 Change 02 的衔接**：Fork 逻辑已在 ConversationService 内，全生命周期拦截需复用同一套 fork 触发条件。
