# OpenSpec 质量审查

> 审查范围：6 个 change，29 个文件，共约 2100 行
> 审查维度：spec 粒度、实现锁定度、失败路径、回归风险、任务可验证性、三者一致性

## 1. 整体评价

| 维度 | 评分 | 说明 |
|------|------|------|
| Issue → Change 映射合理性 | A | 13 个 issue 合并为 6 个 change，分组逻辑清晰，依赖链明确 |
| PRD 质量 | B+ | 场景覆盖充分，Non-goals 明确；部分 Success metrics 偏定性缺量化 |
| Spec 质量 | A- | Given/When/Then 格式规范，边界条件覆盖好；少量需补充（见下） |
| Design 质量 | B+ | 01 和 03 的设计足够指导实现；06 的设计最详细但 Tessl parser 存疑 |
| Tasks 质量 | A | 拆分粒度合适，每个 task 有验证方式，并行标记清晰 |
| 三者一致性 | A- | proposal/spec/tasks 整体一致，少量 spec 需求未映射到 task（见下） |

## 2. 各 Change 具体问题

### Change 01: scaffold-flow-engine

**优点：**
- REQ-1 到 REQ-8 覆盖完整，从定义到兼容性全链路
- 升降级的双重确认机制（Conductor 建议 + Gate 确认）设计合理
- REQ-8 兼容性要求（默认 Standard、接口不变、回归通过）是正确约束

**需补充：**
- [ ] REQ-5.2 提到 Linear 标签覆盖 Intent 映射，但 spec 未定义标签的优先级规则
  （如标签 `hotfix` + Intent `Feature` 时谁赢？）
- [ ] 缺少 FlowGraph 的序列化/持久化需求——如果 run 中途 crash 重启，
  flow state 是否需要恢复？当前 RunState 有持久化但 FlowType 没有
- [ ] tasks.md T5.3 的 `--flow` CLI 参数与 FlowMapper 的自动选择可能冲突，
  需要在 spec 中明确优先级：显式 > 标签 > Intent

**实现锁死风险：**
- design.md 中 `flow_engine/graphs.py` 的模块路径比较具体，可考虑留更多自由度

### Change 02: conductor-fork

**优点：**
- 边界场景 S7.1-S7.4 覆盖精准，60 秒去重和串行 fork 是务实选择
- R6.2 限流降级为本地 `.spec_orch_conductor/forks.jsonl` 是好设计

**需补充：**
- [ ] 缺少 fork 后的同步机制——本地 forks.jsonl 何时回写 Linear？
  可以标注为 out-of-scope 但需显式声明
- [ ] R2.3 对话摘要的截断策略（100 字符/条 * 3-5 条）可能不够，
  建议 spec 改为"合计不超过 500 字符"而非固定每条

**不需要 design 的判断：** 正确，单模块内改动

### Change 03: muscle-evolvers

**优点：**
- 三个进化器的数据源 → 机制 → 输出 → 错误处理结构统一
- R4.2 解耦原则（进化器间无调用链）很重要
- 事件类型表（§4.2）定义清晰

**需补充：**
- [ ] IntentEvolver 的 A/B 测试需要明确：是在生产 intent 分类中同时运行两个
  prompt（影响真实用户），还是用离线 replay 数据？spec 中 R1.6 说"并行运行 N 次"
  但未说明是 shadow mode 还是 live
- [ ] GatePolicyEvolver 的 R3.2 "下游结果"如何获取？如果 merge 后 regression
  的信号来源是后续 run 的 Gate fail，需要跨 issue 关联——这个机制 spec 未定义
- [ ] 场景 A 中"运行 50 次后"是硬编码阈值还是可配置？应显式声明

**实现锁死风险：**
- design.md 提到"通用 Evolver 接口提取"，但现有 4 个进化器没有统一接口。
  如果要做统一，可能需要先 refactor 现有进化器——这是一个前置依赖，spec 未覆盖

### Change 04: conductor-lifecycle

**优点：**
- DMAStage 枚举 + InterceptResult 设计简洁
- R2.6 "无输入时零开销"是关键性能约束
- R5.1/R5.2 与 ConversationService 的兼容边界明确

**需补充：**
- [ ] R4.2 `pause` 动作需要 RunController 支持 PAUSED 状态——当前 RunState
  没有 PAUSED。这是一个 models.py 改动，应在 spec 中明确
- [ ] R2.1 `user_input_provider: Callable` 的调用时机不够精确——"关键节点"
  具体是哪些？建议列举所有 intercept point

### Change 05: spec-discovery-paths

**优点：**
- 参数互斥（R3.1-R3.3）处理完善
- 降级策略（LLM 不可用时用空白骨架）务实

**需补充：**
- [ ] R2.4 反推的 spec 质量如何保证？是否需要人工审核标记？
  建议 mission.json 增加 `source: "reverse-engineered"` 字段
- [ ] 缺少模板列表命令——如何发现可用模板？`mission list` 是否
  需要标注哪些 mission 适合作为模板？

### Change 06: flexible-orchestration

**优点：**
- GateCheckSkill Protocol 设计干净，与现有 BUILTIN_SKILLS 的迁移路径清晰
- design.md 最详细，ComplianceEngine 与 Gate 的职责边界很好

**需补充：**
- [ ] SON-105 的 Tessl 格式——Tessl 格式是否公开？如果未公开，
  这个 parser 可能无法实现。建议标注为 optional/deferred
- [ ] SpecStructure 的 `raw_sections` 字段没有被后续消费——
  如果 spec 导入后只取 goal/scope/AC，raw_sections 的价值需要论证
- [ ] 外部 Skill 的安全性——`skill:<id>` 从路径加载代码，是否需要沙箱？
  至少 spec 应声明"仅加载项目内 Python 模块，不执行任意路径"

## 3. 跨 Change 一致性检查

| 检查项 | 结果 | 说明 |
|--------|------|------|
| Change 01 的 FlowType 被 02/03/04/06 正确引用 | 通过 | 依赖方向一致 |
| Change 02 的 fork 能力被 04 正确复用 | 通过 | R4.4 显式引用 |
| Change 03 的事件类型与 01 的 FlowTransitionEvent 一致 | 通过 | 都用 Episodic Memory + tags |
| Change 01 的 GateVerdict 扩展与 06 的 GateCheckSkill 不冲突 | 需确认 | 两者都改 GateService，实施顺序需协调 |
| SON-97 未纳入 change | 正确 | 探索性工作，产出已沉淀为文档 |

## 4. 建议调整

1. **Change 01 和 06 的 GateService 改造存在冲突风险**。建议：01 先做
   promotion/demotion（扩展 GateVerdict），06 再做 Skill 化（重构 evaluate 内部）。
   在 tasks 中明确 06 依赖 01 完成后再开始 Gate 相关任务。

2. **Change 03 的"通用 Evolver 接口"是否需要独立 change？**
   当前 4 个进化器没有统一 Protocol。如果 03 要求新进化器遵循统一接口，
   可能需要先 refactor 现有进化器。建议拆出 `03a-evolver-protocol`
   或在 tasks 中作为 Phase 0。

3. **SON-98 已被 SON-102 完全吸收**。建议在 Linear 中将 SON-98 关闭并
   标注 "absorbed by SON-102"，避免重复跟踪。

## 5. Issue 分类汇总

| Issue | 类型 | 适合进入 | 说明 |
|-------|------|---------|------|
| SON-97 | exploration/docs | 已完成（文档） | 不转 change |
| SON-98 | feature | spec (被 SON-102 吸收) | 关闭并引用 SON-102 |
| SON-101 | feature | PRD + spec | 模板库 |
| SON-102 | feature | PRD + spec + tasks | Conductor 生命周期 |
| SON-103 | feature + infra | PRD + spec + design | Gate Skill 化 |
| SON-104 | feature | PRD + spec | 示例反推 |
| SON-105 | feature | PRD + spec + design | 格式兼容 |
| SON-107 | feature | PRD + spec + design + tasks | 核心骨架 |
| SON-108 | feature | spec + tasks | 升降级 |
| SON-109 | feature | spec + tasks | Intent 映射 |
| SON-110 | feature | PRD + spec + tasks | Fork |
| SON-111 | feature | spec + tasks | IntentEvolver |
| SON-112 | feature | spec + tasks | FlowPolicyEvolver |
| SON-113 | feature | spec + tasks | GatePolicyEvolver |
| SON-114 | infra | spec + design + tasks | 数据管道 |

## 6. 下一步命令

```bash
# 1. 审阅 openspec/ 目录中的所有草稿
# 2. 确认分组和优先级后，将 change 转为正式 mission：
spec-orch mission create "骨架流程引擎" --from-example openspec/changes/01-scaffold-flow-engine/spec.md
# （当 --from-example 实现后；否则手动复制 spec.md 到 docs/specs/）

# 3. 或者直接按 change 逐个执行：
#    a. 先在 Linear 更新 SON-107/108/109 的 description，附上 spec 链接
#    b. 按 tasks.md 拆为 work packets
#    c. spec-orch promote <mission-id>
```
