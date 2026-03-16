# PRD: 骨架流程引擎

> **Change**: 01-scaffold-flow-engine  
> **Linear Issues**: SON-107, SON-108, SON-109  
> **状态**: 草稿

## Background

当前 spec-orch 的 `RunController` 对单 issue 生命周期进行编排，但采用**隐式单一流程**：所有变更（新功能、Bug 修复、紧急热修）都走同一套步骤序列。`docs/architecture/change-management-policy.md` 已定义三种变更层级（Full / Standard / Hotfix），但仅存在于文档中，代码层面未实现流程区分。

编排大脑设计（`orchestration-brain-design.md`）确立了「骨架确定性 + 肌肉智能化」的两层架构：骨架层定义流程拓扑、步骤转换条件、回退路径，必须可测试、可审计。

## Problem

1. **无流程类型选择**：RunController 对所有变更一视同仁，无法根据变更性质选择 Full / Standard / Hotfix。
2. **无升降级机制**：Gate 后验发现「声称 doc-only 实际改了代码」时，无法触发流程升级；Conductor 建议降级时，Gate 无法确认。
3. **步骤不可跳过**：即使变更类型明确（如纯文档修改），也无法跳过不必要的步骤（如完整 verify）。
4. **回退路径未显式建模**：Gate 判定失败时，应区分 recoverable / needs_redesign / promotion_required，但当前无结构化回退逻辑。

## Goal

实现**确定性流程图引擎**，具备：

- 三种流程类型（Full / Standard / Hotfix）的 DAG 定义
- 步骤序列、转换条件、可跳过条件
- Gate 触发的流程升级（promotion）
- Conductor 建议 + Gate 确认的流程降级（demotion）
- 升降级事件记录到 Episodic Memory
- Intent → Flow 的可配置映射（非硬编码）

## Non-goals

- **不构建完全动态的工作流引擎**：流程拓扑固定，不支持运行时定义新流程类型。
- **不替换 RunController**：RunController 仍是编排入口，仅改为「按 FlowGraph 驱动」。
- **不实现 Episodic Memory 存储**：本 change 仅定义升降级事件的数据模型和写入接口，存储实现由后续 change 负责。
- **不实现 Hotfix 的 Daemon 自动化**：change-management-policy 中 Hotfix 的 daemon 行为标注为 future，本 change 仅完成流程定义和引擎能力。

## Primary User / Stakeholder

- **DMA / Daemon**：自动选取 issue 并执行时，需根据 Linear 标签或 Conductor Intent 选择流程类型。
- **人类操作者**：通过 CLI 显式指定流程类型（如 `spec-orch run --flow hotfix`）或依赖自动选择。
- **Gate / Conductor**：作为流程升降级的触发方和确认方。

## User Scenarios

### 场景 1：新功能走 Full 流程

用户通过 Conductor 讨论后 crystallize 为 Feature，系统创建 Linear issue。Daemon 拉取该 issue，Conductor 的 Intent 为 `Feature`，映射到 Full 流程。执行完整 EODF 管线：discuss → freeze → plan → promote → execute → verify → gate → PR → merge → retro。

### 场景 2：Bug 修复走 Standard 流程

用户创建带 `Bug` 标签的 Linear issue，Daemon 拉取。Intent 映射为 Standard，跳过 discuss / freeze / plan / promote，直接 implement → verify → gate → PR。

### 场景 3：生产阻断走 Hotfix 流程

用户创建带 `hotfix` 标签的 issue。系统选择 Hotfix 流程，使用 minimal gate profile，pre-merge review 可选，post-merge review 必选。

### 场景 4：执行中流程降级

Conductor 建议某 Feature 实际范围很小，可降级到 Standard。Gate 在 verify 后检查：改动量、涉及文件数等均在阈值内，确认降级。流程从 Standard 的起点继续，升降级事件写入 Episodic Memory。

### 场景 5：Gate 触发流程升级

某 issue 以 Standard 启动（声称 doc-only）。Gate 发现实际修改了核心代码，判定 `promotion_required`，拒绝当前流程，要求升级到 Full 并从 Full 的 spec 阶段重新开始。

## Success Metrics

| 指标 | 目标 | 验证方式 |
|------|------|---------|
| 流程类型正确选择 | Intent → Flow 映射与 change-management-policy 决策矩阵一致 | 单元测试覆盖所有 IntentCategory |
| 升降级可触发 | Gate 能发出 promotion/demotion 信号，RunController 能响应 | 集成测试 |
| 回退路径可区分 | Gate 失败原因分类为 recoverable / needs_redesign / promotion_required | 单元测试 |
| 现有行为不破坏 | 未指定 flow 时，默认行为与当前 RunController 一致 | 回归测试 |
| 可配置性 | Intent→Flow 映射可通过 YAML 配置，无需改代码 | 配置加载测试 |

## Risks / Open Questions

1. **Episodic Memory 接口**：升降级事件写入接口的契约需与后续 Memory 模块对齐，避免重复设计。
2. **Gate 后验指标**：判定「改动量超预期」需要具体指标（如 diff 行数、涉及目录深度），需与 GatePolicyEvolver 的输入格式一致。
3. **Conductor 与 RunController 的衔接**：Conductor 建议降级时，RunController 可能尚未启动；需明确「建议」的存储位置和生效时机。
4. **Hotfix 的 minimal gate**：GatePolicy 的 `minimal` profile 是否已存在？若不存在，需在本 change 或依赖 change 中补充。
