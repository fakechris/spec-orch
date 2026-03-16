# PRD: Conductor Fork — 对话漂移/新意图时自动创建 Issue

> **Linear**: SON-110 | **Change**: 02-conductor-fork | **依赖**: 01-scaffold-flow-engine

## 背景

Conductor 是 spec-orch 的渐进式形式化层，负责在自由对话（explore）与结构化工作（execute）之间架桥。当前实现中，当检测到**话题漂移**（drift）时，系统仅将 `IntentSignal` 标记为 `IntentCategory.DRIFT`，但不产生任何后续动作。用户若在讨论 A 时突然转向 B，或在一个对话中混入多个可执行意图，现有流程无法自动分流，导致：

- 对话上下文混杂，难以追溯「哪个意图对应哪条 Issue」
- 用户需手动切分话题或新建 Issue，体验割裂
- 探索阶段结晶出的多个独立需求被合并到单一 proposal，粒度失控

## 问题

1. **漂移无出口**：`_detect_drift()` 已能识别话题切换，但无下游动作。
2. **多意图同流**：当前流程假设一个 thread 对应一个 proposal；若用户在处理 A 时提出新的可执行意图 B，B 会被忽略或混入 A。
3. **探索结晶粒度粗**：用户在一次对话中探索多个方向，最终希望拆成多个独立 Issue，但系统只支持单一 proposal。

## 目标

- 当检测到**漂移**或**新的可执行意图**时，自动创建 Linear Issue，并将该 Issue 纳入独立流程选择。
- 当前对话流**不中断**，继续处理原上下文。
- 提供可追溯的审计链：EventBus 事件、Episodic Memory、Linear 关联。

## 非目标

- 不改变 Conductor 的 explore → crystallize → execute 主流程。
- 不实现跨 Issue 的依赖编排（由 Change 04 负责）。
- 不自动合并或去重已 fork 的 Issue（人工决策）。

## 用户场景

### 场景 1：漂移到新话题

用户在讨论「登录页重构」时，突然说「对了，支付模块的退款逻辑也有问题」。系统检测到 Jaccard 相似度低于阈值，判定为 drift。自动创建新 Issue「支付模块退款逻辑」，包含来源 thread ID、原始意图摘要、相关对话片段。原对话继续围绕登录页，用户可稍后在 Linear 中处理新 Issue。

### 场景 2：当前处理中冒出新的可执行意图

用户已 approve 一个 quick_fix，正在执行。此时用户补充「顺便把导出 CSV 的编码问题也修一下」。系统识别为新的 actionable intent，自动 fork 出新 Issue，当前 flow 继续执行原 quick_fix，新 Issue 进入独立 flow 选择。

### 场景 3：探索结晶为多个独立功能

用户在 explore 模式下连续提出「加个暗色主题」「支持多语言」「优化移动端布局」。系统在积累到阈值时，可为每个方向 fork 出独立 Issue，而非合并为一个 epic proposal，便于用户分别 approve 或搁置。

## 成功指标

- Fork 触发后，Linear 中可见新 Issue，且包含 `source_thread_id`、`original_intent`、`conversation_excerpt`。
- EventBus 发布 `conductor.fork` 事件，MemoryService 记录 Episodic Memory。
- 原 thread 的 Conductor 状态不变，无 mode 切换，无 proposal 覆盖。
- Linear API 失败或限流时，有明确错误提示与重试/降级策略。

## 风险

- **过度 fork**：漂移阈值过敏感会导致频繁创建琐碎 Issue。缓解：可配置阈值、最小间隔、用户确认开关。
- **Linear 依赖**：无 token 或 API 不可用时，fork 失败。缓解：降级为本地占位 Issue，待连通后同步。
- **审计链断裂**：EventBus 或 Memory 写入失败时，Linear Issue 已创建但无法追溯。缓解：先写本地日志，再异步补写审计记录。

## 附录：与现有组件的衔接

- `_detect_drift()`：沿用现有 Jaccard 阈值（0.15），可经环境变量覆盖。
- `IntentCategory.DRIFT`：已存在，fork 时复用。
- `LinearClient.create_issue()`：已支持 team_key、title、description，可直接调用。
- `EventTopic.CONDUCTOR`：已存在，扩展 payload 即可。
