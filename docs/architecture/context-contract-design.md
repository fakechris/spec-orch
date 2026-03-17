# 上下文治理重构：从"写死 prompt"到"可装配、可追溯的 context contract"

> 日期: 2026-03-17
> 状态: 设计方案确认，待按 Phase 执行
> 前置文档:
> - [编排大脑设计](orchestration-brain-design.md) — 骨架确定性 + 肌肉智能化
> - [进化管线架构](evolution-trigger-architecture.md) — LLM 决策点审计 + 触发模型
> - [Skill-Driven vs Spec-Driven](skill-driven-vs-spec-driven.md) — 混合架构提案
> - [Spec-Contract 集成](spec-contract-integration.md) — 三层 spec 层级

## 一、核心判断

**问题不是流程写死，而是上下文写死。**

当前 12 个 LLM 节点（7 执行管线 + 5 进化管线）各自用 ad-hoc 方式拼装 prompt，
导致三个结构性后果：

1. **信息在节点间被反复压缩和重述** — 上游辛苦做出的丰富结构（如 Scoper
   产出的 wave/packet/scope/criteria），到下游 Builder 时被压缩成一段裸文本
2. **节点可见信息取决于开发者手写了什么** — 而非取决于任务本身需要什么。
   Builder 只吃 `builder_prompt`，Review 只看 diff + spec 摘要，
   PromptEvolver 看聚合指标而非原始失败样本
3. **新增/进化节点时重复造 context 拼装逻辑** — 每个新 Evolver 都要写
   自己的数据采集和 prompt 组装代码

**骨架确定性是对的，不需要推翻。** 文档将 Conductor 定位成路由/分诊而非
全知全能大脑；将 Full / Standard / Hotfix 定义成固定骨架；将进化重点放在
prompt、策略、规则、policy 这些"肌肉"上——这个取舍更可审计、更容易回放、
更容易做离线评估。

要改的是：**让"肌肉"的输入从 ad-hoc prompt 拼装变成可治理的结构化接口。**

## 二、当前 12 个 LLM 节点的上下文问题逐点分析

### 执行管线 7 个节点

#### P1: ReadinessChecker

设计本身偏保守偏工程化：先做规则检查（Goal / Acceptance Criteria / Files
in Scope），规则通过后才可选让 LLM 判断。LLM prompt 明确：足够则输出
`READY`，否则输出编号问题。

**问题**：上下文太薄。核心只有 issue 文本 + 一段证据摘要，没有代码树、
spec 快照、相关模块状态。更擅长发现模板缺项，不擅长发现"任务虽然写全了，
但在当前代码基座下仍然不够可执行"的问题。

#### P2: Planner.plan

优点：有边界，要求把 issue 当不可信输入，只输出 JSON。接收 `issue_id`、
`title`、`summary`、`builder_prompt`、`acceptance_criteria`、
`context.files_to_read`、`architecture_notes`、`constraints`。

**问题**：拿到的是"问题单视角"而非"任务上下文"——没有验证命令、没有
repo 事实、没有相关 spec 原文、没有失败历史。规划出来的澄清问题更多
是在整理 issue，而不是在真正理解任务环境。

#### P3: Planner.answer_questions

系统 prompt 让模型"作为资深工程师，基于 issue 上下文和一般工程最佳实践，
自行回答阻塞问题"。

**问题**：风险偏高。本质上是允许模型把"未知事实"替换成"合理猜测"。
没有接 repo 检索、spec 检索、现有 artifacts。优化的是流程连续性，
不是真实性。

#### P4: Builder (OpenCode / Codex / Claude Code / Droid)

全系统**最大的信息瓶颈**。所有 adapter 传给 builder 模型的核心内容
就是 `PREAMBLE + issue.builder_prompt`。上游关于 spec、约束、scope、
acceptance、验证方式、历史失败等信息，如果没被压进 `builder_prompt`，
builder 运行时就基本看不到。

Builder 能自己读工作区文件，但"应该读什么、为什么读、什么不能碰、
什么必须满足"都没有作为结构化上下文稳定注入。同一个 `builder_prompt`
一旦写偏/写漏/过于抽象，下游系统性偏航。

#### P5: LLMReviewAdapter

角色定义不错（像资深 reviewer 找 bug/逻辑错误/回归风险），但上下文不足：
只有 `git diff HEAD`（截断 60k）、`task.spec.md`（截断 10k）、`issue_id`。

**缺少**：测试输出、verify/gate 结果、改动文件的接口摘要、builder 失败
回放、显式 acceptance criteria 列表。对小改动够用，对跨文件行为、隐性回归、
"代码改对了但任务没做完"这类问题视野不够。

#### P6: Scoper.scope

主流程里 prompt 设计**最完整**的节点。要求把 mission spec 拆成
wave/work packet，强约束首尾 wave 职责，定义 `spec_section`、
`run_class`、`files_in_scope` / `files_out_of_scope`、依赖、验收标准和
`builder_prompt`。上下文也相对完整：mission 标题、完整 spec_content、
acceptance criteria、constraints、file_tree、evidence、hints。

**问题不在本身**，而在下游接口太窄：它辛苦做出的丰富结构，最终被
下游再次压缩（Builder 只拿到 builder_prompt 一段文字）。

#### P7: Conductor.classify_intent

把用户意图分成 exploration / question / quick_fix / feature / bug / drift
六类。拿到最近 6 轮对话（每轮截 200 字）+ 当前消息。

**问题**：对长线程、跨轮澄清、需求漂移脆弱。更关键的是存在**接口不匹配**：
分类器调用 `planner.chat_completion()`，但 planner adapter 没有此接口，
退回到纯规则分类。

### 进化管线 5 个节点

#### E1: PromptEvolver

基于当前 active prompt + 成功率统计 + 历史变体表现生成新 prompt variant。

**问题**：证据太粗。只有聚合统计和变体历史，没有原始失败样本、
任务类别切分、具体错误与 prompt 句式的关联。容易优化到"表面成功率"，
而非真正的失败模式。

#### E2: HarnessSynthesizer

基于历史失败和现有 contracts 合成新的 regex 型 compliance 规则。

**问题**：缺少最关键的输入——触发失败的原始文本片段、builder 输出样本、
成功样本、false positive guard。没有这些，模型很难写出既精确又不误伤的规则。

#### E3: PlanStrategyEvolver

基于近期 run outcome、失败条件、deviation 等提炼 scoper hints。

**问题**：证据是 summary 级别不是 artifact 级别。知道某次 plan 不好，
但未必知道坏在 packet 划分、文件范围、还是 builder_prompt 粒度。

#### E4: PolicyDistiller

把高频模式蒸馏成确定性 Python policy 脚本。

**问题**：候选模式挖掘过于简化。从成功的 verification commands 数频次，
容易抓到"经常被验证"而非"值得自动化"的东西，错过"失败→修复→成功"
这种真正应沉淀成 policy 的轨迹。

#### E5: IntentEvolver

根据 misclassification statistics 和 promotion/demotion correlations
改写分类 prompt。

**问题**：证据弱（粗统计代理信号，非标注样本）+ 实现断裂
（调用 `planner.invoke()`，adapter 未实现，会 `AttributeError`）。

## 三、系统中三类上下文的定义

系统中真正存在三种上下文，但代码里它们分散在 issue payload、
`task.spec.md`、memory event、evidence summary、builder_prompt
等不同载体中，没有统一协议。

| 类别 | 内容 | 当前载体 |
|------|------|---------|
| **契约上下文 (TaskContext)** | mission / spec / acceptance / constraints / scope | issue JSON, task.spec.md |
| **执行上下文 (ExecutionContext)** | file tree / diff / verify / gate / deviation / builder events | report.json, deviations.jsonl, builder_events.jsonl |
| **学习上下文 (LearningContext)** | run history / prompt variants / contracts / hints / policies | prompt_history.json, scoper_hints.json, policies_index.json |

当前 Memory 实现无法弥补这个缺口。`MemoryService` 更像事件归档器；
底层 `fs_provider` 的 recall 靠 layer/tags/metadata filters 和简单文本匹配，
不是能按语义和任务需求动态装配上下文的检索系统。

## 四、重构方案：ContextBundle + ArtifactRegistry

### 4.1 ContextBundle 数据结构

```python
from dataclasses import dataclass, field
from spec_orch.domain.models import (
    Issue, GateVerdict, ReviewSummary, VerificationSummary,
)

@dataclass
class TaskContext:
    """契约上下文：任务做什么、边界是什么"""
    issue: Issue
    spec_snapshot_text: str
    acceptance_criteria: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    files_in_scope: list[str] = field(default_factory=list)
    files_out_of_scope: list[str] = field(default_factory=list)
    architecture_notes: str = ""

@dataclass
class ExecutionContext:
    """执行上下文：当前代码状态和运行事实"""
    file_tree: str = ""
    git_diff: str = ""
    verification_results: VerificationSummary | None = None
    gate_report: GateVerdict | None = None
    builder_events_summary: str = ""
    review_summary: ReviewSummary | None = None
    deviation_slices: list[dict] = field(default_factory=list)

@dataclass
class LearningContext:
    """学习上下文：历史经验和进化产物"""
    recent_run_summary: dict | None = None
    similar_failure_samples: list[dict] = field(default_factory=list)
    active_prompt_variant_id: str = ""
    scoper_hints: list[dict] = field(default_factory=list)
    relevant_policies: list[str] = field(default_factory=list)

@dataclass
class ContextBundle:
    """统一上下文包，由 ContextAssembler 组装"""
    task: TaskContext
    execution: ExecutionContext = field(default_factory=ExecutionContext)
    learning: LearningContext = field(default_factory=LearningContext)
```

### 4.2 NodeContextSpec：节点声明式消费合约

```python
@dataclass
class NodeContextSpec:
    """每个 LLM 节点声明自己需要什么上下文"""
    node_name: str
    required_task_fields: list[str]
    required_execution_fields: list[str] = field(default_factory=list)
    required_learning_fields: list[str] = field(default_factory=list)
    optional_fields: list[str] = field(default_factory=list)
    max_tokens_budget: int = 8000
```

示例声明：

| 节点 | 必需 task 字段 | 必需 execution 字段 | 必需 learning 字段 | token 预算 |
|------|-------------|-------------------|------------------|-----------|
| Builder | issue, spec, acceptance, constraints, files_in/out | file_tree | similar_failure_samples | 12000 |
| LLMReview | issue, spec, acceptance | git_diff, verification, gate | — | 16000 |
| ReadinessChecker | issue | file_tree | recent_run_summary | 4000 |
| PromptEvolver | — | — | similar_failure_samples, active_variant | 6000 |
| HarnessSynthesizer | — | — | similar_failure_samples | 8000 |

### 4.3 ArtifactRegistry

每次 run 产出的制品需要有稳定的 ID 和路径约定：

```python
@dataclass
class ArtifactManifest:
    """每次 run 的制品清单"""
    run_id: str
    issue_id: str
    artifacts: dict[str, str]  # artifact_type -> file_path
```

标准 artifact 类型：

| artifact_type | 路径 | 内容 |
|---------------|------|------|
| `spec_snapshot` | `{workspace}/spec_snapshot.json` | 审批后的 spec 快照 |
| `builder_report` | `{workspace}/builder_report.json` | Builder 执行报告 |
| `builder_events` | `{workspace}/telemetry/incoming_events.jsonl` | Builder 原始事件流 |
| `verification` | 嵌入 `report.json` | 4 步验证结果 |
| `gate_report` | 嵌入 `report.json` | Gate 判定和条件 |
| `review_report` | 嵌入 `report.json` | Review verdict 和 issues |
| `deviations` | `{workspace}/deviations.jsonl` | 偏差记录 |
| `explain` | `{workspace}/explain.md` | 可读的判定解释 |
| `prompt_variant` | `prompt_history.json` 中的条目 | 使用的 prompt 变体 ID |

### 4.4 ContextAssembler

```python
class ContextAssembler:
    """从 ArtifactRegistry + MemoryService + Issue 组装 ContextBundle"""

    def assemble(
        self,
        spec: NodeContextSpec,
        issue: Issue,
        workspace: Path,
        memory: MemoryService | None = None,
    ) -> ContextBundle:
        """按节点的 NodeContextSpec 组装上下文，控制 token 预算"""
        ...
```

职责：
- 从 workspace 中读取 artifacts（spec snapshot、report、deviations 等）
- 从 MemoryService 中 recall 相关历史
- 按 `NodeContextSpec.required_*` 和 `optional_fields` 组装
- 按 `max_tokens_budget` 做截断/摘要
- 返回完整的 `ContextBundle`

每个 LLM 节点不再自己拼字符串，而是：
1. 定义自己的 `NodeContextSpec`（静态声明）
2. 调用 `assembler.assemble(spec, issue, workspace)` 获取 `ContextBundle`
3. 用 `ContextBundle` 渲染自己的 prompt（可以有 adapter 特定的渲染逻辑）

## 五、改造优先级

### Phase 0: 修接口和观测（基础设施）

| 任务 | 涉及文件 | 说明 |
|------|---------|------|
| 统一 LLM client protocol | `intent_evolver.py`, `conductor/intent_classifier.py` | `invoke()`/`chat_completion()` 对齐到 `brainstorm()` |
| `record_flow_transition` 接入 Memory | `run_controller.py` | stub → 真正写入 MemoryService |
| ArtifactManifest + 标准化落盘 | `domain/models.py`, `run_controller.py` | 每次 run 结束写 manifest |

### Phase 1: ContextBundle + ArtifactRegistry（核心改造）

优先改造 3 个节点：

1. **Builder** (P4) — 全系统最大的信息瓶颈。从 `PREAMBLE + builder_prompt`
   改为 `ContextBundle → BuilderEnvelope → adapter 特定渲染`。BuilderEnvelope
   至少包括：任务目标、acceptance criteria、files in/out of scope、建议优先
   读的文件、验证方式、禁止事项、相关 spec section、近期同类失败摘要

2. **LLMReviewAdapter** (P5) — 除了 diff 和 spec，稳定带上 verify/gate
   结果、改动文件摘要、显式 acceptance criteria

3. **HarnessSynthesizer** (E2) — 从 failure summary 改为带原始失败样本
   的证据包

### Phase 2: 进化管线从"报表驱动"升级到"案例驱动"

- **PromptEvolver**：按任务类型 + adapter + 失败模式分桶；feed 原始失败样本
- **HarnessSynthesizer**：触发失败的原始文本 + 成功对照 + false positive guard
- **PlanStrategyEvolver**：具体 packet/依赖设计与失败的关联
- **PolicyDistiller**：从频次统计改为"失败→修复→成功"轨迹挖掘
- 统一 evolution lifecycle: `observe → propose → validate → promote`

### Phase 3: 配置驱动触发 + 可选 EvolutionAgent

在 Phase 0-2 稳定后：
- `spec-orch.toml` 的 `[evolution]` 段控制触发策略
- EvolutionPolicy engine 按配置触发 Evolver
- 可选的薄 EvolutionAgent 层做排序和优先级判断

### 建议路径

**不要急着把"写死流程"改成"自由 agent 流程"；先把"写死上下文"改成
"可装配、可追溯、可评估的上下文系统"。**

所有脑子都在拿不完整、不可复用、不可追溯的局部信息做判断。
骨架可以先不动，先把 context contract、artifact registry、
evolution validation 做起来，系统的上限会立刻高很多。

## 六、与现有设计的关系

### 与"骨架确定性、肌肉智能化"的一致性

ContextBundle 不改变骨架（流程拓扑、步骤序列、回退路径），只改变
肌肉的输入接口。骨架仍然是 Full / Standard / Hotfix 三种固定流程；
肌肉（每个 LLM 节点）从"自己找饭吃"变成"点菜式供餐"。

### 与 Adapter Factory 的兼容

ContextAssembler 和 AdapterFactory 是正交的：
- AdapterFactory 决定"用哪个 adapter 执行"
- ContextAssembler 决定"给 adapter 什么上下文"
- 两者通过 `ContextBundle` 解耦

### 与 Memory 子系统的关系

ContextAssembler 使用 MemoryService 作为 LearningContext 的数据源，
但不取代 Memory 的存储和检索职责。未来如果引入 MemRL 式的
Q-value 检索，改动在 MemoryProvider 层面，不影响 ContextBundle 接口。

## 七、Linear Issues

| Issue | Phase | 类型 | 前置 |
|-------|-------|------|------|
| **SON-123: 上下文治理与进化管线重构** | — | Epic | — |
| SON-125: 统一 LLM client protocol (invoke/chat_completion) | 0 | bugfix | — |
| SON-126: record_flow_transition 接入 MemoryService | 0 | bugfix | — |
| SON-127: ArtifactManifest + 标准化 artifact 落盘 | 0 | feature | — |
| SON-128: ContextBundle 三包数据结构设计 | 1 | feature | Phase 0 |
| SON-129: NodeContextSpec + ContextAssembler | 1 | feature | SON-128 |
| SON-130: Builder envelope 结构化渲染 | 1 | feature | SON-129 |
| SON-131: LLMReviewAdapter 上下文扩充 | 1 | feature | SON-129 |
| SON-132: HarnessSynthesizer 证据包改造 | 1 | feature | SON-129 |
| SON-133: PromptEvolver 分桶 + 样本驱动 | 2 | feature | SON-127 |
| SON-134: Evolution lifecycle 统一 (observe/propose/validate/promote) | 2 | feature | Phase 1 |
| SON-135: spec-orch.toml [evolution] 触发策略 | 3 | feature | Phase 2 |
