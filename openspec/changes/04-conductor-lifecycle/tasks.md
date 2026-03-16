# 任务清单：Conductor 全生命周期拦截

> **Change**: 04-conductor-lifecycle | **无 design.md**：本变更为单模块（Conductor）能力扩展 + RunController 集成点插入，不涉及跨模块架构重构、新协议或格式解析，故跳过 design 阶段。详见文末说明。

## 前置

- [ ] Change 01（scaffold-flow-engine）已合并或可并行开发。
- [ ] Change 02（conductor-fork）已合并或可并行；fork 逻辑可复用。

## 实现任务

### 1. 类型与接口

- [ ] 在 `conductor/types.py` 中新增 `DMAStage` 枚举、`InterceptResult` dataclass、`UserInputSource`（可选）。
- [ ] 在 `conductor/conductor.py` 中实现 `intercept(stage, user_input, context) -> InterceptResult`。
- [ ] `intercept()` 内部调用 `classify_intent()`，根据 `IntentSignal` 映射到 `action`（continue/pause/redirect/fork）。

### 2. RunController 集成

- [ ] `RunController.__init__` 增加可选参数 `user_input_provider: Callable[[], str | None]`。
- [ ] 在 `_run_builder` 前、后插入拦截点：若有输入则调用 `Conductor.intercept()`，根据 `action` 决定是否中断。
- [ ] 在 `verification_service.run` 前、后插入拦截点。
- [ ] 在 `review_adapter` 调用前、后插入拦截点。
- [ ] 在 `gate_service.evaluate` 前插入拦截点。
- [ ] 实现 `action=pause` 时返回 `RunState.PAUSED` 或等价机制。

### 3. 动作实现

- [ ] `action=continue`：无操作，继续流程。
- [ ] `action=pause`：设置 run 状态为暂停，返回控制权。
- [ ] `action=redirect`：根据 `metadata.target_stage` 或 `target_issue_id` 实现重定向逻辑（或标记为 TODO，由后续 change 实现）。
- [ ] `action=fork`：复用 Change 02 的 `_maybe_fork()` 或实现最小 fork 路径。

### 4. 配置与去重

- [ ] 环境变量：`SPEC_ORCH_INTERCEPT_ENABLED`、`SPEC_ORCH_INTERCEPT_STAGES`。
- [ ] 实现 60 秒内相同输入哈希不重复触发的去重逻辑。

### 5. 测试

- [ ] 单元测试：`intercept()` 在无输入时不被 RunController 调用（通过 mock 验证）。
- [ ] 单元测试：`intercept()` 返回 `continue` 时流程不变。
- [ ] 单元测试：`intercept()` 返回 `pause` 时 RunController 正确暂停。
- [ ] 单元测试：`SPEC_ORCH_INTERCEPT_ENABLED=false` 时拦截点不执行。
- [ ] 集成测试（可选）：mock user_input_provider，验证 build 阶段拦截流程。

## 验收

- [ ] 满足 spec.md 中 R1–R7、S7.1–S7.3。
- [ ] 至少一个非 conversation 阶段（如 build）可手动验证拦截行为。
- [ ] 无新增 linter 错误，现有测试通过。

## 设计说明（为何无 design.md）

本变更限定为：1）Conductor 新增 `intercept()` 方法及配套类型；2）RunController 在既有流程节点插入调用。不涉及新模块、新协议、格式解析或跨系统集成。Conductor 与 RunController 的集成方式为「函数调用 + 回调」，无需单独架构设计文档，spec + tasks 即可指导实现。
