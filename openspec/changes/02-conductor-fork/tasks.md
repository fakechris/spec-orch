# 任务清单：Conductor Fork

> **Change**: 02-conductor-fork | **无 design.md**：本变更仅涉及 Conductor 单模块内逻辑扩展，不涉及跨模块架构设计，故跳过 design 阶段。

## 前置

- [ ] Change 01（scaffold-flow-engine）已合并或可并行开发，FlowType 定义可用。

## 实现任务

### 1. Fork 逻辑

- [ ] 在 `conductor.py` 中实现 `_maybe_fork(state, signal, thread)`，封装触发判断与 Issue 创建。
- [ ] 在 `process_message()` 的 drift 分支（`signal.category == DRIFT`）后调用 `_maybe_fork()`。
- [ ] 在 `process_message()` 的 CRYSTALLIZE/EXECUTE 分支中，当新 signal 为 actionable 时调用 `_maybe_fork()`。
- [ ] 实现去重：`state.forked_intent_ids` 或基于 `(summary_hash, timestamp)` 的 60 秒防抖。

### 2. Issue 创建

- [ ] 构造 fork 专用 description 模板：`source_thread_id`、`original_intent`、`conversation_excerpt`。
- [ ] 调用 `LinearClient.create_issue()`，team 从 `SPEC_ORCH_FORK_TEAM` 或默认配置读取。
- [ ] 无 Linear token 时优雅跳过，不抛错。

### 3. 审计链

- [ ] 在 fork 成功后发布 `EventTopic.CONDUCTOR`，payload 含 `action: "fork"`、`thread_id`、`linear_issue_id`、`intent_signal`。
- [ ] 调用 `MemoryService.store()` 写入 Episodic Memory，tags 含 `conductor-fork`、`thread:{id}`、`linear:{identifier}`。
- [ ] 确保 Linear Issue description 或首条 comment 包含来源 thread 信息。

### 4. 错误处理

- [ ] 捕获 `LinearClient` 调用异常，记录日志，不向上抛出。
- [ ] 实现 429 限流时的指数退避（最多 2 次重试）。
- [ ] 可选：失败时写入 `.spec_orch_conductor/forks.jsonl` 作为待同步队列。

### 5. 配置与类型

- [ ] 可选：`ConductorState` 增加 `forked_intent_ids: list[str]` 或等价字段。
- [ ] 可选：`types.py` 增加 `ForkResult` dataclass。
- [ ] 环境变量：`SPEC_ORCH_FORK_ENABLED`（默认 true）、`SPEC_ORCH_FORK_TEAM`、`SPEC_ORCH_DRIFT_THRESHOLD` 可覆盖。
- [ ] 更新 `ConductorState.to_dict()` / `from_dict()` 以支持 `forked_intent_ids` 持久化。

### 6. 测试

- [ ] 单元测试：`_maybe_fork()` 在 drift 时被调用，且不修改 state.mode。
- [ ] 单元测试：`_maybe_fork()` 在 CRYSTALLIZE/EXECUTE 下新 actionable 时被调用。
- [ ] 单元测试：无 Linear token 时跳过，无异常。
- [ ] 单元测试：60 秒内相同 intent 不重复 fork。
- [ ] 集成测试（可选）：mock LinearClient，验证 EventBus 与 Memory 写入。
- [ ] 边界测试：fork 期间再 fork 时串行处理，无嵌套。

## 验收

- [ ] 满足 spec.md 中 R1–R7、S7.1–S7.4。
- [ ] 三个用户场景（漂移、新意图、探索结晶）至少前两个可手动验证。
- [ ] 无新增 linter 错误，现有测试通过。

## 设计说明（为何无 design.md）

本变更限定在 Conductor 模块内部：新增 `_maybe_fork()` 方法，在现有 `process_message()` 流程中插入调用点，复用 `LinearClient`、`EventBus`、`MemoryService` 的既有接口。不涉及新模块、新协议或跨系统集成，故无需单独 design 文档，spec + tasks 即可指导实现。
